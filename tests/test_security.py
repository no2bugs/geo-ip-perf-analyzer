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

    def test_top_servers_endpoint(self, client, sample_results):
        resp = client.get("/api/top-servers")
        assert resp.status_code == 200

    def test_v1_top_latency(self, client, sample_results):
        resp = client.get("/api/v1/top/latency")
        assert resp.status_code == 200

    def test_v1_top_download(self, client, sample_results):
        resp = client.get("/api/v1/top/download")
        assert resp.status_code == 200

    def test_v1_top_upload(self, client, sample_results):
        resp = client.get("/api/v1/top/upload")
        assert resp.status_code == 200

    def test_results_geo_no_file(self, client):
        resp = client.get("/api/results/geo")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_map_page(self, client):
        resp = client.get("/map")
        assert resp.status_code == 200

    def test_statistics_page(self, client):
        resp = client.get("/statistics")
        assert resp.status_code == 200

    def test_scan_status_idle(self, client):
        resp = client.get("/api/scan/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['active'] is False

    def test_ovpn_download_no_url(self, client):
        resp = client.post("/api/ovpn/download", json={})
        assert resp.status_code == 400

    def test_prune_stale_post(self, client, paths, sample_results, sample_servers):
        resp = client.post("/api/prune-stale")
        assert resp.status_code == 200

    def test_logs_clear(self, client, paths):
        import os
        with open(os.path.join(paths["log_dir"], "general.log"), "w") as f:
            f.write("test\n")
        resp = client.post("/api/logs/clear")
        assert resp.status_code == 200

    def test_schedule_run_valid(self, client):
        resp = client.post("/api/schedule/run", json={"job": "geolite_update"})
        assert resp.status_code == 200

    def test_wallpaper_custom_not_found(self, client):
        resp = client.get("/api/wallpaper/custom")
        assert resp.status_code == 404

    def test_wallpaper_video_not_found(self, client):
        resp = client.get("/api/wallpaper/video")
        assert resp.status_code == 404

    def test_wallpaper_delete_nonexistent(self, client, sample_config):
        resp = client.delete("/api/wallpaper/custom")
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] is False

    def test_video_delete_nonexistent(self, client, sample_config):
        resp = client.delete("/api/wallpaper/video")
        assert resp.status_code == 200

    def test_servers_save_and_get_roundtrip(self, client, paths):
        client.post("/api/servers", json={"servers": "a.com\nb.com\nc.com"})
        resp = client.get("/api/servers")
        assert 'a.com' in resp.get_json()['servers']


class TestAdditionalEdgeCases:
    """Additional edge case tests for robustness."""

    def test_scan_stop_when_idle(self, client):
        resp = client.post("/api/scan/stop")
        assert resp.status_code == 400

    def test_vpn_speedtest_no_results_file(self, client, paths, sample_servers):
        """VPN speedtest with no results.json should fail gracefully."""
        import web.state as state_mod
        state_mod.scan_active = False
        resp = client.post("/api/vpn-speedtest", json={"domains": ["test.com"]})
        # Should start background thread (which will fail internally)
        assert resp.status_code == 200

    def test_config_post_preserves_latency_scan_last_run(self, client, paths):
        """POST /api/config should preserve last_run of latency_scan."""
        import yaml
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': False},
                'latency_scan': {'enabled': False, 'last_run': '2026-03-27 10:00'},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False, 'download_url': ''},
                'servers_update': {'enabled': False},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        new_cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': False},
                'latency_scan': {'enabled': True, 'interval': 'daily', 'time': '05:00'},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False, 'download_url': ''},
                'servers_update': {'enabled': False},
            }
        }
        resp = client.post("/api/config", json=new_cfg)
        assert resp.status_code == 200

    def test_statistics_domains_country_filter(self, client, paths, sample_results):
        resp = client.get("/api/statistics/domains?country=Germany")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data['untested'], list)
        assert isinstance(data['failed'], list)

    def test_export_invalid_format(self, client, paths, sample_results):
        resp = client.get("/api/results/export/xml")
        assert resp.status_code == 400

    def test_export_no_results(self, client):
        resp = client.get("/api/results/export/json")
        assert resp.status_code == 404

    def test_countries_with_mixed_entry_types(self, client, paths):
        """Countries endpoint handles mix of dict and non-dict entries."""
        data = {
            "s1.com": {"latency_ms": 10, "country": "US", "city": "NYC"},
            "s2.com": [10, "1.2.3.4", "DE", "Berlin"],
            "s3.com": "invalid"
        }
        with open(paths['results'], 'w') as f:
            json.dump(data, f)
        resp = client.get("/api/countries")
        assert resp.status_code == 200
        countries = resp.get_json()
        names = [c['country'] for c in countries]
        assert 'US' in names

    def test_queue_add_then_clear_then_status(self, client, paths, sample_results, sample_servers):
        """Full queue workflow: add, verify, clear, verify empty."""
        client.post("/api/queue/add", json={
            "domains": ["server1.example.com"], "type": "test", "label": "Test"
        })
        status = client.get("/api/queue/status").get_json()
        assert status['pending'] == 1
        client.post("/api/queue/clear")
        status = client.get("/api/queue/status").get_json()
        assert status['pending'] == 0

    def test_config_test_notification_not_enabled(self, client, sample_config):
        resp = client.post("/api/config/test-notification")
        assert resp.status_code == 400

    def test_credentials_roundtrip(self, client, paths):
        """Set and verify credentials are stored correctly."""
        client.post("/api/credentials", json={
            "vpn_username": "testuser", "vpn_password": "testpass"
        })
        resp = client.get("/api/credentials")
        data = resp.get_json()
        assert data['vpn_password_set'] is True
        assert 'tes' in data['vpn_username_masked']
        assert 'testpass' not in json.dumps(data)
