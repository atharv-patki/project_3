import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

VALID_PLAYBACK_STATES = {"playing", "paused", "buffering", "seeking", "ended"}
VALID_PLAYBACK_QUALITIES = {"1080p", "720p", "480p", "360p", "240p", "auto", "original"}
VALID_DEVICE_TYPES = {"web", "mobile", "smart_tv", "desktop", "unknown"}

@dataclass
class PlaybackEvent:
    user_id: str
    video_id: str
    session_id: str
    timestamp: float
    watch_time_seconds: float
    playback_quality: str
    buffer_health: float
    playback_state: str
    device_type: str = "web"
    bitrate_kbps: int = 0
    client_ip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlaybackEvent':
        """Validate and construct a PlaybackEvent from a raw dictionary."""
        return validate_event(data)


def validate_event(data: Any) -> PlaybackEvent:
    """
    Validates a raw dictionary against the PlaybackEvent telemetry schema.
    Raises ValueError with a descriptive error message if invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Telemetry payload must be a JSON object (dictionary).")

    # 1. Validate required string fields
    user_id = data.get("user_id")
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("Field 'user_id' is required and must be a non-empty string.")

    video_id = data.get("video_id")
    if not video_id or not isinstance(video_id, str) or not video_id.strip():
        raise ValueError("Field 'video_id' is required and must be a non-empty string.")

    # 2. Session ID (optional in payload, auto-generated if missing)
    session_id = data.get("session_id")
    if not session_id or not isinstance(session_id, str):
        session_id = str(uuid.uuid4())

    # 3. Timestamp validation (defaults to current time if missing)
    raw_timestamp = data.get("timestamp")
    if raw_timestamp is None:
        timestamp = time.time()
    else:
        try:
            timestamp = float(raw_timestamp)
        except (ValueError, TypeError):
            raise ValueError("Field 'timestamp' must be a numeric timestamp (epoch seconds).")

    # 4. Watch Time validation (seconds watched in current session/heartbeat)
    raw_watch_time = data.get("watch_time_seconds")
    if raw_watch_time is None:
        raise ValueError("Field 'watch_time_seconds' is required.")
    try:
        watch_time_seconds = float(raw_watch_time)
        if watch_time_seconds < 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Field 'watch_time_seconds' must be a non-negative number.")

    # 5. Playback Quality validation
    playback_quality = data.get("playback_quality")
    if not playback_quality or not isinstance(playback_quality, str):
        raise ValueError(f"Field 'playback_quality' is required. Allowed: {sorted(list(VALID_PLAYBACK_QUALITIES))}")
    playback_quality_clean = playback_quality.strip().lower()
    if playback_quality_clean not in VALID_PLAYBACK_QUALITIES:
        raise ValueError(
            f"Invalid 'playback_quality' '{playback_quality}'. Allowed values: {sorted(list(VALID_PLAYBACK_QUALITIES))}"
        )

    # 6. Buffer Health validation (seconds of buffered video ahead of current playhead)
    raw_buffer_health = data.get("buffer_health")
    if raw_buffer_health is None:
        raise ValueError("Field 'buffer_health' is required.")
    try:
        buffer_health = float(raw_buffer_health)
        if buffer_health < 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Field 'buffer_health' must be a non-negative number (seconds of buffer).")

    # 7. Playback State validation
    playback_state = data.get("playback_state")
    if not playback_state or not isinstance(playback_state, str):
        raise ValueError(f"Field 'playback_state' is required. Allowed: {sorted(list(VALID_PLAYBACK_STATES))}")
    playback_state_clean = playback_state.strip().lower()
    if playback_state_clean not in VALID_PLAYBACK_STATES:
        raise ValueError(
            f"Invalid 'playback_state' '{playback_state}'. Allowed values: {sorted(list(VALID_PLAYBACK_STATES))}"
        )

    # 8. Optional device_type & bitrate
    device_type = str(data.get("device_type", "web")).strip().lower()
    if device_type not in VALID_DEVICE_TYPES:
        device_type = "unknown"

    raw_bitrate = data.get("bitrate_kbps", 0)
    try:
        bitrate_kbps = max(0, int(raw_bitrate))
    except (ValueError, TypeError):
        bitrate_kbps = 0

    client_ip = data.get("client_ip")
    if client_ip is not None:
        client_ip = str(client_ip).strip()

    return PlaybackEvent(
        user_id=user_id.strip(),
        video_id=video_id.strip(),
        session_id=session_id.strip(),
        timestamp=timestamp,
        watch_time_seconds=watch_time_seconds,
        playback_quality=playback_quality_clean,
        buffer_health=buffer_health,
        playback_state=playback_state_clean,
        device_type=device_type,
        bitrate_kbps=bitrate_kbps,
        client_ip=client_ip
    )
