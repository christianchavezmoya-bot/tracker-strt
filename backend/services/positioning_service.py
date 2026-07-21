"""
HOLO-RTLS — Positioning Service
Wraps reference/uwb_positioning.py:
  - UWB trilateration + Kalman smoothing
  - BLE/WiFi RSSI → distance → weighted centroid
  - Per-tracker filter state (stateless, re-initialised on restart)
  - Reads anchor positions from WifiNode DB table
"""
from __future__ import annotations
import math
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

# Import from reference — add reference/ to path at runtime
import sys, os
_ref_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "reference")
if _ref_path not in sys.path:
    sys.path.insert(0, _ref_path)

from uwb_positioning import UWBPositioning, KalmanFilter1D, simulate_uwb_ranges


# ── Signal model constants ─────────────────────────────────────────────────────
# Path-loss exponent (n): 2.0 = free space, 2.5–4.0 = indoor
_PATH_LOSS_EXPONENT = 2.5
# Reference RSSI at 1 meter (tune per hardware)
_RSSI_REF_DBM = -60.0


class PositioningService:
    """
    Unified positioning engine. Handles:
    - UWB: trilateration from range measurements
    - BLE/WiFi: RSSI → distance via log-distance path loss model
    - Kalman smoothing per tracker
    - Anchor management (loads from DB WifiNode table)
    """

    def __init__(self, db_session=None):
        self._db = db_session
        # Per-tracker UWB instances: tracker_hardware_id → UWBPositioning
        self._uwb_instances: Dict[str, UWBPositioning] = {}
        # Per-tracker Kalman filters: tracker_hardware_id → (kf_x, kf_y, kf_z)
        self._kalman: Dict[str, Tuple[KalmanFilter1D, KalmanFilter1D, KalmanFilter1D]] = {}
        # Anchor cache: anchor_id → (x, y, z)
        self._anchors: Dict[str, Tuple[float, float, float]] = {}
        self._initialized = False

    # ── Anchor management ─────────────────────────────────────────────────────

    def load_anchors_from_db(self) -> int:
        """
        Load anchor positions from the WifiNode table.
        Returns number of anchors loaded.
        """
        if not self._db:
            logger.warning("No DB session — cannot load anchors")
            return 0

        try:
            # Import here to avoid circular import
            from backend.models.tracker import WifiNode, NodeStatus

            anchors = self._db.query(WifiNode).filter(
                WifiNode.status == int(NodeStatus.ACTIVE)
            ).all()

            self._anchors.clear()
            for node in anchors:
                mac = node.mac_address
                self._anchors[mac] = (
                    float(node.pos_x),
                    float(node.pos_y),
                    float(node.pos_z or 0.0),
                )

            logger.info(f"Loaded {len(self._anchors)} anchors: {list(self._anchors.keys())}")
            return len(self._anchors)
        except Exception as e:
            logger.error(f"Failed to load anchors from DB: {e}")
            return 0

    def add_anchor(self, anchor_id: str, x: float, y: float, z: float = 0.0) -> None:
        """Manually register an anchor (overrides DB load)."""
        self._anchors[anchor_id] = (x, y, z)
        # Reset UWB instances so they pick up new anchors
        self._uwb_instances.clear()

    def remove_anchor(self, anchor_id: str) -> None:
        if anchor_id in self._anchors:
            del self._anchors[anchor_id]
            self._uwb_instances.clear()

    # ── Per-tracker filter state ───────────────────────────────────────────────

    def _get_uwb(self, tracker_hardware_id: str) -> UWBPositioning:
        if tracker_hardware_id not in self._uwb_instances:
            uwb = UWBPositioning(num_anchors=4, history_size=10)
            for anchor_id, (x, y, z) in self._anchors.items():
                uwb.add_anchor(anchor_id, x, y, z)
            self._uwb_instances[tracker_hardware_id] = uwb
        return self._uwb_instances[tracker_hardware_id]

    def _get_kalman(self, tracker_hardware_id: str) -> Tuple[KalmanFilter1D, KalmanFilter1D, KalmanFilter1D]:
        if tracker_hardware_id not in self._kalman:
            self._kalman[tracker_hardware_id] = (
                KalmanFilter1D(process_variance=0.005, measurement_variance=0.05),
                KalmanFilter1D(process_variance=0.005, measurement_variance=0.05),
                KalmanFilter1D(process_variance=0.005, measurement_variance=0.2),
            )
        return self._kalman[tracker_hardware_id]

    # ── UWB positioning ────────────────────────────────────────────────────────

    def position_from_uwb_ranges(
        self,
        tracker_hardware_id: str,
        ranges: Dict[str, float],
        use_kalman: bool = True,
    ) -> Optional[Dict]:
        """
        Compute 3D position from UWB range measurements.
        Returns {x, y, z, accuracy, raw_x, raw_y, raw_z} or None.

        Args:
            tracker_hardware_id: Identifier for this tracker (hardware_id)
            ranges: {anchor_id: distance_in_meters}
            use_kalman: Apply Kalman smoothing
        """
        if len(self._anchors) < 3:
            logger.warning("Fewer than 3 anchors registered — cannot trilaterate")
            return None

        uwb = self._get_uwb(tracker_hardware_id)
        kf_x, kf_y, kf_z = self._get_kalman(tracker_hardware_id)

        # Trilaterate
        pos3d = uwb.trilaterate_3d(ranges)
        if not pos3d:
            pos2d = uwb.trilaterate_2d(ranges)
            if not pos2d:
                return None
            raw_x, raw_y = pos2d
            raw_z = 0.0
        else:
            raw_x, raw_y, raw_z = pos3d

        raw = (raw_x, raw_y, raw_z)

        # Kalman smoothing
        if use_kalman:
            smooth_x = kf_x.update(raw_x)
            smooth_y = kf_y.update(raw_y)
            smooth_z = kf_z.update(raw_z)
        else:
            smooth_x, smooth_y, smooth_z = raw_x, raw_y, raw_z

        accuracy = uwb.calculate_accuracy((raw_x, raw_y), ranges)

        return {
            "x": smooth_x,
            "y": smooth_y,
            "z": smooth_z,
            "raw_x": raw_x,
            "raw_y": raw_y,
            "raw_z": raw_z,
            "accuracy": accuracy,
        }

    # ── BLE/WiFi RSSI positioning ────────────────────────────────────────────────

    def rssi_to_distance(self, rssi: float, tx_power: float = _RSSI_REF_DBM,
                        exp: float = _PATH_LOSS_EXPONENT) -> float:
        """
        Convert RSSI (dBm) to estimated distance (meters).
        Uses the log-distance path loss model.
        """
        if rssi >= 0:
            return 999.0  # Invalid RSSI
        distance = 10 ** ((tx_power - rssi) / (10 * exp))
        return max(0.1, min(distance, 100.0))  # Clamp to 0.1–100 m

    def position_from_rssi(
        self,
        tracker_hardware_id: str,
        rssi_by_anchor: Dict[str, float],
        use_kalman: bool = True,
    ) -> Optional[Dict]:
        """
        Estimate position from RSSI measurements using weighted centroid.
        Less accurate than UWB (3–10m) but works with BLE/WiFi.
        """
        if len(rssi_by_anchor) < 3:
            logger.warning(f"Not enough RSSI anchors for {tracker_hardware_id}: {len(rssi_by_anchor)}")
            return None

        # Convert RSSI → distance
        distances = {aid: self.rssi_to_distance(rssi) for aid, rssi in rssi_by_anchor.items()}

        # Weighted centroid — weight = 1/d² (closer anchors count more)
        total_weight = 0.0
        wx, wy = 0.0, 0.0

        for aid, dist in distances.items():
            if aid not in self._anchors:
                continue
            x, y, _ = self._anchors[aid]
            weight = 1.0 / (dist ** 2) if dist > 0.01 else 1e6
            wx += x * weight
            wy += y * weight
            total_weight += weight

        if total_weight <= 0:
            return None

        raw_x = wx / total_weight
        raw_y = wy / total_weight

        kf_x, kf_y, _ = self._get_kalman(tracker_hardware_id)
        smooth_x = kf_x.update(raw_x) if use_kalman else raw_x
        smooth_y = kf_y.update(raw_y) if use_kalman else raw_y

        # Estimate accuracy: average distance-weighted error proxy
        avg_dist = sum(distances.values()) / max(len(distances), 1)
        accuracy = avg_dist * 0.5  # Rough proxy

        return {
            "x": smooth_x,
            "y": smooth_y,
            "z": 0.0,
            "raw_x": raw_x,
            "raw_y": raw_y,
            "raw_z": 0.0,
            "accuracy": accuracy,
        }

    # ── Multi-source fusion ────────────────────────────────────────────────────

    def position_from_payload(
        self,
        tracker_hardware_id: str,
        payload: Dict,
        source: str = "UWB",
    ) -> Optional[Dict]:
        """
        Route a raw hardware payload to the right positioning method.

        Expected UWB payload:  {"ranges": {"anchor_0": 2.5, "anchor_1": 3.2}}
        Expected BLE payload:   {"rssi": {"anchor_0": -72, "anchor_1": -68}}
        Expected Sewio payload: {"x": 12.5, "y": 8.3, "z": 0.0, "quality": 0.95}
        Expected mock payload:  {"x": 1.2, "y": 3.4, "z": 0.0}
        """
        if source == "UWB" or "ranges" in payload:
            ranges = payload.get("ranges", payload)
            return self.position_from_uwb_ranges(tracker_hardware_id, ranges)

        elif source in ("BLE", "WIFI") or "rssi" in payload:
            rssi_data = payload.get("rssi", payload)
            return self.position_from_rssi(tracker_hardware_id, rssi_data)

        elif source == "SEWIO" or ("x" in payload and "y" in payload):
            # Sewio / external IPS already provides x,y
            raw_x = float(payload["x"])
            raw_y = float(payload["y"])
            raw_z = float(payload.get("z", 0.0))

            kf_x, kf_y, kf_z = self._get_kalman(tracker_hardware_id)
            smooth_x = kf_x.update(raw_x)
            smooth_y = kf_y.update(raw_y)
            smooth_z = kf_z.update(raw_z)

            return {
                "x": smooth_x,
                "y": smooth_y,
                "z": smooth_z,
                "raw_x": raw_x,
                "raw_y": raw_y,
                "raw_z": raw_z,
                "accuracy": float(payload.get("accuracy", payload.get("quality", 1.0))),
            }

        else:
            logger.warning(f"Unknown payload format from {tracker_hardware_id}: {list(payload.keys())}")
            return None

    # ── Velocity estimation ────────────────────────────────────────────────────

    def estimate_velocity(
        self,
        pos_now: Dict,
        pos_prev: Dict,
        dt: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Compute velocity (vx, vy, speed) from two position snapshots.
        dt = time delta in seconds.
        Returns (vx, vy, speed) or (None, None, None) if insufficient data.
        """
        if dt <= 0 or not pos_now or not pos_prev:
            return None, None, None
        vx = (pos_now["x"] - pos_prev["x"]) / dt
        vy = (pos_now["y"] - pos_prev["y"]) / dt
        speed = math.sqrt(vx ** 2 + vy ** 2)
        return round(vx, 3), round(vy, 3), round(speed, 3)

    # ── Mock data generator ────────────────────────────────────────────────────

    def generate_mock_position(self, tracker_hardware_id: str,
                              anchor_positions: Dict[str, Tuple[float, float, float]],
                              noise_std: float = 0.1) -> Dict:
        """
        Generate a synthetic UWB position for testing (no real hardware needed).
        Registers anchor_positions into self._anchors so trilateration works.
        """
        # Register the anchors so position_from_uwb_ranges can use them
        for aid, pos in anchor_positions.items():
            self._anchors[aid] = pos
        self._uwb_instances.clear()  # Force re-init of UWB instances

        # Pick a random "true" position within the anchor bounding box
        xs = [p[0] for p in anchor_positions.values()]
        ys = [p[1] for p in anchor_positions.values()]
        true_x = (min(xs) + max(xs)) / 2 + (np.random.rand() - 0.5) * 2
        true_y = (min(ys) + max(ys)) / 2 + (np.random.rand() - 0.5) * 2

        ranges = simulate_uwb_ranges((true_x, true_y), anchor_positions, noise_std)
        return self.position_from_uwb_ranges(tracker_hardware_id, ranges)


# ── Singleton (initialised by app factory) ────────────────────────────────────
_positioning_service: Optional[PositioningService] = None


def get_positioning_service() -> PositioningService:
    global _positioning_service
    if _positioning_service is None:
        from backend.extensions import db
        _positioning_service = PositioningService(db.session)
    return _positioning_service
