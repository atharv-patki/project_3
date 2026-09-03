import time
import queue
import threading
import sys
import traceback
from pathlib import Path

try:
    from database import DatabaseManager
    from transcoder_service import TranscoderService
    from config import Config
except ImportError:
    from backend.database import DatabaseManager
    from backend.transcoder_service import TranscoderService
    from backend.config import Config

# Thread-safe worker queue for video transcoding jobs
transcode_queue = queue.Queue()
_worker_thread = None
_lock = threading.Lock()

def _transcode_worker_loop():
    """Background loop that executes video jobs sequentially using FFmpeg."""
    print("[*] Transcoding background worker thread started.")
    
    while True:
        try:
            # Block until a job is available in the queue
            video_id = transcode_queue.get()
            print(f"[*] Worker picked up video '{video_id}' from queue.")
            
            # Fetch video record from DB
            record = DatabaseManager.get_upload_session(video_id)
            if not record:
                print(f"[-] Record not found for video: {video_id}")
                transcode_queue.task_done()
                continue
                
            from config import Config
            filename = record['filename']
            ext = Path(filename).suffix
            input_path = Path(Config.UPLOAD_FINAL_DIR) / f"{video_id}{ext}"
            if not input_path.exists():
                print(f"[-] Input file does not exist: {input_path}")
                DatabaseManager.update_transcode_metadata(
                    video_id,
                    transcode_status='failed',
                    transcode_progress=0.0
                )
                transcode_queue.task_done()
                continue

            # 1. Update status to 'processing'
            try:
                DatabaseManager.update_transcode_metadata(
                    video_id,
                    transcode_status='processing',
                    transcode_progress=0.0
                )
            except Exception as e:
                print(f"[-] Worker database error: {e}")

            # Define output paths
            output_dir = input_path.parent
            path_720p = output_dir / f"{video_id}_720p.mp4"
            path_480p = output_dir / f"{video_id}_480p.mp4"
            path_thumb = output_dir / f"{video_id}_thumb.jpg"
            
            try:
                # 2. Get video duration using ffprobe
                print(f"[*] Probing duration for '{video_id}'...")
                duration = TranscoderService.get_video_duration(str(input_path))
                print(f"[+] Duration: {duration} seconds")
                
                # 3. Transcode 720p (corresponds to 0% -> 50% of overall progress)
                print(f"[*] Starting 720p transcode for '{video_id}'...")
                def progress_720p(percent):
                    overall = percent * 0.5
                    DatabaseManager.update_transcode_metadata(video_id, transcode_progress=overall)
                    
                TranscoderService.transcode_to_720p(
                    str(input_path),
                    str(path_720p),
                    duration=duration,
                    progress_callback=progress_720p
                )
                print(f"[+] 720p transcode finished for '{video_id}'.")
                
                # 4. Transcode 480p (corresponds to 50% -> 100% of overall progress)
                print(f"[*] Starting 480p transcode for '{video_id}'...")
                def progress_480p(percent):
                    overall = 50.0 + (percent * 0.5)
                    # Cap at 99.9% until thumbnail is extracted
                    overall = min(99.9, overall)
                    DatabaseManager.update_transcode_metadata(video_id, transcode_progress=overall)
                    
                TranscoderService.transcode_to_480p(
                    str(input_path),
                    str(path_480p),
                    duration=duration,
                    progress_callback=progress_480p
                )
                print(f"[+] 480p transcode finished for '{video_id}'.")
                
                # 5. Extract Thumbnail at 5-second mark
                print(f"[*] Extracting thumbnail at 5s mark for '{video_id}'...")
                TranscoderService.extract_thumbnail(str(input_path), str(path_thumb))
                print(f"[+] Thumbnail extracted for '{video_id}'.")
                
                # 6. Complete Job and register paths
                DatabaseManager.update_transcode_metadata(
                    video_id,
                    transcode_status='completed',
                    transcode_progress=100.0,
                    path_720p=str(path_720p),
                    path_480p=str(path_480p),
                    path_thumbnail=str(path_thumb)
                )
                print(f"[+] Job '{video_id}' transcoding complete. Status set to 'completed'.")
                
            except Exception as err:
                print(f"[-] Transcoding failed for '{video_id}': {err}")
                traceback.print_exc()
                try:
                    DatabaseManager.update_transcode_metadata(
                        video_id,
                        transcode_status='failed',
                        transcode_progress=0.0
                    )
                except Exception as db_err:
                    print(f"[-] Failed to update failure state in DB: {db_err}")

            # Notify queue that the task is complete
            transcode_queue.task_done()
            
        except Exception as e:
            print(f"[-] Error in worker thread: {e}")
            time.sleep(1)

def start_worker():
    """Initialize and start the background worker thread if not already running."""
    global _worker_thread
    with _lock:
        if _worker_thread is None:
            _worker_thread = threading.Thread(target=_transcode_worker_loop, daemon=True)
            _worker_thread.start()
            print("[+] Transcoding background worker process initialized.")

def queue_transcode_job(video_id: str):
    """Enqueue a video transcoding task and set its initial status to 'pending'."""
    # Ensure worker is started
    start_worker()
    
    # 1. Update status to pending
    try:
        DatabaseManager.update_transcode_metadata(
            video_id,
            transcode_status='pending',
            transcode_progress=0.0
        )
    except Exception as e:
        print(f"[-] Error updating database state for queued video '{video_id}': {e}")
        raise e
        
    # 2. Add to queue
    transcode_queue.put(video_id)
    print(f"[+] Enqueued transcode task for video '{video_id}'. Current Queue Size: {transcode_queue.qsize()}")
