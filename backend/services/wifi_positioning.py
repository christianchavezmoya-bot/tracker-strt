"""
HOLO-RTLS — WiFi / BLE RSSI-based Positioning Engine
Implements trilateration using the log-distance path loss model.
"""
from __future__ import annotations
import json
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from backend.extensions import db
from backend.models.detection import (
    DetectionEvent, WifiAnchor, TrackedDevice,
    FloorPlan, SignalType, DeviceType, AnchorStatus,
)
from backend.models.positioning import PositionSnapshot, TrackingHistory

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────
# Default path loss exponent (n): 2–4 indoors. 2.0 = free space.
DEFAULT_PATH_LOSS_EXPONENT = 2.5
# Minimum anchors needed for a position fix
MIN_ANCHORS_FOR_FIX = 3
# RSSI outlier threshold (dBm beyond median per anchor)
RSSI_OUTLIER_THRESHOLD = 10.0
# Maximum age of detections to consider fresh (seconds)
MAX_DETECTION_AGE_SEC = 10.0


@dataclass
class AnchorReading:
    anchor_id: int
    mac_address: str
    rssi: float
    tx_power: float
    path_loss_exp: float
    real_x: float
    real_y: float
    real_z: float


@dataclass
class PositionFix:
    x: float
    y: float
    z: float
    accuracy: float          # metres (estimated RMSE)
    source: str = "TRILATERATION"
    mac_address: str = ""
    method: str = "lsm"
    anchors_used: int = 0
    raw_rssi: dict = field(default_factory=dict)   # anchor_id → rssi


# ── Distance estimation ───────────────────────────────────────────────────────
def rssi_to_distance(rssi: float, tx_power: float, n: float = DEFAULT_PATH_LOSS_EXPONENT) -> float:
    """
    Log-distance path loss model.
    d = 10 ^ ((tx_power - rssi) / (10 * n))
    Returns distance in metres.
    """
    if rssi >= tx_power:
        return 0.5   # inside tx range — clamp to minimum
    try:
        return 10 ** ((tx_power - rssi) / (10 * n))
    except (ValueError, ZeroDivisionError):
        return 5.0   # fallback


# ── Trilateration solvers ─────────────────────────────────────────────────────

def solve_lsm(anchors: list[AnchorReading]) -> tuple[float, float, float]:
    """
    Least-squares minimisation (pseudo-inverse).
    Linearises circles: 2*x*dx + 2*y*dy = dx²+dy²-r²+r₀²
    Works for ≥ 3 anchors.
    NOTE: anchors[i].rssi must already be the **distance in metres**,
    not the raw RSSI dBm value.
    """
    n = len(anchors)
    if n < 3:
        return anchors[0].real_x, anchors[0].real_y, anchors[0].real_z

    # Convert RSSI → distance for every anchor first
    dists = [rssi_to_distance(a.rssi, a.tx_power, a.path_loss_exp) for a in anchors]

    # Build matrices using the actual distances
    H = []
    b = []
    x0, y0 = anchors[0].real_x, anchors[0].real_y
    d0 = dists[0]
    for i, a in enumerate(anchors):
        H.append([2 * (a.real_x - x0), 2 * (a.real_y - y0)])
        dist_sq = (a.real_x - x0) ** 2 + (a.real_y - y0) ** 2
        b.append(dist_sq - dists[i] ** 2 + d0 ** 2)

    H = np.array(H)
    b = np.array(b)

    try:
        sol = np.linalg.lstsq(H, b, rcond=None)[0]
        return float(sol[0]), float(sol[1]), anchors[0].real_z
    except Exception:
        return x0, y0, anchors[0].real_z


def solve_iterative(anchors: list[AnchorReading],
                    max_iter: int = 50,
                    tol: float = 1e-4) -> tuple[float, float, float]:
    """
    Iterative gradient descent for trilateration.
    Starts from centroid and converges toward solution.
    """
    n = len(anchors)
    if n < 3:
        return anchors[0].real_x, anchors[0].real_y, anchors[0].real_z

    # Initial guess: centroid
    x = sum(a.real_x for a in anchors) / n
    y = sum(a.real_y for a in anchors) / n
    z = anchors[0].real_z

    for _ in range(max_iter):
        grad_x = 0.0
        grad_y = 0.0
        total_w = 0.0

        for a in anchors:
            d = math.sqrt((a.real_x - x) ** 2 + (a.real_y - y) ** 2)
            d = max(d, 0.01)
            w = 1.0 / (d ** 2)
            residual = d - a.rssi
            grad_x += w * residual * (x - a.real_x) / d
            grad_y += w * residual * (y - a.real_y) / d
            total_w += w

        if total_w < 1e-9:
            break

        grad_x /= total_w
        grad_y /= total_w

        x -= 0.5 * grad_x
        y -= 0.5 * grad_y

        if abs(grad_x) < tol and abs(grad_y) < tol:
            break

    return x, y, z


def estimate_accuracy(anchors: list[AnchorReading], x: float, y: float) -> float:
    """
    Estimate position error from residuals across anchors.
    Uses the same distance conversion as solve_lsm for consistency.
    """
    if len(anchors) < 2:
        return 10.0
    residuals = []
    for a in anchors:
        d_actual = math.sqrt((a.real_x - x) ** 2 + (a.real_y - y) ** 2)
        d_rssi   = rssi_to_distance(a.rssi, a.tx_power, a.path_loss_exp)
        residuals.append(abs(d_actual - d_rssi))
    return float(statistics.mean(residuals)) if residuals else 10.0


# ── Kalman filter for position smoothing ─────────────────────────────────────
class PositionKalman:
    """
    Lightweight 1D Kalman filter per axis.
    Smooths noisy RSSI-derived positions.
    """
    def __init__(self, process_noise: float = 0.5, measurement_noise: float = 2.0):
        self.x     = 0.0
        self.P     = 1.0
        self.Q     = process_noise
        self.R     = measurement_noise

    def update(self, measurement: float) -> float:
        # Prediction
        self.P += self.Q
        # Update
        K = self.P / (self.P + self.R)
        self.x += K * (measurement - self.x)
        self.P *= (1 - K)
        return self.x

    def reset(self, value: float = 0.0):
        self.x = value
        self.P = 1.0


# ── Main positioning service ───────────────────────────────────────────────────
class WifiPositioningService:
    """
    RSSI-based indoor positioning using WiFi / BLE anchors.
    Reads fresh DetectionEvents, groups by MAC, trilaterates, persists.
    """

    def __init__(self, session, path_loss_exp: float = DEFAULT_PATH_LOSS_EXPONENT):
        self.db            = session
        self.path_loss_exp = path_loss_exp
        self._kalman: dict[str, tuple[PositionKalman, PositionKalman]] = {}
        self._last_fix: dict[str, datetime] = {}
        self._stale_after_sec = 30.0

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_scan_batch(self, anchor_mac: str, detections: list[dict]) -> int:
        """
        Ingest a batch of detections from one anchor.
        Returns number of positions computed.
        """
        anchor = self.db.query(WifiAnchor).filter_by(mac_address=anchor_mac).first()
        if not anchor:
            logger.warning(f"Unknown anchor MAC: {anchor_mac}")
            return 0

        anchor.last_seen = datetime.utcnow()
        self.db.query(DetectionEvent).filter_by(anchor_id=anchor.id).delete()
        self.db.flush()

        # Persist raw detections (accept mac_address / mac / bssid aliases)
        for d in detections:
            mac = (
                d.get("mac_address")
                or d.get("mac")
                or d.get("bssid")
                or d.get("device_mac")
                or ""
            )
            if not mac:
                logger.warning("Skipping detection without mac_address: %s", d)
                continue
            try:
                rssi = float(d.get("rssi", d.get("signal_strength", -70)))
            except (TypeError, ValueError):
                continue
            ev = DetectionEvent(
                anchor_id=anchor.id,
                mac_address=str(mac).upper(),
                rssi=rssi,
                signal_type=int(d.get("signal_type", SignalType.WIFI)),
                ssid=d.get("ssid"),
                adv_name=d.get("adv_name"),
                channel=d.get("channel"),
            )
            self.db.add(ev)

        self.db.commit()
        return self._compute_positions_for_anchor(anchor.id)

    def _compute_positions_for_anchor(self, anchor_id: int) -> int:
        """Compute positions for all MACs seen by one anchor (solo anchor = no fix)."""
        # This anchor alone can't trilaterate — return raw detections only
        return 0

    def compute_all_positions(self, floor_plan_id: int = None) -> list[PositionFix]:
        """
        Full trilateration pass: group fresh detections by MAC,
        solve for each device, apply Kalman smoothing, persist.
        Returns list of PositionFix objects.
        """
        anchors = self._get_active_anchors(floor_plan_id)
        if len(anchors) < MIN_ANCHORS_FOR_FIX:
            logger.debug(f"Not enough anchors ({len(anchors)}) for positioning")
            return []

        # Group detections by MAC across anchors.
        # process_scan_batch deletes old events for each anchor before inserting fresh ones,
        # so we just query all events per anchor — no timestamp filter needed.
        mac_detections: dict[str, list[DetectionEvent]] = {}
        for anchor in anchors:
            events = self.db.query(DetectionEvent).filter(
                DetectionEvent.anchor_id == anchor.id,
            ).all()
            for ev in events:
                mac_detections.setdefault(ev.mac_address, []).append(ev)

        fixes = []
        for mac, events in mac_detections.items():
            if len(events) < MIN_ANCHORS_FOR_FIX:
                continue

            fix = self._trilaterate_mac(mac, events, anchors)
            if fix:
                fixes.append(fix)

        # Persist positions
        for fix in fixes:
            self._persist_fix(fix)

        return fixes

    def get_position(self, mac_address: str) -> Optional[PositionFix]:
        """Get last known position for a MAC (from DB snapshot)."""
        dev = self.db.query(TrackedDevice).filter(
            TrackedDevice.mac_address == mac_address.upper()
        ).first()
        if dev and dev.pos_x is not None:
            return PositionFix(
                x=dev.pos_x, y=dev.pos_y, z=dev.pos_z,
                accuracy=dev.pos_accuracy or 10.0,
                source=dev.pos_source or "SNAPSHOT",
                mac_address=mac_address,
            )
        return None

    def get_active_devices(self, floor_plan_id: int = None,
                          since_seconds: float = 120.0) -> list[dict]:
        """Return all recently active tracked devices with positions."""
        cutoff = datetime.utcnow()
        since = datetime.fromtimestamp(cutoff.timestamp() - since_seconds)

        devs = self.db.query(TrackedDevice).filter(
            TrackedDevice.is_active == True,
            TrackedDevice.last_seen >= since,
        ).all()

        return [dev.to_dict() for dev in devs]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _get_active_anchors(self, floor_plan_id: int = None):
        q = self.db.query(WifiAnchor).filter(WifiAnchor.status == AnchorStatus.ACTIVE)
        if floor_plan_id:
            q = q.filter(WifiAnchor.floor_plan_id == floor_plan_id)
        anchors = q.all()
        return [a for a in anchors if a.real_x is not None]

    def _trilaterate_mac(self, mac: str,
                          events: list[DetectionEvent],
                          anchors: list[WifiAnchor]) -> Optional[PositionFix]:
        """
        Trilaterate a single MAC from ≥3 detection events.
        """
        anchor_map = {a.id: a for a in anchors}

        # Filter to anchors we know positions for
        readings: list[AnchorReading] = []
        rssi_vals: list[float] = []

        for ev in events:
            if ev.anchor_id not in anchor_map:
                continue
            anchor = anchor_map[ev.anchor_id]
            if anchor.real_x is None:
                continue

            # Outlier filter: skip if anchor's avg RSSI is very different
            readings.append(AnchorReading(
                anchor_id=anchor.id,
                mac_address=mac,
                rssi=ev.rssi,
                tx_power=anchor.tx_power,
                path_loss_exp=self.path_loss_exp,
                real_x=anchor.real_x,
                real_y=anchor.real_y,
                real_z=anchor.real_z,
            ))
            rssi_vals.append(ev.rssi)

        if len(readings) < MIN_ANCHORS_FOR_FIX:
            return None

        # Remove gross outliers (RSSI more than RSSI_OUTLIER_THRESHOLD from median)
        if len(rssi_vals) > 2:
            median_rssi = statistics.median(rssi_vals)
            readings = [
                r for r in readings
                if abs(r.rssi - median_rssi) <= RSSI_OUTLIER_THRESHOLD
            ]
        if len(readings) < MIN_ANCHORS_FOR_FIX:
            return None

        # Solve
        x, y, z = solve_lsm(readings)
        accuracy = estimate_accuracy(readings, x, y)

        # Centroid as anchor for Kalman initialization
        cx = sum(r.real_x for r in readings) / len(readings)
        cy = sum(r.real_y for r in readings) / len(readings)

        # Kalman smooth per device (seeded near first fix to avoid startup jump)
        kx, ky = self._get_kalman(mac, init_x=cx, init_y=cy)
        x_k = kx.update(x)
        y_k = ky.update(y)

        # Confidence check — if LSM result is far from centroid, fall back
        dist_from_centroid = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if dist_from_centroid > 30.0:
            logger.debug(f"Trilateration implausible for {mac}: ({x:.1f},{y:.1f}) vs centroid ({cx:.1f},{cy:.1f})")
            return None

        raw_rssi = {r.anchor_id: r.rssi for r in readings}
        return PositionFix(
            x=round(x_k, 3), y=round(y_k, 3), z=round(z, 3),
            accuracy=round(accuracy, 2),
            source="TRILATERATION",
            mac_address=mac,
            method="lsm",
            anchors_used=len(readings),
            raw_rssi=raw_rssi,
        )

    def _get_kalman(self, mac: str, init_x: float = 0.0, init_y: float = 0.0):
        """Return (or create) per-device Kalman filters, seeded near the first fix."""
        key = mac.upper()
        if key not in self._kalman:
            kx = PositionKalman()
            ky = PositionKalman()
            kx.reset(init_x)
            ky.reset(init_y)
            self._kalman[key] = (kx, ky)
        return self._kalman[key]

    def _persist_fix(self, fix: PositionFix):
        """Write PositionFix to TrackedDevice + PositionSnapshot."""
        mac = fix.mac_address.upper()
        dev = self.db.query(TrackedDevice).filter_by(mac_address=mac).first()
        now = datetime.utcnow()

        if dev is None:
            dev = TrackedDevice(mac_address=mac, first_seen=now)
            self.db.add(dev)

        dev.pos_x      = fix.x
        dev.pos_y      = fix.y
        dev.pos_z      = fix.z
        dev.pos_accuracy = fix.accuracy
        dev.pos_source = fix.source
        dev.last_seen  = now

        self.db.commit()

    # ── Calibration helpers ─────────────────────────────────────────────────────

    def calibrate_anchor(self, anchor_id: int, tx_power: float):
        """Update anchor TX power after calibration."""
        anchor = self.db.query(WifiAnchor).get(anchor_id)
        if anchor:
            anchor.tx_power = tx_power
            self.db.commit()

    def set_calibration(self, floor_plan_id: int, calibration: dict):
        """Save affine transform for a floor plan."""
        fp = self.db.query(FloorPlan).get(floor_plan_id)
        if fp:
            fp.calibration_json = json.dumps(calibration)
            self.db.commit()

    def pixel_to_real(self, floor_plan_id: int, px: float, py: float) -> tuple[float, float]:
        """Convert pixel coords → real-world metres using saved calibration."""
        fp = self.db.query(FloorPlan).get(floor_plan_id)
        if not fp or not fp.calibration_json:
            return px, py   # no calibration — identity pass-through

        try:
            c = json.loads(fp.calibration_json)
        except Exception:
            return px, py

        # Affine: real_x = a*px + b*py + c
        rx = c.get("a", 1.0) * px + c.get("b", 0.0) * py + c.get("c", 0.0)
        ry = c.get("d", 0.0) * px + c.get("e", 1.0) * py + c.get("f", 0.0)
        return rx, ry
