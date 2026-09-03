import os
import math
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config import Config
from database import DatabaseManager
from storage_service import StorageService
from security import verify_file_signature, CleanupWorker
from worker import queue_transcode_job

try:
    from analytics_schema import validate_event, PlaybackEvent
    from kafka_service import get_kafka_service
    from traffic_generator import get_traffic_generator
except ImportError:
    from backend.analytics_schema import validate_event, PlaybackEvent
    from backend.kafka_service import get_kafka_service
    from backend.traffic_generator import get_traffic_generator

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

    @app.route('/api/transcode/status/<video_id>', methods=['GET'])
    def transcode_status(video_id):
        session = DatabaseManager.get_upload_session(video_id)
        if not session:
            return jsonify({"error": f"Video session '{video_id}' not found."}), 404
            
        return jsonify({
            "video_id": video_id,
            "transcode_status": session.get('transcode_status', 'none'),
            "transcode_progress": session.get('transcode_progress', 0.0),
            "path_720p": session.get('path_720p'),
            "path_480p": session.get('path_480p'),
            "path_thumbnail": session.get('path_thumbnail')
        }), 200

    @app.route('/stream/<path:filename>', methods=['GET'])
    def stream_file(filename):
        try:
            return send_from_directory(Config.UPLOAD_FINAL_DIR, filename)
        except FileNotFoundError:
            return jsonify({"error": "File not found."}), 404

    # -------------------------------------------------------------
    # Real-Time Streaming Analytics & Telemetry Ingestion Endpoints
    # -------------------------------------------------------------
    @app.route('/api/analytics/event', methods=['POST'])
    def ingest_event():
        """
        Ingests a single video viewer telemetry heartbeat event.
        Validates the schema and publishes the event to the Kafka message broker.
        """
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"error": "Bad Request", "message": "Missing or invalid JSON payload."}), 400

        # Auto-detect client IP if not supplied
        if 'client_ip' not in payload or not payload['client_ip']:
            payload['client_ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)

        try:
            event = validate_event(payload)
        except ValueError as val_err:
            return jsonify({"error": "Validation Error", "message": str(val_err)}), 400

        broker = get_kafka_service()
        published = broker.publish_event(event)

        if not published:
            return jsonify({"error": "Broker Error", "message": "Failed to enqueue telemetry event."}), 503

        return jsonify({
            "status": "accepted",
            "session_id": event.session_id,
            "video_id": event.video_id,
            "received_at": time.time()
        }), 202

    @app.route('/api/analytics/events/batch', methods=['POST'])
    def ingest_batch_events():
        """
        High-throughput batch ingestion for video player telemetry events.
        Accepts a JSON array of events or an object with an 'events' list.
        """
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Bad Request", "message": "Missing JSON payload."}), 400

        if isinstance(body, dict):
            raw_events = body.get("events", [])
        elif isinstance(body, list):
            raw_events = body
        else:
            return jsonify({"error": "Bad Request", "message": "Batch payload must be a JSON array or object with an 'events' list."}), 400

        if not raw_events or not isinstance(raw_events, list):
            return jsonify({"error": "Bad Request", "message": "Batch cannot be empty."}), 400

        if len(raw_events) > 5000:
            return jsonify({"error": "Payload Too Large", "message": "Batch size exceeds maximum limit of 5000 events."}), 413

        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        validated_events = []
        validation_errors = []

        for idx, item in enumerate(raw_events):
            if isinstance(item, dict):
                if 'client_ip' not in item or not item['client_ip']:
                    item['client_ip'] = client_ip
            try:
                evt = validate_event(item)
                validated_events.append(evt)
            except ValueError as err:
                validation_errors.append({"index": idx, "error": str(err)})

        if not validated_events and validation_errors:
            return jsonify({
                "error": "Validation Error",
                "message": "All events in batch failed schema validation.",
                "errors": validation_errors[:10]
            }), 400

        broker = get_kafka_service()
        ingested_count = broker.publish_batch(validated_events)

        return jsonify({
            "status": "accepted",
            "ingested_count": ingested_count,
            "rejected_count": len(validation_errors),
            "errors": validation_errors[:10] if validation_errors else [],
            "received_at": time.time()
        }), 202

    @app.route('/api/analytics/status', methods=['GET'])
    def analytics_status():
        """
        Returns real-time status, health, and throughput metrics of the telemetry message broker.
        """
        broker = get_kafka_service()
        return jsonify(broker.get_status()), 200

    # -------------------------------------------------------------
    # Synthetic Viewer Traffic Simulation Endpoints
    # -------------------------------------------------------------
    @app.route('/api/analytics/simulation/start', methods=['POST'])
    def start_simulation():
        """
        Starts the synthetic viewer traffic generator.
        """
        body = request.get_json(silent=True) or {}
        viewers = int(body.get('viewers', 100))
        duration = body.get('duration_seconds')
        if duration is not None:
            duration = int(duration)

        generator = get_traffic_generator()
        started = generator.start_simulation(num_viewers=viewers, duration_seconds=duration)
        if not started:
            return jsonify({
                "error": "Conflict",
                "message": "Traffic simulation is already active.",
                "status": generator.get_status()
            }), 409

        return jsonify({
            "status": "started",
            "message": f"Simulating {viewers} concurrent viewers.",
            "metrics": generator.get_status()
        }), 200

    @app.route('/api/analytics/simulation/stop', methods=['POST'])
    def stop_simulation():
        """
        Stops the synthetic viewer traffic generator.
        """
        generator = get_traffic_generator()
        stopped = generator.stop_simulation()
        return jsonify({
            "status": "stopped" if stopped else "not_running",
            "metrics": generator.get_status()
        }), 200

    @app.route('/api/analytics/simulation/status', methods=['GET'])
    def simulation_status():
        """
        Returns real-time status and throughput of the traffic generator.
        """
        generator = get_traffic_generator()
        return jsonify(generator.get_status()), 200

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"[*] Starting Video Pipeline API on {Config.HOST}:{Config.PORT} in {Config.ENV} mode...")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
