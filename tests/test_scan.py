"""
E2E tests for /api/scan/start, /api/scan/status, /api/scan/stop,
/api/vpn-speedtest, and /api/queue/*.
"""

import json
import time
from unittest.mock import patch, MagicMock


# ===================================================================
# /api/scan/start
# ===================================================================

class TestScanStart:

    def test_missing_servers_file(self, client):
        resp = client.post("/api/scan/start", json={})
        assert resp.status_code == 400
        assert "missing" in resp.get_json()["message"].lower()

    def test_empty_servers_file(self, client, paths):
        with open(paths["servers"], "w") as f:
            f.write("")
        resp = client.post("/api/scan/start", json={})
        assert resp.status_code == 400
        assert "empty" in resp.get_json()["message"].lower()

    def test_start_scan_success(self, client, sample_servers):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            mock_thread.return_value.daemon = True
            resp = client.post("/api/scan/start", json={
                "pings": 3, "timeout": 500, "workers": 5
            })
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "started"

    def test_scan_already_running(self, client, sample_servers, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        resp = client.post("/api/scan/start", json={})
        assert resp.status_code == 409

    def test_params_clamped(self, client, sample_servers):
        """Extreme params should be clamped to valid ranges."""
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/scan/start", json={
                "pings": 999,
                "timeout": 0,
                "workers": -10
            })
        assert resp.status_code == 200


# ===================================================================
# /api/scan/status
# ===================================================================

class TestScanStatus:

    def test_idle_status(self, client):
        resp = client.get("/api/scan/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active"] is False

    def test_active_status(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        monkeypatch.setattr(state_mod, "scan_progress", {
            "done": 5, "total": 10, "status": "running", "message": "Scanning..."
        })
        resp = client.get("/api/scan/status")
        data = resp.get_json()
        assert data["active"] is True


# ===================================================================
# /api/scan/stop
# ===================================================================

class TestScanStop:

    def test_stop_no_scan(self, client):
        resp = client.post("/api/scan/stop")
        assert resp.status_code == 400

    def test_stop_active_scan(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        resp = client.post("/api/scan/stop")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "stopping"


# ===================================================================
# /api/vpn-speedtest
# ===================================================================

class TestVpnSpeedtest:

    def test_conflict_when_scan_running(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        resp = client.post("/api/vpn-speedtest", json={"domains": ["a.com"]})
        assert resp.status_code == 409

    def test_start_vpn_speedtest(self, client, sample_results):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            mock_thread.return_value.daemon = True
            resp = client.post("/api/vpn-speedtest", json={
                "domains": ["server1.example.com"]
            })
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "started"


# ===================================================================
# /api/queue/*
# ===================================================================

class TestQueue:

    def test_queue_status_empty(self, client):
        resp = client.get("/api/queue/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pending"] == 0

    def test_queue_add(self, client, monkeypatch):
        # Prevent the queue processor from actually starting
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        resp = client.post("/api/queue/add", json={
            "domains": ["a.com", "b.com"],
            "type": "untested",
            "label": "Test batch"
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "queued"
        assert data["pending"] == 1

    def test_queue_add_empty(self, client):
        resp = client.post("/api/queue/add", json={"domains": []})
        assert resp.status_code == 400

    def test_queue_clear(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        # Add jobs
        client.post("/api/queue/add", json={"domains": ["x.com"], "type": "test", "label": "a"})
        client.post("/api/queue/add", json={"domains": ["y.com"], "type": "test", "label": "b"})

        resp = client.post("/api/queue/clear")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["removed"] == 2

        # Verify queue is empty
        resp = client.get("/api/queue/status")
        assert resp.get_json()["pending"] == 0

    def test_queue_status_after_add(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        client.post("/api/queue/add", json={"domains": ["a.com", "b.com", "c.com"], "type": "untested", "label": "Batch"})
        resp = client.get("/api/queue/status")
        data = resp.get_json()
        assert data["pending"] == 1
        assert data["total_domains"] == 3

    def test_queue_fifo_order(self, client, monkeypatch):
        """Jobs are returned in FIFO (insertion) order."""
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        client.post("/api/queue/add", json={"domains": ["a.com"], "type": "t", "label": "first"})
        client.post("/api/queue/add", json={"domains": ["b.com", "c.com"], "type": "t", "label": "second"})
        resp = client.get("/api/queue/status")
        jobs = resp.get_json()["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["label"] == "first"
        assert jobs[1]["label"] == "second"

    def test_queue_add_while_scan_active(self, client, monkeypatch):
        """Adding to queue should work even if a scan is active."""
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        resp = client.post("/api/queue/add", json={"domains": ["x.com"], "type": "t", "label": "L"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "queued"

    def test_queue_clear_does_not_stop_active(self, client, monkeypatch):
        """Clear should remove pending items but not affect scan_active."""
        import web.state as state_mod
        monkeypatch.setattr(state_mod, "scan_active", True)
        monkeypatch.setattr(state_mod, "_ensure_queue_processor", lambda: None)

        client.post("/api/queue/add", json={"domains": ["a.com"], "type": "t", "label": "L"})
        resp = client.post("/api/queue/clear")
        assert resp.status_code == 200
        assert state_mod.scan_active is True
