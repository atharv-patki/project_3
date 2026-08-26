import time
import queue
import threading
from database import DatabaseManager

# Thread-safe worker queue for video transcoding jobs
transcode_queue = queue.Queue()
_worker_thread = None
_lock = threading.Lock()

def _transcode_worker_loop():
    """Background loop that executes video jobs sequentially from the queue."""
    print("[*] Transcoding background worker thread started.")
    
    while True:
        try:
            # Block until a job is available in the queue
            video_id = transcode_queue.get()
            print(f"[*] Worker picked up video '{video_id}' from queue.")
            
            # 1. Transition state to 'processing'
            try:
                DatabaseManager.update_transcode_metadata(
                    video_id,
                    transcode_status='processing',
                    transcode_progress=0.0
                )
            except Exception as e:
                print(f"[-] Worker database error: {e}")
            
            # 2. Simulate transcode operation (Day 8 placeholder)
            # Simulates progress from 0% -> 50% -> 100%
            time.sleep(2)
            try:
                DatabaseManager.update_transcode_metadata(video_id, transcode_progress=50.0)
                print(f"[*] Job '{video_id}' progress updated: 50.0%")
            except Exception as e:
                print(f"[-] Worker database error: {e}")
                
            time.sleep(2)
            
            # 3. Complete job and set dummy resolution paths
            dummy_720p = f"storage/mock_cloud/{video_id}_720p.mp4"
            dummy_480p = f"storage/mock_cloud/{video_id}_480p.mp4"
            dummy_thumb = f"storage/mock_cloud/{video_id}_thumb.jpg"
            
            try:
                DatabaseManager.update_transcode_metadata(
                    video_id,
                    transcode_status='completed',
                    transcode_progress=100.0,
                    path_720p=dummy_720p,
                    path_480p=dummy_480p,
                    path_thumbnail=dummy_thumb
                )
                print(f"[+] Job '{video_id}' transcoding complete. Status updated to 'completed'.")
            except Exception as e:
                print(f"[-] Worker database error: {e}")

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
