import os
import time
import shutil
import threading
from pathlib import Path
from config import Config
from database import DatabaseManager

# Magic byte dictionary for common video formats
VIDEO_MAGIC_BYTES = {
    '.mp4': [b'ftyp'],  # Offset 4-8
    '.mkv': [b'\x1a\x45\xdf\xa3'],  # Offset 0-4
    '.avi': [b'RIFF', b'AVI '],  # Offset 0-4 RIFF, 8-12 AVI
    '.mov': [b'ftyp', b'moov'],  # Offset 4-8
    '.wmv': [b'\x30\x26\xB2\x75\x8E\x66\xCF\x11']  # Offset 0-8 (ASF header)
}

def verify_file_signature(chunk_data: bytes, filename: str) -> bool:
    """
    Verify if the binary content matches the expected file extension.
    Only checks for chunk index 0 since that contains the file header.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_MAGIC_BYTES:
        return False

    magic = VIDEO_MAGIC_BYTES[suffix]
    
    if len(chunk_data) < 12:
        return False
        
    if suffix == '.mp4' or suffix == '.mov':
        # check ftyp signature at bytes 4 to 8
        header = chunk_data[4:8]
        return any(sig in header for sig in magic)
        
    elif suffix == '.mkv':
        # EBML header at start
        header = chunk_data[0:4]
        return any(header.startswith(sig) for sig in magic)
        
    elif suffix == '.avi':
        # RIFF header at start and AVI at byte 8
        riff = chunk_data[0:4]
        avi = chunk_data[8:12]
        return riff == b'RIFF' and avi == b'AVI '
        
    elif suffix == '.wmv':
        # GUID for ASF header
        header = chunk_data[0:8]
        return any(header.startswith(sig) for sig in magic)

    return False


class CleanupWorker:
    def __init__(self, expiry_seconds: int = 7200, check_interval_seconds: int = 600):
        self.expiry_seconds = expiry_seconds
        self.check_interval_seconds = check_interval_seconds
        self.running = False
        self._thread = None

    def start(self):
        """Start the background cleanup worker."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_cleanup_loop, daemon=True)
        self._thread.start()
        print(f"[+] Background cleanup worker started (Interval: {self.check_interval_seconds}s, Expiry: {self.expiry_seconds}s)")

    def _run_cleanup_loop(self):
        while self.running:
            try:
                self.cleanup_expired_uploads()
            except Exception as e:
                print(f"[-] Error in background cleanup worker: {e}")
            time.sleep(self.check_interval_seconds)

    def cleanup_expired_uploads(self):
        """Scan the temp directory for expired folders and update database statuses."""
        if not Config.UPLOAD_TEMP_DIR.exists():
            return

        now = time.time()
        for item in Config.UPLOAD_TEMP_DIR.iterdir():
            if item.is_dir():
                video_id = item.name
                # Get last modification time of the folder
                mtime = item.stat().st_mtime
                age = now - mtime
                
                if age > self.expiry_seconds:
                    print(f"[*] Found expired upload session: {video_id} (Age: {round(age)}s). Cleaning up...")
                    try:
                        # Clean up disk
                        shutil.rmtree(item)
                        # Clean up/update DB status to failed or expired if currently active
                        session = DatabaseManager.get_upload_session(video_id)
                        if session and session['status'] not in ('completed', 'failed'):
                            DatabaseManager.update_status(video_id, 'failed')
                            print(f"[+] Updated status for expired video {video_id} to failed.")
                    except Exception as e:
                        print(f"[-] Error cleaning up expired upload session {video_id}: {e}")
