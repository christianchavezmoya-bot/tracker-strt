"""
HOLO-RTLS — History Service
Manages tracking history: circular buffer + periodic SQLite writes.
Pruning old records based on retention policy.
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Accumulates position snapshots and writes them to the DB in batches.

    Flow:
      1. Ingestion loop calls write_position() for every position update
      2. HistoryService appends to an in-memory circular buffer
      3. A background thread flushes to SQLite every `flush_interval` seconds
      4. A nightly job prunes records older than `retention_days`
    """

    def __init__(self, db_session, retention_days: int = 30, flush_interval: int = 5,
                 max_buffer: int = 5000, app=None):
        self._db = db_session
        self._retention_days = retention_days
        self._flush_interval = flush_interval
        self._max_buffer = max_buffer
        # Flask app reference — needed for app_context() in background threads
        self._app = app

        # In-memory circular buffers: tracker_id → deque of positions
        from collections import deque
        self._buffers: Dict[int, list] = defaultdict(list)
        self._last_velocity: Dict[int, Dict] = {}   # tracker_id → {prev_pos, prev_time}
        self._lock = threading.Lock()

        # Background flush thread
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="HistoryFlush")
        self._stop = threading.Event()

        # Stats
        self._total_written = 0
        self._total_pruned = 0

    def start(self):
        self._flush_thread.start()
        logger.info(f"HistoryService started (flush every {self._flush_interval}s, retention {self._retention_days}d)")

    def stop(self):
        self._stop.set()
        self._flush_thread.join(timeout=10)
        self._flush_all()   # Final flush on shutdown
        logger.info(f"HistoryService stopped. Written: {self._total_written}, Pruned: {self._total_pruned}")

    # ── Ingestion API ──────────────────────────────────────────────────────────

    def write_position(self, tracker_id: int,
                       x: float, y: float, z: float,
                       accuracy: Optional[float] = None,
                       source: str = "UWB",
                       hardware_id: Optional[str] = None,
                       timestamp: Optional[datetime] = None,
                       section_id: Optional[int] = None):
        """
        Record a position update. Called by the ingestion loop on every update.

        Args:
            tracker_id: DB id of the tracker
            x, y, z: Position in real-world meters
            accuracy: Estimated error in meters
            source: "UWB", "BLE", "WIFI", "MOCK"
            hardware_id: Hardware identifier of the source
            timestamp: When the position was measured (default: now)
            section_id: Map section this position belongs to
        """
        from backend.models.positioning import TrackingHistory, PositionSnapshot

        now = timestamp or datetime.now(timezone.utc)

        # ── Update PositionSnapshot (latest position, one row per tracker) ──
        snapshot = self._db.query(PositionSnapshot).get(tracker_id)
        if not snapshot:
            snapshot = PositionSnapshot(tracker_id=tracker_id)
            self._db.add(snapshot)

        # Velocity estimation
        vx, vy, speed = None, None, None
        if tracker_id in self._last_velocity:
            prev = self._last_velocity[tracker_id]
            dt = (now - prev["time"]).total_seconds()
            if dt > 0:
                vx = (x - prev["x"]) / dt
                vy = (y - prev["y"]) / dt
                speed = (vx ** 2 + vy ** 2) ** 0.5

        self._last_velocity[tracker_id] = {"x": x, "y": y, "time": now}

        snapshot.x = x
        snapshot.y = y
        snapshot.z = z
        snapshot.accuracy = accuracy
        snapshot.vx = round(vx, 3) if vx else None
        snapshot.vy = round(vy, 3) if vy else None
        snapshot.speed = round(speed, 3) if speed else None
        snapshot.source = source
        snapshot.hardware_id = hardware_id
        snapshot.updated_at = now
        snapshot.last_seen_hardware = now

        # ── Append to circular buffer for batch history write ──
        entry = {
            "tracker_id": tracker_id,
            "x": x, "y": y, "z": z,
            "accuracy": accuracy,
            "hardware_id": hardware_id,
            "timestamp": now,
            "vx": round(vx, 3) if vx else None,
            "vy": round(vy, 3) if vy else None,
            "speed": round(speed, 3) if speed else None,
            "section_id": section_id,
        }

        with self._lock:
            self._buffers[tracker_id].append(entry)
            # Soft cap: flush early if buffer is getting huge
            total_size = sum(len(v) for v in self._buffers.values())
            if total_size >= self._max_buffer:
                self._flush_unlocked()

    # ── Batch flush ────────────────────────────────────────────────────────────

    def _flush_loop(self):
        """Background thread: flush buffers to DB every flush_interval seconds."""
        while not self._stop.is_set():
            time.sleep(self._flush_interval)
            if self._stop.is_set():
                break
            try:
                self._flush_all()
                self._maybe_prune()
            except Exception as e:
                logger.error(f"History flush error: {e}")

    def _flush_all(self):
        # Background thread has no Flask context by default — push one so scoped
        # sessions (used by SQLAlchemy in this app) can acquire a connection.
        app = self._app or __import__('flask').current_app._get_current_object()
        with app.app_context():
            with self._lock:
                self._flush_unlocked()

    def _flush_unlocked(self):
        """Flush all buffers. Must be called while holding self._lock."""
        from backend.models.positioning import TrackingHistory

        if not self._buffers:
            return

        total = 0
        for tracker_id, entries in list(self._buffers.items()):
            if not entries:
                continue
            for entry in entries:
                hist = TrackingHistory(
                    tracker_id=entry["tracker_id"],
                    x=entry["x"],
                    y=entry["y"],
                    z=entry.get("z", 0.0),
                    accuracy=entry.get("accuracy"),
                    hardware_id=entry.get("hardware_id"),
                    timestamp=entry["timestamp"],
                    vx=entry.get("vx"),
                    vy=entry.get("vy"),
                    speed=entry.get("speed"),
                )
                self._db.add(hist)
                total += 1

            self._buffers[tracker_id].clear()

        if total > 0:
            try:
                self._db.commit()
                self._total_written += total
                logger.debug(f"Flushed {total} history records")
            except Exception as e:
                logger.error(f"DB flush error: {e}")
                self._db.rollback()

    # ── Pruning ───────────────────────────────────────────────────────────────

    def _maybe_prune(self):
        """Prune records older than retention_days. Runs nightly."""
        # Same as _flush_all: background thread needs an app context for the
        # scoped session to reach the DB (incl. the rollback in the except).
        app = self._app or __import__('flask').current_app._get_current_object()
        with app.app_context():
            cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
            from backend.models.positioning import TrackingHistory
            try:
                deleted = self._db.query(TrackingHistory).filter(
                    TrackingHistory.timestamp < cutoff
                ).delete()
                self._db.commit()
                if deleted > 0:
                    self._total_pruned += deleted
                    logger.info(f"Pruned {deleted} history records older than {cutoff.date()}")
            except Exception as e:
                logger.error(f"History prune error: {e}")
                self._db.rollback()

    def prune_now(self) -> int:
        """Explicit prune. Returns number of deleted records."""
        self._maybe_prune()
        return self._total_pruned

    # ── Read API ───────────────────────────────────────────────────────────────

    def get_latest(self, tracker_id: int) -> Optional[Dict]:
        """Get the latest position snapshot for a tracker."""
        from backend.models.positioning import PositionSnapshot
        snapshot = self._db.query(PositionSnapshot).get(tracker_id)
        return snapshot.to_dict() if snapshot else None

    def get_history(self, tracker_id: int,
                    since: Optional[datetime] = None,
                    limit: int = 1000) -> List[Dict]:
        """Get position history for a tracker."""
        from backend.models.positioning import TrackingHistory
        q = self._db.query(TrackingHistory).filter(
            TrackingHistory.tracker_id == tracker_id
        ).order_by(TrackingHistory.timestamp.desc())

        if since:
            q = q.filter(TrackingHistory.timestamp >= since)

        rows = q.limit(limit).all()
        return [r.to_dict() for r in rows]

    def get_stats(self) -> Dict:
        from backend.models.positioning import TrackingHistory
        total = self._db.query(TrackingHistory).count()
        return {
            "total_records": total,
            "total_written": self._total_written,
            "total_pruned": self._total_pruned,
            "retention_days": self._retention_days,
            "buffer_size": sum(len(v) for v in self._buffers.values()),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_history_service: Optional[HistoryService] = None


def get_history_service() -> HistoryService:
    return _history_service


def init_history_service(db_session, app=None, **kwargs) -> HistoryService:
    global _history_service
    _history_service = HistoryService(db_session, app=app, **kwargs)
    return _history_service
