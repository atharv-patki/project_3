import sqlite3
from pathlib import Path
from config import Config

class DatabaseManager:
    @classmethod
    def get_connection(cls) -> sqlite3.Connection:
        """Establish a connection to the SQLite database."""
        conn = sqlite3.connect(Config.DB_PATH)
        # Enable dictionary-like access to rows
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def init_db(cls):
        """Initialize the database tables if they do not exist."""
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    video_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            print(f"[+] Database initialized at: {Config.DB_PATH}")
        except Exception as e:
            print(f"[-] Failed to initialize database: {e}")
            raise e
        finally:
            conn.close()

    @classmethod
    def create_upload_session(cls, video_id: str, filename: str, file_size: int, total_chunks: int) -> dict:
        """Create a new upload session entry in the database."""
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO uploads (video_id, filename, file_size, total_chunks, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (video_id, filename, file_size, total_chunks, "initiated")
            )
            conn.commit()
            return {
                "video_id": video_id,
                "filename": filename,
                "file_size": file_size,
                "total_chunks": total_chunks,
                "status": "initiated"
            }
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Error creating upload session in database: {e}")
        finally:
            conn.close()

    @classmethod
    def update_status(cls, video_id: str, status: str):
        """Update the status of an upload session."""
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE uploads SET status = ? WHERE video_id = ?",
                (status, video_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Error updating status for video {video_id}: {e}")
        finally:
            conn.close()

    @classmethod
    def get_upload_session(cls, video_id: str) -> dict:
        """Fetch upload session details for a given video_id."""
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM uploads WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()
