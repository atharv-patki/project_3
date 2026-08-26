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

            # Dynamic migrations for transcoding metrics
            cursor.execute("PRAGMA table_info(uploads)")
            columns = [row[1] for row in cursor.fetchall()]
            
            migrations = {
                "transcode_status": "ALTER TABLE uploads ADD COLUMN transcode_status TEXT DEFAULT 'none'",
                "transcode_progress": "ALTER TABLE uploads ADD COLUMN transcode_progress REAL DEFAULT 0.0",
                "path_720p": "ALTER TABLE uploads ADD COLUMN path_720p TEXT",
                "path_480p": "ALTER TABLE uploads ADD COLUMN path_480p TEXT",
                "path_thumbnail": "ALTER TABLE uploads ADD COLUMN path_thumbnail TEXT"
            }
            
            for col, sql in migrations.items():
                if col not in columns:
                    print(f"[*] Migrating database: Adding column '{col}'...")
                    cursor.execute(sql)
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

    @classmethod
    def list_uploads(cls) -> list:
        """Fetch all upload sessions from the database ordered by creation date."""
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM uploads ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @classmethod
    def update_transcode_metadata(cls, video_id: str, **kwargs):
        """Update selective transcode metadata fields in database."""
        if not kwargs:
            return
        
        valid_cols = {'transcode_status', 'transcode_progress', 'path_720p', 'path_480p', 'path_thumbnail'}
        updates = []
        params = []
        
        for k, v in kwargs.items():
            if k in valid_cols:
                updates.append(f"{k} = ?")
                params.append(v)
                
        if not updates:
            return
            
        params.append(video_id)
        query = f"UPDATE uploads SET {', '.join(updates)} WHERE video_id = ?"
        
        conn = cls.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Error updating transcode metadata for {video_id}: {e}")
        finally:
            conn.close()
