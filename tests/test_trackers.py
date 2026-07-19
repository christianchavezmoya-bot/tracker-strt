"""
HOLO-RTLS — Tracker CRUD Tests
"""
import pytest


class TestTrackerCRUD:
    def test_create_tracker(self, client, admin_headers):
        resp = client.post("/api/trackers", json={
            "hardware_id": "PRN-001",
            "assigned_name": "John Doe",
            "tag_type": 1,
            "category": 1,
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["tracker"]["hardware_id"] == "PRN-001"
        assert data["tracker"]["assigned_name"] == "John Doe"

    def test_create_duplicate_hardware_id(self, client, admin_headers):
        client.post("/api/trackers", json={"hardware_id": "PRN-002", "assigned_name": "A"}, headers=admin_headers)
        resp = client.post("/api/trackers", json={"hardware_id": "PRN-002", "assigned_name": "B"}, headers=admin_headers)
        assert resp.status_code == 409

    def test_list_trackers(self, client, admin_headers):
        # Create a few trackers
        for i in range(3):
            client.post("/api/trackers", json={
                "hardware_id": f"PRN-{i:03d}",
                "assigned_name": f"Tag {i}",
            }, headers=admin_headers)
        resp = client.get("/api/trackers", headers=admin_headers)
        data = resp.get_json()
        assert data["total"] >= 3

    def test_list_trackers_filter_by_category(self, client, admin_headers):
        client.post("/api/trackers", json={"hardware_id": "PRN-010", "category": 1}, headers=admin_headers)
        client.post("/api/trackers", json={"hardware_id": "PRN-020", "category": 2}, headers=admin_headers)
        resp = client.get("/api/trackers?category=1", headers=admin_headers)
        data = resp.get_json()
        for t in data["items"]:
            assert t["category"] == "PERSONNEL_TAG"

    def test_get_tracker(self, client, admin_headers):
        create_resp = client.post("/api/trackers", json={"hardware_id": "PRN-030"}, headers=admin_headers)
        tracker_id = create_resp.get_json()["tracker"]["id"]
        resp = client.get(f"/api/trackers/{tracker_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["tracker"]["hardware_id"] == "PRN-030"

    def test_update_tracker(self, client, admin_headers):
        create_resp = client.post("/api/trackers", json={"hardware_id": "PRN-040"}, headers=admin_headers)
        tracker_id = create_resp.get_json()["tracker"]["id"]
        resp = client.patch(f"/api/trackers/{tracker_id}", json={
            "assigned_name": "Updated Name",
            "asset_state": 2,   # OFFLINE
        }, headers=admin_headers)
        data = resp.get_json()
        assert data["tracker"]["assigned_name"] == "Updated Name"
        assert data["tracker"]["asset_state"] == "OFFLINE"

    def test_reassign_tracker(self, client, admin_headers):
        create_resp = client.post("/api/trackers", json={"hardware_id": "PRN-050"}, headers=admin_headers)
        tracker_id = create_resp.get_json()["tracker"]["id"]
        resp = client.post(f"/api/trackers/{tracker_id}/reassign", json={
            "hardware_id": "PRN-050-NEW",
        }, headers=admin_headers)
        data = resp.get_json()
        assert data["tracker"]["hardware_id"] == "PRN-050-NEW"

    def test_delete_tracker(self, client, admin_headers):
        create_resp = client.post("/api/trackers", json={"hardware_id": "PRN-060"}, headers=admin_headers)
        tracker_id = create_resp.get_json()["tracker"]["id"]
        resp = client.delete(f"/api/trackers/{tracker_id}", headers=admin_headers)
        assert resp.status_code == 200
        # Confirm deleted
        get_resp = client.get(f"/api/trackers/{tracker_id}", headers=admin_headers)
        assert get_resp.status_code == 404

    def test_viewer_cannot_create_tracker(self, client, viewer_headers):
        """VIEWER role cannot create trackers."""
        resp = client.post("/api/trackers", json={
            "hardware_id": "PRN-070",
        }, headers=viewer_headers)
        assert resp.status_code == 403

    def test_search_trackers(self, client, admin_headers):
        client.post("/api/trackers", json={"hardware_id": "SEARCH-001", "assigned_name": "Alice"}, headers=admin_headers)
        resp = client.get("/api/trackers?q=alice", headers=admin_headers)
        data = resp.get_json()
        assert any("alice" in t["assigned_name"].lower() for t in data["items"] if t["assigned_name"])
