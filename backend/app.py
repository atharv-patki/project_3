import os
import math
from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from database import DatabaseManager
from storage_service import StorageService
from security import verify_file_signature, CleanupWorker
from worker import queue_transcode_job

# Allowed video extensions
ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv'}

def allowed_file(filename):
    suffix = os.path.splitext(filename)[1].lower()
    return suffix in ALLOWED_EXTENSIONS

def create_app():
    # Initialize directory structure
    Config.init_app()
    
    # Initialize SQLite database
    DatabaseManager.init_db()

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Start background cleanup task (daemon thread)
    # Avoid duplicate threads during Flask reloader reload
    if not Config.DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Default cleanup: check every 10 minutes, expire files after 2 hours
        cleanup_worker = CleanupWorker(expiry_seconds=7200, check_interval_seconds=600)
        cleanup_worker.start()

    # Generic Error Handlers
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad Request", "message": str(e.description)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found", "message": str(e.description)}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method Not Allowed", "message": str(e.description)}), 405

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"error": e.name, "message": e.description}), e.code
            
        app.logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected server error occurred."
        }), 500

    @app.route('/api/health', methods=['GET'])
    def health_check():
        temp_writable = os.access(Config.UPLOAD_TEMP_DIR, os.W_OK)
        final_writable = os.access(Config.UPLOAD_FINAL_DIR, os.W_OK)
        return jsonify({
            "status": "healthy",
            "environment": Config.ENV,
            "max_file_size_bytes": Config.MAX_CONTENT_LENGTH,
            "chunk_size_bytes": Config.CHUNK_SIZE,
            "storage": {
                "temp_directory": str(Config.UPLOAD_TEMP_DIR),
                "temp_writable": temp_writable,
                "final_directory": str(Config.UPLOAD_FINAL_DIR),
                "final_writable": final_writable
            }
        }), 200

    @app.route('/api/upload/initiate', methods=['POST'])
    def initiate_upload():
        data = request.get_json() or {}
        filename = data.get('filename')
        file_size = data.get('file_size')

        if not filename or not file_size:
            return jsonify({"error": "Missing filename or file_size parameters."}), 400

        if not allowed_file(filename):
            return jsonify({"error": f"Unsupported file extension. Allowed: {list(ALLOWED_EXTENSIONS)}"}), 400

        try:
            file_size = int(file_size)
            if file_size <= 0:
                raise ValueError()
        except ValueError:
            return jsonify({"error": "file_size must be a positive integer."}), 400

        if file_size > Config.MAX_CONTENT_LENGTH:
            return jsonify({"error": f"File size exceeds maximum limit of {Config.MAX_CONTENT_LENGTH} bytes."}), 400

        # Calculate chunk limits
        chunk_size = Config.CHUNK_SIZE
        total_chunks = math.ceil(file_size / chunk_size)

        video_id = StorageService.generate_video_id()

        try:
            # Register in database
            DatabaseManager.create_upload_session(video_id, filename, file_size, total_chunks)
            # Register on disk
            StorageService.initiate_upload(video_id)
        except Exception as e:
            return jsonify({"error": f"Failed to initialize upload: {str(e)}"}), 500

        return jsonify({
            "video_id": video_id,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "status": "initiated"
        }), 201

    @app.route('/api/upload/chunk', methods=['POST'])
    def upload_chunk():
        video_id = request.form.get('video_id')
        chunk_index = request.form.get('chunk_index')
        
        if 'file' not in request.files:
            return jsonify({"error": "No file part in the request."}), 400
            
        file = request.files['file']

        if not video_id or chunk_index is None:
            return jsonify({"error": "Missing video_id or chunk_index."}), 400

        try:
            chunk_index = int(chunk_index)
        except ValueError:
            return jsonify({"error": "chunk_index must be an integer."}), 400

        # Fetch session from DB
        session = DatabaseManager.get_upload_session(video_id)
        if not session:
            return jsonify({"error": f"Upload session '{video_id}' not found."}), 404

        if chunk_index < 0 or chunk_index >= session['total_chunks']:
            return jsonify({"error": f"Invalid chunk index. Must be between 0 and {session['total_chunks'] - 1}."}), 400

        try:
            # Read chunk raw bytes
            chunk_data = file.read()
            
            # Security verification: check file magic bytes on chunk 0
            if chunk_index == 0:
                if not verify_file_signature(chunk_data, session['filename']):
                    # Delete partial temporary directory
                    import shutil
                    temp_dir = StorageService.get_upload_temp_dir(video_id)
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                    # Mark failed in DB
                    DatabaseManager.update_status(video_id, 'failed')
                    return jsonify({
                        "error": "Security Verification Failed",
                        "message": "The uploaded file header does not match its declared video extension structure."
                    }), 400

            # Save raw bytes to disk
            StorageService.save_chunk(video_id, chunk_index, chunk_data)
            
            # If status was initiated, change to uploading
            if session['status'] == 'initiated':
                DatabaseManager.update_status(video_id, 'uploading')
        except Exception as e:
            return jsonify({"error": f"Failed to save chunk: {str(e)}"}), 500

        return jsonify({
            "video_id": video_id,
            "chunk_index": chunk_index,
            "status": "success"
        }), 200

    @app.route('/api/upload/complete', methods=['POST'])
    def complete_upload():
        data = request.get_json() or {}
        video_id = data.get('video_id')

        if not video_id:
            return jsonify({"error": "Missing video_id."}), 400

        session = DatabaseManager.get_upload_session(video_id)
        if not session:
            return jsonify({"error": f"Upload session '{video_id}' not found."}), 404

        if session['status'] == 'completed':
            return jsonify({"error": "Upload session already completed."}), 400

        try:
            # Merge and clean up
            final_path = StorageService.merge_chunks(
                video_id=video_id,
                original_filename=session['filename'],
                total_chunks=session['total_chunks'],
                expected_size=session['file_size']
            )
            # Update database status
            DatabaseManager.update_status(video_id, 'completed')
            
            # Queue background transcoding job
            try:
                queue_transcode_job(video_id)
            except Exception as w_err:
                print(f"[-] Failed to enqueue transcode job for {video_id}: {w_err}")
        except Exception as e:
            DatabaseManager.update_status(video_id, 'failed')
            return jsonify({"error": f"Failed to complete and merge upload: {str(e)}"}), 500

        return jsonify({
            "video_id": video_id,
            "status": "completed",
            "filename": session['filename'],
            "filepath": str(final_path)
        }), 200

    @app.route('/api/upload/status/<video_id>', methods=['GET'])
    def upload_status(video_id):
        session = DatabaseManager.get_upload_session(video_id)
        if not session:
            return jsonify({"error": f"Upload session '{video_id}' not found."}), 404

        # Calculate progress
        status = session['status']
        progress_percentage = 0.0

        if status == 'completed':
            progress_percentage = 100.0
        elif status == 'failed':
            progress_percentage = 0.0
        else:
            # Count the chunks currently on disk to determine progress
            temp_dir = StorageService.get_upload_temp_dir(video_id)
            if temp_dir.exists():
                try:
                    uploaded_chunks = len([name for name in os.listdir(temp_dir) if name.startswith("chunk_")])
                    progress_percentage = round((uploaded_chunks / session['total_chunks']) * 100, 2)
                except Exception:
                    progress_percentage = 0.0

        return jsonify({
            "video_id": video_id,
            "filename": session['filename'],
            "file_size": session['file_size'],
            "total_chunks": session['total_chunks'],
            "status": status,
            "progress_percent": progress_percentage
        }), 200

    @app.route('/api/videos', methods=['GET'])
    def list_videos():
        try:
            videos = DatabaseManager.list_uploads()
            return jsonify(videos), 200
        except Exception as e:
            return jsonify({"error": f"Failed to list videos: {str(e)}"}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"[*] Starting Video Pipeline API on {Config.HOST}:{Config.PORT} in {Config.ENV} mode...")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
