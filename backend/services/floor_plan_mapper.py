"""
HOLO-RTLS — Floor Plan Mapper Service
Wraps reference/floor_plan_mapper.py (affine transformation).
Calibration data is stored in the Setting table as JSON.
"""
from __future__ import annotations
import logging
import json
from typing import Dict, Optional, Tuple, List

import sys, os
_ref_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "reference")
if _ref_path not in sys.path:
    sys.path.insert(0, _ref_path)

from floor_plan_mapper import FloorPlanMapper as _FPM

logger = logging.getLogger(__name__)

SETTING_KEY = "floor_plan_calibration"


class FloorPlanMapperService:
    """
    Manages one or more floor plan mappers (one per map/section).
    Calibration is persisted to the Setting key-value store.
    """

    def __init__(self, db_session=None):
        self._db = db_session
        # section_id → FloorPlanMapper instance
        self._mappers: Dict[int, _FPM] = {}
        self._load_all()

    def _load_all(self):
        """Load all calibration data from the Setting table."""
        if not self._db:
            return
        from backend.models import Setting
        rows = self._db.query(Setting).filter(Setting.key == SETTING_KEY).all()
        for row in rows:
            try:
                data = json.loads(row.value)
                section_id = int(row.scope_id or 0)
                self._load_mapper(section_id, data)
            except Exception as e:
                logger.error(f"Failed to load floor plan calibration for scope {row.scope_id}: {e}")

    def _load_mapper(self, section_id: int, data: dict):
        """Reconstruct a FloorPlanMapper from saved calibration data."""
        mapper = _FPM()
        for pt in data.get("calibration_points", []):
            mapper.add_calibration_point(
                pt["pixel_x"], pt["pixel_y"],
                pt["real_x"], pt["real_y"],
            )
        self._mappers[section_id] = mapper
        logger.info(f"Loaded floor plan mapper for section {section_id}: calibrated={mapper.is_calibrated}")

    def _save(self, section_id: int):
        """Persist mapper calibration to the Setting table."""
        if not self._db:
            return
        from backend.models import Setting, SettingScope

        mapper = self._mappers.get(section_id)
        if not mapper:
            return

        data = {
            "calibration_points": mapper.get_calibration_points(),
            "is_calibrated": mapper.is_calibrated,
            "calibration_error": mapper.calculate_calibration_error(),
        }

        row = self._db.query(Setting).filter(
            Setting.key == SETTING_KEY,
            Setting.scope_id == str(section_id),
        ).first()

        if row:
            row.value = json.dumps(data)
        else:
            row = Setting(
                key=SETTING_KEY,
                value=json.dumps(data),
                scope=SettingScope.SECTION,
                scope_id=str(section_id),
            )
            self._db.add(row)

        self._db.commit()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_mapper(self, section_id: int = 0) -> _FPM:
        """Get or create a mapper for a section."""
        if section_id not in self._mappers:
            self._mappers[section_id] = _FPM()
        return self._mappers[section_id]

    def add_calibration_point(self, section_id: int,
                               pixel_x: float, pixel_y: float,
                               real_x: float, real_y: float):
        """Add one calibration point and persist."""
        mapper = self.get_mapper(section_id)
        mapper.add_calibration_point(pixel_x, pixel_y, real_x, real_y)
        self._save(section_id)

    def pixel_to_real(self, pixel_x: float, pixel_y: float,
                      section_id: int = 0) -> Optional[Tuple[float, float]]:
        """Convert pixel coords → real-world meters."""
        mapper = self.get_mapper(section_id)
        return mapper.pixel_to_real(pixel_x, pixel_y)

    def real_to_pixel(self, real_x: float, real_y: float,
                      section_id: int = 0) -> Optional[Tuple[float, float]]:
        """Convert real-world meters → pixel coords."""
        mapper = self.get_mapper(section_id)
        return mapper.real_to_pixel(real_x, real_y)

    def is_calibrated(self, section_id: int = 0) -> bool:
        mapper = self._mappers.get(section_id)
        return mapper.is_calibrated if mapper else False

    def calibration_error(self, section_id: int = 0) -> Optional[float]:
        mapper = self._mappers.get(section_id)
        return mapper.calculate_calibration_error() if mapper else None

    def get_calibration_points(self, section_id: int = 0) -> List[Dict]:
        mapper = self._mappers.get(section_id)
        return mapper.get_calibration_points() if mapper else []

    def get_calibration_status(self) -> Dict:
        """Return calibration status for all sections."""
        from backend.models import Setting
        rows = self._db.query(Setting).filter(Setting.key == SETTING_KEY).all() if self._db else []
        status = {}
        for row in rows:
            sid = int(row.scope_id or 0)
            try:
                data = json.loads(row.value)
                status[sid] = {
                    "calibrated": data.get("is_calibrated", False),
                    "error": data.get("calibration_error"),
                    "points": len(data.get("calibration_points", [])),
                }
            except Exception:
                status[sid] = {"calibrated": False, "error": None, "points": 0}
        return status

    def create_simple_transform(self, section_id: int,
                                 image_width: float, image_height: float,
                                 real_width: float, real_height: float):
        """
        Quick setup: assumes image directly represents the real world.
        Uses 3-corner calibration (top-left, top-right, bottom-left).
        """
        mapper = _FPM()
        mapper.add_calibration_point(0, 0, 0, 0)
        mapper.add_calibration_point(image_width, 0, real_width, 0)
        mapper.add_calibration_point(0, image_height, 0, real_height)
        self._mappers[section_id] = mapper
        self._save(section_id)
        return mapper


# ── Singleton ─────────────────────────────────────────────────────────────────
_mapper_service: Optional[FloorPlanMapperService] = None


def get_floor_plan_mapper() -> FloorPlanMapperService:
    global _mapper_service
    if _mapper_service is None:
        from backend.extensions import db
        _mapper_service = FloorPlanMapperService(db.session)
    return _mapper_service
