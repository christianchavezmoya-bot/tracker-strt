"""Stress and scale smoke tests."""
import time


def test_tracker_list_300_tags(client, admin_headers, app):
    from backend.extensions import db
    from backend.models import Tracker
    from backend.models.tracker import TagType, DeviceCategory

    with app.app_context():
        batch = [
            Tracker(
                hardware_id=f"STRESS-{i:04d}",
                assigned_name=f"Tag {i}",
                tag_type=TagType.PERSONNEL,
                category=DeviceCategory.PERSONNEL_TAG,
                pos_x=float(i % 50),
                pos_y=float(i // 50),
            )
            for i in range(300)
        ]
        db.session.add_all(batch)
        db.session.commit()

    start = time.perf_counter()
    res = client.get("/api/trackers?per_page=500", headers=admin_headers)
    elapsed = time.perf_counter() - start

    assert res.status_code == 200
    data = res.get_json() or {}
    assert data.get("total", 0) >= 300
    assert elapsed < 5.0, f"Tracker list too slow: {elapsed:.2f}s"
