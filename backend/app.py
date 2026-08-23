import os
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config

def create_app():
    # Initialize directory structure and configure configuration paths
    Config.init_app()

    app = Flask(__name__)
    
    # Configure Flask limits
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

    # Enable Cross-Origin Resource Sharing (CORS)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.route('/api/health', methods=['GET'])
    def health_check():
        # Verify writable storage status
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

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"[*] Starting Video Pipeline API on {Config.HOST}:{Config.PORT} in {Config.ENV} mode...")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
