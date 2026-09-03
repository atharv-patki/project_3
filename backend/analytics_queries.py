import time
from typing import Dict, Any, List, Optional

try:
    from database import DatabaseManager
except ImportError:
    from backend.database import DatabaseManager

class AnalyticsQueries:
    """
    SQL Analytical Query Engine for the AetherStream Telemetry Warehouse.
    Provides fast, indexed aggregations across time windows, devices, resolutions, and video assets.
    """

    @classmethod
    def get_historical_summary(
        cls,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        video_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates fleet-wide aggregate streaming KPIs over an optional time window and video filter.
        """
        conditions = []
        params = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if video_id:
            conditions.append("video_id = ?")
            params.append(video_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT
                COUNT(*) AS total_events,
                COUNT(DISTINCT user_id) AS unique_viewers,
                COUNT(DISTINCT session_id) AS unique_sessions,
                COALESCE(SUM(watch_time_seconds), 0.0) AS total_watch_time_seconds,
                COALESCE(AVG(buffer_health), 0.0) AS avg_buffer_health_seconds,
                COALESCE(AVG(bitrate_kbps), 0.0) AS avg_bitrate_kbps,
                COALESCE(SUM(CASE WHEN playback_state = 'buffering' THEN 1 ELSE 0 END), 0) AS stall_events
            FROM telemetry_events
            {where_clause}
        """

        conn = DatabaseManager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()

            total_events = row['total_events'] or 0
            stall_events = row['stall_events'] or 0
            stall_rate = round((stall_events / total_events * 100.0), 2) if total_events > 0 else 0.0
            total_watch_hours = round(row['total_watch_time_seconds'] / 3600.0, 2)

            return {
                "total_events": total_events,
                "unique_viewers": row['unique_viewers'] or 0,
                "unique_sessions": row['unique_sessions'] or 0,
                "total_watch_time_hours": total_watch_hours,
                "total_watch_time_minutes": round(row['total_watch_time_seconds'] / 60.0, 1),
                "avg_buffer_health_seconds": round(row['avg_buffer_health_seconds'], 2),
                "avg_bitrate_kbps": round(row['avg_bitrate_kbps'], 1),
                "rebuffer_stall_rate_percent": stall_rate,
                "start_time": start_time,
                "end_time": end_time,
                "video_id": video_id
            }
        finally:
            conn.close()

    @classmethod
    def get_historical_timeseries(
        cls,
        interval_seconds: int = 60,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        video_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Aggregates telemetry into time-bucketed trend points for charting historical QoS waves.
        """
        interval = max(5, int(interval_seconds))
        conditions = []
        params = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if video_id:
            conditions.append("video_id = ?")
            params.append(video_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Group by bucket timestamp
        query = f"""
            SELECT
                CAST(timestamp / {interval} AS INTEGER) * {interval} AS bucket_time,
                COUNT(*) AS event_count,
                COUNT(DISTINCT user_id) AS active_viewers,
                COALESCE(AVG(buffer_health), 0.0) AS avg_buffer_health,
                COALESCE(AVG(bitrate_kbps), 0.0) AS avg_bitrate,
                COALESCE(SUM(CASE WHEN playback_state = 'buffering' THEN 1 ELSE 0 END), 0) AS stall_count
            FROM telemetry_events
            {where_clause}
            GROUP BY bucket_time
            ORDER BY bucket_time ASC
        """

        conn = DatabaseManager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            result = []
            for r in rows:
                b_time = r['bucket_time']
                ev_cnt = r['event_count']
                stalls = r['stall_count']
                stall_pct = round((stalls / ev_cnt * 100.0), 2) if ev_cnt > 0 else 0.0
                
                result.append({
                    "timestamp": b_time,
                    "time_label": time.strftime("%H:%M:%S", time.localtime(b_time)),
                    "event_count": ev_cnt,
                    "active_viewers": r['active_viewers'],
                    "avg_buffer_health": round(r['avg_buffer_health'], 2),
                    "avg_bitrate_kbps": round(r['avg_bitrate'], 1),
                    "stall_rate_percent": stall_pct
                })
            return result
        finally:
            conn.close()

    @classmethod
    def get_historical_breakdown(
        cls,
        dimension: str = "playback_quality",
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        video_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Computes categorical distributions and per-category QoS performance.
        Allowed dimensions: 'playback_quality', 'device_type', 'video_id', 'playback_state'.
        """
        valid_dimensions = {
            "playback_quality": "playback_quality",
            "device_type": "device_type",
            "video_id": "video_id",
            "playback_state": "playback_state"
        }

        col_name = valid_dimensions.get(dimension.lower(), "playback_quality")
        conditions = []
        params = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if video_id and col_name != "video_id":
            conditions.append("video_id = ?")
            params.append(video_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT
                COALESCE({col_name}, 'unknown') AS dimension_value,
                COUNT(*) AS event_count,
                COUNT(DISTINCT user_id) AS unique_viewers,
                COALESCE(AVG(buffer_health), 0.0) AS avg_buffer_health,
                COALESCE(AVG(bitrate_kbps), 0.0) AS avg_bitrate,
                COALESCE(SUM(CASE WHEN playback_state = 'buffering' THEN 1 ELSE 0 END), 0) AS stall_count
            FROM telemetry_events
            {where_clause}
            GROUP BY {col_name}
            ORDER BY event_count DESC
        """

        conn = DatabaseManager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            total_events = sum(r['event_count'] for r in rows)

            result = []
            for r in rows:
                ev_cnt = r['event_count']
                stalls = r['stall_count']
                share_pct = round((ev_cnt / total_events * 100.0), 2) if total_events > 0 else 0.0
                stall_pct = round((stalls / ev_cnt * 100.0), 2) if ev_cnt > 0 else 0.0

                result.append({
                    "dimension": col_name,
                    "dimension_value": r['dimension_value'],
                    "event_count": ev_cnt,
                    "share_percentage": share_pct,
                    "unique_viewers": r['unique_viewers'],
                    "avg_buffer_health": round(r['avg_buffer_health'], 2),
                    "avg_bitrate_kbps": round(r['avg_bitrate'], 1),
                    "stall_rate_percent": stall_pct
                })
            return result
        finally:
            conn.close()

    @classmethod
    def get_retention_curve(cls, video_id: str, bucket_seconds: int = 15) -> List[Dict[str, Any]]:
        """
        Calculates the audience retention and viewer drop-off curve for a given video asset.
        """
        bucket_size = max(5, int(bucket_seconds))

        conn = DatabaseManager.get_connection()
        try:
            cursor = conn.cursor()
            # 1. Get max watch time achieved per distinct session
            cursor.execute("""
                SELECT session_id, MAX(watch_time_seconds) AS max_watch_time
                FROM telemetry_events
                WHERE video_id = ?
                GROUP BY session_id
            """, (video_id,))
            sessions = cursor.fetchall()

            total_sessions = len(sessions)
            if total_sessions == 0:
                return []

            max_duration = max(s['max_watch_time'] for s in sessions)
            num_buckets = int(max_duration // bucket_size) + 1

            retention_points = []
            for b in range(num_buckets):
                bucket_time = b * bucket_size
                retained_count = sum(1 for s in sessions if s['max_watch_time'] >= bucket_time)
                retention_rate = round((retained_count / total_sessions) * 100.0, 1)

                retention_points.append({
                    "time_seconds": bucket_time,
                    "time_label": f"{int(bucket_time // 60)}:{int(bucket_time % 60):02d}",
                    "viewers_retained": retained_count,
                    "retention_rate_percent": retention_rate
                })

            return retention_points
        finally:
            conn.close()
