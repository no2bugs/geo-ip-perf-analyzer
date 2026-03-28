"""
E2E tests for input validation, security, and edge cases.
"""

import io
import json
import zipfile
from unittest.mock import patch, MagicMock


class TestInputValidation:
    """Verify parameter clamping and sanitization."""

    def test_scan_pings_clamped_high(self, client, paths):
        """pings=999 should be clamped to 20."""
        with open(paths["servers"], "w") as f:
            f.write("a.com\n")

        calls = []
        original_thread = __import__("threading").Thread

        class CapturingThread(original_thread):
            def __init__(self, *a, **kw):
                calls.append(kw.get("args", a))
                super().__init__(*a, **kw)
                self.daemon = True

            def start(self):
                pass  # don't actually start

        with patch("threading.Thread", CapturingThread):
            client.post("/api/scan/start", json={"pings": 999, "timeout": 1000, "workers": 10})

        # The thread args should have clamped pings to 20
        assert calls[0][0] == 20  # first arg = pings

    def test_scan_timeout_clamped_low(self, client, paths):
        with open(paths["servers"], "w") as f:
            f.write("a.com\n")

        calls = []
        original_thread = __import__("threading").Thread

        class CapturingThread(original_thread):
            def __init__(self, *a, **kw):
                calls.append(kw.get("args", a))
                super().__init__(*a, **kw)
                self.daemon = True

            def start(self):
                pass

        with patch("threading.Thread", CapturingThread):
            client.post("/api/scan/start", json={"pings": 1, "timeout": 0, "workers": 10})

        assert calls[0][1] == 100  # timeout clamped to 100

    def test_scan_workers_clamped(self, client, paths):
        with open(paths["servers"], "w") as f:
            f.write("a.com\n")

        calls = []
        original_thread = __import__("threading").Thread

        class CapturingThread(original_thread):
            def __init__(self, *a, **kw):
                calls.append(kw.get("args", a))
                super().__init__(*a, **kw)
                self.daemon = True

            def start(self):
                pass

        with patch("threading.Thread", CapturingThread):
            client.post("/api/scan/start", json={"pings": 1, "timeout": 1000, "workers": -5})

        assert calls[0][2] == 1  # workers clamped to 1


class TestCredentialSecurity:
    """Ensure credentials are never leaked."""

    def test_password_never_in_response(self, client, paths):
        client.post("/api/credentials", json={
            "vpn_username": "myuser",
            "vpn_password": "supersecretpassword"
        })
        resp = client.get("/api/credentials")
        raw = resp.data.decode()
        assert "supersecretpassword" not in raw
        assert "myuser" not in raw  # full username not exposed
        assert "myu***" in raw  # only masked version

    def test_config_no_password_leak(self, client, paths):
        client.post("/api/credentials", json={
            "vpn_username": "user",
            "vpn_password": "secret"
        })
        resp = client.get("/api/config")
        raw = resp.data.decode()
        assert "secret" not in raw


class TestOvpnSecurity:

    def test_path_traversal_in_domain(self, client):
        """Path traversal is blocked by Flask routing (404) or sanitization (400)."""
        resp = client.get("/api/ovpn/config/../../../etc/passwd")
        assert resp.status_code in (400, 404)

    def test_special_chars_in_domain(self, client):
        """Special chars in domain rejected by Flask routing or sanitization."""
        resp = client.get("/api/ovpn/config/<script>alert(1)</script>")
        assert resp.status_code in (400, 404)


class TestZipSecurity:

    def test_absolute_path_in_zip(self, client):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("/etc/crontab", "* * * * * evil")
        buf.seek(0)
        resp = client.post("/api/ovpn/upload", data={
            "file": (buf, "evil.zip")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_dotdot_in_zip(self, client):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("foo/../../../etc/shadow", "root:::")
        buf.seek(0)
        resp = client.post("/api/ovpn/upload", data={
            "file": (buf, "evil2.zip")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400


class TestWallpaperSecurity:

    def test_reject_exe(self, client, sample_config):
        resp = client.post("/api/wallpaper/upload", data={
            "file": (io.BytesIO(b"MZ"), "shell.exe")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_reject_html(self, client, sample_config):
        resp = client.post("/api/wallpaper/upload", data={
            "file": (io.BytesIO(b"<script>"), "xss.html")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400


class TestEdgeCases:

    def test_results_empty_object(self, client, paths):
        with open(paths["results"], "w") as f:
            json.dump({}, f)
        resp = client.get("/api/results")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_countries_empty_results(self, client, paths):
        with open(paths["results"], "w") as f:
            json.dump({}, f)
        resp = client.get("/api/countries")
        assert resp.get_json() == []

    def test_statistics_empty_results(self, client, paths):
        with open(paths["results"], "w") as f:
            json.dump({}, f)
        resp = client.get("/api/statistics")
        data = resp.get_json()
        assert data["countries"] == []

    def test_concurrent_config_writes(self, client, sample_config):
        """Multiple rapid config writes should not corrupt the file."""
        for i in range(10):
            resp = client.post("/api/theme", json={
                "palette": "midnight" if i % 2 == 0 else "default"
            })
            assert resp.status_code == 200

        resp = client.get("/api/theme")
        data = resp.get_json()
        assert data["palette"] in ("midnight", "default")

    def test_servers_unicode(self, client, paths):
        resp = client.post("/api/servers", json={
            "servers": "münchen.example.com\ntokyo.example.jp\n"
        })
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 2

    def test_results_non_dict_entries_skipped(self, client, paths):
        """Legacy list-format entries should not crash countries endpoint."""
        with open(paths["results"], "w") as f:
            json.dump({
                "old.server": [25.0, "1.2.3.4", "US", "NYC"],
                "new.server": {"latency_ms": 10, "ip": "5.6.7.8", "country": "DE", "city": "Berlin"}
            }, f)
        resp = client.get("/api/countries")
        assert resp.status_code == 200


# ===================================================================
# Smoke tests — every endpoint responds without 500
# ===================================================================

class TestSmokeEndpoints:
    """Minimal reachability checks for every API endpoint."""

    def test_get_results_no_file(self, client):
        assert client.get("/api/results").status_code == 200

    def test_export_json_with_data(self, client, sample_results):
        resp = client.get("/api/results/export/json")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_export_csv_with_data(self, client, sample_results):
        resp = client.get("/api/results/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_prune_stale_get_not_allowed(self, client):
        resp = client.get("/api/prune-stale")
        assert resp.status_code == 405

    def test_statistics_domains_with_data(self, client, sample_results):
        resp = client.get("/api/statistics/domains")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "untested" in body
        assert "failed" in body

    def test_server_history_endpoint(self, client, sample_results):
        resp = client.get("/api/server/server1.example.com/history")
        assert resp.status_code == 200

    def test_geolite_status(self, client):
        resp = client.get("/api/geolite/status")
        assert resp.status_code == 200

    def test_ovpn_status(self, client):
        resp = client.get("/api/ovpn/status")
        assert resp.status_code == 200

    def test_servers_get(self, client):
        resp = client.get("/api/servers")
        assert resp.status_code == 200

    def test_config_get(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_credentials_get(self, client):
        resp = client.get("/api/credentials")
        assert resp.status_code == 200

    def test_theme_get(self, client):
        resp = client.get("/api/theme")
        assert resp.status_code == 200

    def test_schedule_next(self, client):
        resp = client.get("/api/schedule/next")
        assert resp.status_code == 200

    def test_logs_get(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200

    def test_logs_files(self, client):
        resp = client.get("/api/logs/files")
        assert resp.status_code == 200

    def test_logs_file_general(self, client, paths):
        import os
        # Create a log file so the endpoint can read it
        with open(os.path.join(paths["log_dir"], "general.log"), "w") as f:
            f.write("2026-03-28 10:00:00 [INFO] test line\n")
        resp = client.get("/api/logs/file/general")
        assert resp.status_code == 200

    def test_logs_file_unknown(self, client):
        resp = client.get("/api/logs/file/nonexistent")
        assert resp.status_code == 404

    def test_queue_status_empty(self, client):
        resp = client.get("/api/queue/status")
        assert resp.status_code == 200

    def test_origin_endpoint(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setitem(state_mod._origin_cache, "auto", {
            "ip": "1.2.3.4", "lat": 0, "lon": 0, "country": "US", "city": "NYC", "source": "auto"
        })
        resp = client.get("/api/origin")
        assert resp.status_code == 200
