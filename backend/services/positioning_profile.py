from __future__ import annotations

from backend.models.settings import Setting

POSITIONING_PROFILE_DEFS = {
    "open_space": {
        "id": "open_space",
        "label": "Open space",
        "positioning_mode": "free_2d",
        "min_anchors": 3,
        "quality_state": "exact",
        "description": "Use 3 or more anchors for general 2D positioning.",
        "allows_two_anchor_linear": False,
    },
    "tunnel": {
        "id": "tunnel",
        "label": "Tunnel / corridor",
        "positioning_mode": "linear",
        "min_anchors": 2,
        "quality_state": "approximate",
        "description": "Allow 2-anchor linear positioning along constrained paths.",
        "allows_two_anchor_linear": True,
    },
    "adaptive": {
        "id": "adaptive",
        "label": "Adaptive",
        "positioning_mode": "adaptive",
        "min_anchors": 2,
        "quality_state": "approximate",
        "description": "Use 3-anchor free-space positioning when available, otherwise fall back to 2-anchor linear mode.",
        "allows_two_anchor_linear": True,
    },
}

DEFAULT_POSITIONING_PROFILE = "open_space"
SETTING_KEY = "positioning_application_profile"


def get_positioning_profile(session) -> dict:
    profile_id = DEFAULT_POSITIONING_PROFILE
    try:
        row = session.query(Setting).filter_by(key=SETTING_KEY).first()
        if row and row.value:
            candidate = str(row.value).strip().lower()
            if candidate in POSITIONING_PROFILE_DEFS:
                profile_id = candidate
    except Exception:
        pass
    return dict(POSITIONING_PROFILE_DEFS.get(profile_id, POSITIONING_PROFILE_DEFS[DEFAULT_POSITIONING_PROFILE]))
