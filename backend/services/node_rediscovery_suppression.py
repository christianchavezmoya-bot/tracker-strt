from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.extensions import db
from backend.models import Setting, SettingScope


SUPPRESSION_KEY = "mqtt_node_purge_suppressions"
QUIET_WINDOW_SECONDS = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _load_state(session=None) -> dict:
    sess = session or db.session
    row = sess.query(Setting).filter_by(key=SUPPRESSION_KEY).first()
    if not row:
        return {}
    try:
        value = row.get_typed_value()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict, session=None) -> None:
    sess = session or db.session
    row = sess.query(Setting).filter_by(key=SUPPRESSION_KEY).first()
    if not row:
        row = Setting(
            key=SUPPRESSION_KEY,
            scope=int(SettingScope.SYSTEM),
            label="MQTT purge suppressions",
            description="Temporary suppressions for purged MQTT anchors until they go quiet.",
        )
        sess.add(row)
    row.set_typed_value(state or {})


def suppress_node_rediscovery(
    *,
    node_key: str,
    node_ip: str | None = None,
    aliases: list[str] | None = None,
    session=None,
) -> None:
    sess = session or db.session
    state = _load_state(sess)
    now_iso = _utc_now().isoformat()
    for key in [node_key, *(aliases or [])]:
        if key:
            state[f"key:{str(key).upper()}"] = {"purged_at": now_iso, "last_seen_at": None}
    if node_ip:
        state[f"ip:{node_ip}"] = {"purged_at": now_iso, "last_seen_at": None}
    _save_state(state, sess)


def should_suppress_node(
    *,
    node_key: str,
    node_ip: str | None = None,
    session=None,
) -> bool:
    """
    Suppress rediscovery until the unit has gone quiet for QUIET_WINDOW_SECONDS.
    Continuous traffic keeps suppression active; a later fresh burst clears it.
    """
    sess = session or db.session
    state = _load_state(sess)
    if not state:
        return False

    keys = []
    if node_key:
        keys.append(f"key:{str(node_key).upper()}")
    if node_ip:
        keys.append(f"ip:{node_ip}")

    now = _utc_now()
    quiet_cutoff = now - timedelta(seconds=QUIET_WINDOW_SECONDS)
    matched = False
    changed = False

    for key in keys:
        entry = state.get(key)
        if not isinstance(entry, dict):
            continue
        matched = True
        last_seen = _parse_iso(entry.get("last_seen_at"))
        if last_seen and last_seen < quiet_cutoff:
            state.pop(key, None)
            changed = True
            continue
        entry["last_seen_at"] = now.isoformat()
        state[key] = entry
        changed = True

    if changed:
        _save_state(state, sess)
    return matched
