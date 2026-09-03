import os
import sys
import time
import uuid
import random
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    from backend.analytics_schema import PlaybackEvent, validate_event
    from backend.kafka_service import get_kafka_service
    from backend.database import DatabaseManager
except ImportError:
    from analytics_schema import PlaybackEvent, validate_event
    from kafka_service import get_kafka_service
    from database import DatabaseManager

logger = logging.getLogger(__name__)

DEVICE_TYPES = ["web", "mobile", "smart_tv", "desktop"]
QUALITIES = ["1080p", "720p", "480p"]

class VirtualViewer:
    """
    Simulates an individual OTT viewer with realistic playback dynamics:
    ABR resolution adaptation, buffer fluctuations, pausing, scrubbing, and dropouts.
    """
    def __init__(self, viewer_id: int, video_id: Optional[str] = None):
        self.viewer_id = viewer_id
        self.user_id = f"sim_user_{viewer_id:04d}"
        self.video_id = video_id or "vid_demo_sample"
        self.session_id = f"sess_sim_{uuid.uuid4().hex[:10]}"
        self.device_type = random.choice(DEVICE_TYPES)
        self.quality = random.choice(QUALITIES)
        self.watch_time = round(random.uniform(0.0, 120.0), 2)
        self.buffer_health = round(random.uniform(5.0, 25.0), 2)
        self.state = "playing"
        self.bitrate = 4500 if self.quality == "1080p" else (2500 if self.quality == "720p" else 1000)

    def tick(self) -> Dict[str, Any]:
        """
        Advance simulated playback state by 1 second and return a telemetry event payload.
        """
        # 1. State transitions with realistic probabilities
        rand = random.random()
        if self.state == "playing":
            if rand < 0.04:
                self.state = "paused"
            elif rand < 0.07:
                self.state = "buffering"
            elif rand < 0.09:
                self.state = "seeking"
                self.watch_time = max(0.0, self.watch_time + random.uniform(-30.0, 60.0))
        elif self.state == "paused":
            if rand < 0.35:
                self.state = "playing"
        elif self.state == "buffering":
            if rand < 0.50:
                self.state = "playing"
                self.buffer_health = max(2.0, self.buffer_health + 4.0)
        elif self.state == "seeking":
            self.state = "playing"

        # 2. Advance watch time & buffer dynamics
        if self.state == "playing":
            self.watch_time = round(self.watch_time + 1.0, 2)
            # Buffer fluctuates around consumption vs download
            buffer_delta = random.uniform(-1.2, 1.5)
            self.buffer_health = max(0.0, round(self.buffer_health + buffer_delta, 2))
            
            # Adaptive Bitrate (ABR) response to low buffer
            if self.buffer_health < 3.0 and self.quality != "480p":
                self.quality = "480p"
                self.bitrate = 1000
            elif self.buffer_health > 15.0 and self.quality == "480p":
                self.quality = "720p"
                self.bitrate = 2500

        elif self.state == "buffering":
            # In buffering state, buffer is near zero
            self.buffer_health = max(0.0, round(self.buffer_health - 0.5, 2))
        elif self.state == "paused":
            # In paused state, buffer fills up gradually
            self.buffer_health = min(35.0, round(self.buffer_health + 0.8, 2))

        return {
            "user_id": self.user_id,
            "video_id": self.video_id,
            "session_id": self.session_id,
            "timestamp": time.time(),
            "watch_time_seconds": self.watch_time,
            "playback_quality": self.quality,
            "buffer_health": self.buffer_health,
            "playback_state": self.state,
            "device_type": self.device_type,
            "bitrate_kbps": self.bitrate,
            "client_ip": f"10.0.{random.randint(1, 254)}.{random.randint(1, 254)}"
        }


class TrafficGenerator:
    """
    Multi-threaded synthetic traffic generator engine.
    Orchestrates hundreds of concurrent virtual viewers, emitting batched telemetry heartbeats every second.
    """
    _instance: Optional['TrafficGenerator'] = None
    _lock = threading.Lock()

    def __init__(self):
        self.is_running = False
        self.viewers: List[VirtualViewer] = []
        self.num_viewers = 0
        self.duration_seconds: Optional[int] = None
        self.total_generated_events = 0
        self.start_time: Optional[float] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stats_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'TrafficGenerator':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = TrafficGenerator()
        return cls._instance

    def _get_catalog_video_ids(self) -> List[str]:
        """Fetch available video IDs from SQLite registry, or fallback to default IDs."""
        try:
            uploads = DatabaseManager.list_uploads()
            ids = [u['video_id'] for u in uploads if u.get('transcode_status') == 'completed' or u.get('status') == 'completed']
            if ids:
                return ids
        except Exception:
            pass
        return ["vid_demo_matrix_01", "vid_demo_inception_02", "vid_demo_interstellar_03"]

    def start_simulation(self, num_viewers: int = 100, duration_seconds: Optional[int] = None) -> bool:
        """
        Start concurrent viewer simulation.
        """
        with self._lock:
            if self.is_running:
                logger.warning("Simulation is already running.")
                return False

            self.num_viewers = max(1, min(num_viewers, 2000))
            self.duration_seconds = duration_seconds
            self.total_generated_events = 0
            self.start_time = time.time()
            self._stop_event.clear()
            self.is_running = True

            # Populate virtual viewers
            video_ids = self._get_catalog_video_ids()
            self.viewers = [
                VirtualViewer(viewer_id=i + 1, video_id=random.choice(video_ids))
                for i in range(self.num_viewers)
            ]

            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TrafficGeneratorThread")
            self._thread.start()
            print(f"[+] Started Traffic Generator with {self.num_viewers} concurrent virtual viewers.")
            return True

    def stop_simulation(self) -> bool:
        """
        Stop the active viewer simulation.
        """
        with self._lock:
            if not self.is_running:
                return False

            self._stop_event.set()
            self.is_running = False
            print("[*] Stopping Traffic Generator engine...")
            return True

    def _run_loop(self):
        """Worker loop executing 1-second telemetry generation ticks."""
        broker = get_kafka_service()
        tick_interval = 1.0

        while not self._stop_event.is_set():
            loop_start = time.perf_counter()

            # Check duration expiry
            if self.duration_seconds and (time.time() - self.start_time) >= self.duration_seconds:
                print(f"[*] Simulation reached duration limit of {self.duration_seconds}s. Stopping.")
                break

            # 1. Generate 1 tick for each virtual viewer
            batch = []
            for viewer in self.viewers:
                try:
                    event_dict = viewer.tick()
                    batch.append(event_dict)
                except Exception as e:
                    logger.error(f"Error ticking viewer {viewer.viewer_id}: {e}")

            # 2. Publish batch directly to Kafka/in-memory broker
            if batch:
                published = broker.publish_batch(batch)
                with self._stats_lock:
                    self.total_generated_events += published

            # 3. Sleep to maintain ~1 tick/sec cadence
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0.01, tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

        self.is_running = False
        print(f"[+] Traffic Generator loop exited. Total events emitted: {self.total_generated_events}")

    def get_status(self) -> Dict[str, Any]:
        """Returns real-time status and throughput metrics of the generator."""
        with self._stats_lock:
            total_events = self.total_generated_events
            running = self.is_running
            start = self.start_time

        elapsed = (time.time() - start) if (running and start) else 0.0
        eps = round(total_events / elapsed, 1) if elapsed > 0 else 0.0

        return {
            "running": running,
            "active_viewers": len(self.viewers) if running else 0,
            "total_generated_events": total_events,
            "elapsed_seconds": round(elapsed, 1),
            "events_per_second": eps
        }


def get_traffic_generator() -> TrafficGenerator:
    return TrafficGenerator.get_instance()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AetherStream Synthetic Traffic Generator")
    parser.add_argument("--viewers", type=int, default=50, help="Number of concurrent viewers")
    parser.add_argument("--duration", type=int, default=15, help="Simulation duration in seconds")
    args = parser.parse_args()

    print(f"Starting standalone Traffic Generator: {args.viewers} viewers for {args.duration}s...")
    gen = get_traffic_generator()
    gen.start_simulation(num_viewers=args.viewers, duration_seconds=args.duration)
    
    try:
        while gen.is_running:
            time.sleep(1)
            st = gen.get_status()
            print(f"[{st['elapsed_seconds']}s] Active Viewers: {st['active_viewers']} | Events: {st['total_generated_events']} ({st['events_per_second']} eps)")
    except KeyboardInterrupt:
        gen.stop_simulation()
    print("Simulation finished.")
