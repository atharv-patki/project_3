import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve project root path
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from the project root .env file
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    # Flask configuration
    ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = ENV == 'development'
    PORT = int(os.getenv('PORT', 5000))
    HOST = os.getenv('HOST', '127.0.0.1')
    FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')

    # Kafka & Analytics Stream configuration
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_TOPIC_EVENTS = os.getenv('KAFKA_TOPIC_EVENTS', 'playback-events')

    # Storage paths
    # Resolve relative paths relative to BASE_DIR, keep absolute paths intact
    _temp_dir = os.getenv('UPLOAD_TEMP_DIR', 'storage/temp')
    _final_dir = os.getenv('UPLOAD_FINAL_DIR', 'storage/mock_cloud')

    UPLOAD_TEMP_DIR = BASE_DIR / _temp_dir if not os.path.isabs(_temp_dir) else Path(_temp_dir)
    UPLOAD_FINAL_DIR = BASE_DIR / _final_dir if not os.path.isabs(_final_dir) else Path(_final_dir)
    DB_PATH = BASE_DIR / os.getenv('DB_PATH', 'storage/metadata.db')

    # Size constraints
    # Default Max: 500MB
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 524288000))
    # Default Chunk: 5MB
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 5242880))

    @classmethod
    def init_app(cls):
        """Ensure all required storage directories exist."""
        cls.UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.UPLOAD_FINAL_DIR.mkdir(parents=True, exist_ok=True)
        # Ensure database directory exists
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[*] Storage initialized:")
        print(f"    Temp directory:  {cls.UPLOAD_TEMP_DIR}")
        print(f"    Final directory: {cls.UPLOAD_FINAL_DIR}")
        print(f"    Database path:   {cls.DB_PATH}")
