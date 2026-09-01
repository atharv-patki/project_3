import json
import logging
import queue
import threading
from collections import defaultdict
from typing import Dict, Any, List, Optional, Union
from backend.config import Config
from backend.analytics_schema import PlaybackEvent

logger = logging.getLogger(__name__)

class InMemoryBroker:
    """
    High-throughput, thread-safe in-memory message broker.
    Provides topic queues and statistics for seamless local operation.
    """
    def __init__(self, maxsize_per_topic: int = 50000):
        self._maxsize = maxsize_per_topic
        self._topics: Dict[str, queue.Queue] = defaultdict(lambda: queue.Queue(maxsize=self._maxsize))
        self._lock = threading.Lock()
        self._published_count = 0
        self._consumed_count = 0

    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        try:
            q = self._topics[topic]
            q.put_nowait(message)
            with self._lock:
                self._published_count += 1
            return True
        except queue.Full:
            logger.warning(f"In-memory topic '{topic}' is full. Dropping message.")
            return False

    def get_topic_queue(self, topic: str) -> queue.Queue:
        return self._topics[topic]

    def get_queue_size(self, topic: str) -> int:
        if topic in self._topics:
            return self._topics[topic].qsize()
        return 0

    def increment_consumed(self, count: int = 1):
        with self._lock:
            self._consumed_count += count

    @property
    def published_count(self) -> int:
        with self._lock:
            return self._published_count

    @property
    def consumed_count(self) -> int:
        with self._lock:
            return self._consumed_count


class KafkaService:
    """
    Unified Message Broker Service.
    Connects to Apache Kafka if available; falls back to InMemoryBroker otherwise.
    """
    _instance: Optional['KafkaService'] = None
    _lock = threading.Lock()

    def __init__(self, bootstrap_servers: Optional[str] = None, default_topic: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or Config.KAFKA_BOOTSTRAP_SERVERS
        self.default_topic = default_topic or Config.KAFKA_TOPIC_EVENTS
        self.is_kafka_connected = False
        self.producer = None
        self.in_memory_broker = InMemoryBroker()
        self.total_published = 0
        self._stats_lock = threading.Lock()

        self._init_producer()

    def _init_producer(self):
        """Attempt connection to real Kafka cluster."""
        try:
            # Try importing kafka-python / kafka-python-ng
            from kafka import KafkaProducer
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                request_timeout_ms=3000,
                max_block_ms=3000,
                retries=2
            )
            # Test connectivity by querying cluster metadata
            self.producer.bootstrap_connected()
            self.is_kafka_connected = True
            print(f"[+] Connected to Apache Kafka broker cluster at {self.bootstrap_servers}")
        except Exception as e:
            self.is_kafka_connected = False
            self.producer = None
            print(f"[*] Kafka broker unavailable at {self.bootstrap_servers} ({e}). Activated In-Memory Telemetry Broker.")

    def publish_event(self, event: Union[PlaybackEvent, Dict[str, Any]], topic: Optional[str] = None) -> bool:
        """
        Publish a single telemetry event.
        Accepts either a PlaybackEvent instance or raw dict.
        """
        target_topic = topic or self.default_topic
        payload = event.to_dict() if isinstance(event, PlaybackEvent) else event

        if self.is_kafka_connected and self.producer is not None:
            try:
                self.producer.send(target_topic, value=payload)
                with self._stats_lock:
                    self.total_published += 1
                return True
            except Exception as e:
                logger.error(f"Failed to publish event to Kafka topic {target_topic}: {e}")
                # Fallback to in-memory on error
                return self.in_memory_broker.publish(target_topic, payload)
        else:
            success = self.in_memory_broker.publish(target_topic, payload)
            if success:
                with self._stats_lock:
                    self.total_published += 1
            return success

    def publish_batch(self, events: List[Union[PlaybackEvent, Dict[str, Any]]], topic: Optional[str] = None) -> int:
        """
        Publish a batch of telemetry events.
        Returns count of successfully published events.
        """
        target_topic = topic or self.default_topic
        published = 0

        for event in events:
            if self.publish_event(event, target_topic):
                published += 1

        if self.is_kafka_connected and self.producer is not None:
            try:
                self.producer.flush(timeout=2)
            except Exception as e:
                logger.warning(f"Error flushing Kafka producer: {e}")

        return published

    def get_consumer_channel(self, topic: Optional[str] = None) -> queue.Queue:
        """
        Retrieve the in-memory queue channel for downstream stream consumers.
        """
        target_topic = topic or self.default_topic
        return self.in_memory_broker.get_topic_queue(target_topic)

    def get_status(self) -> Dict[str, Any]:
        """
        Returns real-time status and operational health of the message broker.
        """
        with self._stats_lock:
            total_pub = self.total_published

        return {
            "mode": "kafka" if self.is_kafka_connected else "in-memory-broker",
            "healthy": True,
            "bootstrap_servers": self.bootstrap_servers,
            "default_topic": self.default_topic,
            "kafka_connected": self.is_kafka_connected,
            "total_published_events": total_pub,
            "in_memory_queue_depth": self.in_memory_broker.get_queue_size(self.default_topic)
        }

    def close(self):
        """Clean up producer connections."""
        if self.producer:
            try:
                self.producer.flush()
                self.producer.close()
            except Exception:
                pass


def get_kafka_service() -> KafkaService:
    """
    Singleton accessor for KafkaService.
    """
    if KafkaService._instance is None:
        with KafkaService._lock:
            if KafkaService._instance is None:
                KafkaService._instance = KafkaService()
    return KafkaService._instance
