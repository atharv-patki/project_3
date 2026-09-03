import time
import queue
import logging
import threading
from collections import deque, defaultdict
from typing import Dict, Any, List, Optional

try:
    from backend.config import Config
    from backend.kafka_service import get_kafka_service
    from backend.database import DatabaseManager
except ImportError:
    from config import Config
    from kafka_service import get_kafka_service
    from database import DatabaseManager

logger = logging.getLogger(__name__)

class MetricsAggregator:
    """
    In-Memory Streaming Analytics Aggregator.
    Computes real-time sliding-window KPIs:
    - Active Concurrent Viewers (active in last 15s)
    - Average Buffer Health (seconds)
    - Rebuffer Stall Rate (QoS %)
    - Playback Quality Distribution (1080p, 720p, 480p)
    - Playback States (playing, paused, buffering, seeking)
    - Device Distribution (web, mobile, smart_tv, desktop)
    - Top Active Videos
    - Historical Time-Series trendline (last 60 data points)
    """
    def __init__(self, session_timeout_seconds: float = 15.0, window_seconds: float = 30.0, max_time_series_points: int = 60):
        self.session_timeout = session_timeout_seconds
        self.window_seconds = window_seconds
        self._lock = threading.Lock()

        # Session tracking: session_id -> { user_id, video_id, quality, buffer_health, state, device_type, watch_time_seconds, last_seen }
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

        # Sliding window of recent events for QoS & throughput: deque of (timestamp, state, buffer_health)
        self._window_events: deque = deque()

        # Global historical totals
        self._total_consumed = 0
        self._total_watch_time_seconds = 0.0

        # Time-series trend buffer: deque of snapshot points
        self._time_series: deque = deque(maxlen=max_time_series_points)
        self._last_point_time = 0

    def ingest_event(self, event: Any):
        """
        Process a single telemetry event into the real-time aggregation model.
        Supports both dict and PlaybackEvent dataclass instances.
        """
        if hasattr(event, "to_dict"):
            event = event.to_dict()
        elif hasattr(event, "__dict__"):
            event = event.__dict__

        now = time.time()
        session_id = event.get("session_id") or event.get("user_id")
        if not session_id:
            return

        with self._lock:
            self._total_consumed += 1
            watch_delta = max(0.0, float(event.get("watch_time_seconds", 0.0)))
            self._total_watch_time_seconds += min(watch_delta, 1.5)  # Cap delta to prevent jump spikes

            state = str(event.get("playback_state", "playing")).lower()
            quality = str(event.get("playback_quality", "720p")).lower()
            buffer_health = max(0.0, float(event.get("buffer_health", 0.0)))
            video_id = str(event.get("video_id", "unknown"))
            device_type = str(event.get("device_type", "web")).lower()

            # Update or register session
            self._active_sessions[session_id] = {
                "user_id": event.get("user_id", "unknown"),
                "video_id": video_id,
                "playback_quality": quality,
                "buffer_health": buffer_health,
                "playback_state": state,
                "device_type": device_type,
                "last_seen": now
            }

            # Append to sliding event window
            self._window_events.append((now, state, buffer_health))

    def prune_and_tick(self):
        """
        Remove expired sessions and prune events outside the sliding window.
        """
        now = time.time()
        with self._lock:
            # 1. Prune stale sessions
            cutoff = now - self.session_timeout
            stale_keys = [sid for sid, data in self._active_sessions.items() if data["last_seen"] < cutoff]
            for sid in stale_keys:
                del self._active_sessions[sid]

            # 2. Prune window events
            window_cutoff = now - self.window_seconds
            while self._window_events and self._window_events[0][0] < window_cutoff:
                self._window_events.popleft()

            # 3. Add to time series every ~1 second
            if now - self._last_point_time >= 1.0:
                self._last_point_time = now
                self._record_time_series_point(now)

    def _record_time_series_point(self, now: float):
        """Records an instantaneous snapshot point into the historical buffer."""
        active_count = len(self._active_sessions)
        
        # Calculate avg buffer health & stall rate across active sessions
        if active_count > 0:
            avg_buffer = sum(s["buffer_health"] for s in self._active_sessions.values()) / active_count
            buffering_sessions = sum(1 for s in self._active_sessions.values() if s["playback_state"] == "buffering")
            stall_rate = round((buffering_sessions / active_count) * 100, 1)
        else:
            avg_buffer = 0.0
            stall_rate = 0.0

        # Calculate throughput (events/sec in window)
        eps = round(len(self._window_events) / self.window_seconds, 1) if self.window_seconds > 0 else 0.0

        point = {
            "timestamp": now,
            "time_label": time.strftime("%H:%M:%S", time.localtime(now)),
            "active_viewers": active_count,
            "avg_buffer_health": round(avg_buffer, 1),
            "stall_rate": stall_rate,
            "events_per_sec": eps
        }
        self._time_series.append(point)

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Generates a comprehensive snapshot of real-time streaming KPIs.
        """
        self.prune_and_tick()
        now = time.time()

        with self._lock:
            active_count = len(self._active_sessions)
            
            # 1. Quality Breakdown
            qualities = defaultdict(int)
            # 2. State Breakdown
            states = defaultdict(int)
            # 3. Device Breakdown
            devices = defaultdict(int)
            # 4. Top Videos
            videos = defaultdict(int)
            
            total_buffer = 0.0
            for s in self._active_sessions.values():
                qualities[s["playback_quality"]] += 1
                states[s["playback_state"]] += 1
                devices[s["device_type"]] += 1
                videos[s["video_id"]] += 1
                total_buffer += s["buffer_health"]

            avg_buffer = round(total_buffer / active_count, 1) if active_count > 0 else 0.0

            # 5. QoS Rebuffer Stall Rate
            buffering_count = states.get("buffering", 0)
            stall_rate = round((buffering_count / active_count) * 100, 1) if active_count > 0 else 0.0

            # 6. Top videos ranking
            top_videos = sorted([{"video_id": vid, "viewers": cnt} for vid, cnt in videos.items()], key=lambda x: x["viewers"], reverse=True)[:5]

            # 7. Velocity (Events per second in current window)
            eps = round(len(self._window_events) / self.window_seconds, 1) if self.window_seconds > 0 else 0.0

            return {
                "timestamp": now,
                "active_concurrent_viewers": active_count,
                "avg_buffer_health_seconds": avg_buffer,
                "rebuffer_stall_rate_percent": stall_rate,
                "events_per_second": eps,
                "total_events_consumed": self._total_consumed,
                "total_watch_time_minutes": round(self._total_watch_time_seconds / 60.0, 1),
                "quality_distribution": dict(qualities),
                "state_distribution": dict(states),
                "device_distribution": dict(devices),
                "top_videos": top_videos,
                "time_series": list(self._time_series)
            }


class AnalyticsConsumer:
    """
    Background Stream Consumer Thread.
    Continuously pulls events from the message broker, feeds the real-time aggregator,
    and asynchronously buffers and persists events into the SQLite/PostgreSQL warehouse.
    """
    _instance: Optional['AnalyticsConsumer'] = None
    _lock = threading.Lock()

    def __init__(self, batch_flush_threshold: int = 150, flush_interval_seconds: float = 1.0):
        self.aggregator = MetricsAggregator()
        self.is_running = False
        self.batch_flush_threshold = batch_flush_threshold
        self.flush_interval_seconds = flush_interval_seconds
        
        self._persistence_buffer: List[Any] = []
        self._persistence_lock = threading.Lock()
        self._last_flush_time = time.time()
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @classmethod
    def get_instance(cls) -> 'AnalyticsConsumer':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = AnalyticsConsumer()
        return cls._instance

    def start(self):
        """Start the background consumer thread."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._consume_loop, daemon=True, name="AnalyticsConsumerThread")
            self._thread.start()
            print("[+] Analytics Stream Consumer & Warehouse Persistence worker started.")

    def stop(self):
        """Stop the background consumer and flush pending telemetry to database."""
        with self._lock:
            if not self.is_running:
                return
            self._stop_event.set()
            self.is_running = False
            self._flush_persistence_buffer()

    def _flush_persistence_buffer(self):
        """Flushes buffered telemetry events to the database warehouse."""
        with self._persistence_lock:
            if not self._persistence_buffer:
                return
            events_to_write = list(self._persistence_buffer)
            self._persistence_buffer.clear()
            self._last_flush_time = time.time()

        try:
            DatabaseManager.batch_insert_events(events_to_write)
        except Exception as e:
            logger.error(f"Failed to persist telemetry batch to warehouse: {e}")

    def _consume_loop(self):
        """Worker loop reading from broker queue and flushing to database."""
        broker = get_kafka_service()
        channel = broker.get_consumer_channel()

        while not self._stop_event.is_set():
            try:
                # Read event from queue with timeout
                event = channel.get(timeout=0.2)
                if event is not None:
                    # 1. Real-time in-memory KPI aggregation
                    self.aggregator.ingest_event(event)
                    
                    # 2. Add to batch persistence buffer
                    with self._persistence_lock:
                        self._persistence_buffer.append(event)
                        should_flush = (
                            len(self._persistence_buffer) >= self.batch_flush_threshold or
                            (time.time() - self._last_flush_time) >= self.flush_interval_seconds
                        )
                    
                    if should_flush:
                        self._flush_persistence_buffer()

                    channel.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error consuming analytics event: {e}")

            # Check periodic timer flush
            with self._persistence_lock:
                timer_flush = (
                    bool(self._persistence_buffer) and
                    (time.time() - self._last_flush_time) >= self.flush_interval_seconds
                )
            if timer_flush:
                self._flush_persistence_buffer()

            # Maintain time series ticks periodically
            self.aggregator.prune_and_tick()

        # Final cleanup flush on exit
        self._flush_persistence_buffer()

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """Expose current real-time streaming KPIs."""
        return self.aggregator.get_snapshot()


def get_analytics_consumer() -> AnalyticsConsumer:
    return AnalyticsConsumer.get_instance()
