"""
E2E tests for /api/config, /api/config (POST), /api/config/test-notification,
/api/credentials, and /api/schedule/*.
"""

import json
from unittest.mock import patch, MagicMock

import yaml


# ===================================================================
# /api/config (GET/POST)
# ===================================================================

class TestGetConfig:

    def test_default_config_when_missing(self, client):
        """When config.yaml doesn't exist, returns DEFAULT_CONFIG."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "schedule" in data
        assert "notifications" in data

    def test_returns_saved_config(self, client, sample_config):
        resp = client.get("/api/config")
        data = resp.get_json()
        assert data["schedule"]["vpn_speedtest"]["enabled"] is False


class TestPostConfig:

    def test_save_config(self, client, paths, sample_config):
        new_cfg = sample_config.copy()
        new_cfg["schedule"]["vpn_speedtest"]["enabled"] = True
        new_cfg["schedule"]["vpn_speedtest"]["interval"] = "daily"
        new_cfg["schedule"]["vpn_speedtest"]["time"] = "05:00"

        resp = client.post("/api/config", json=new_cfg)
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

        with open(paths["config"]) as f:
            saved = yaml.safe_load(f)
        assert saved["schedule"]["vpn_speedtest"]["enabled"] is True

    def test_rejects_ovpn_enabled_without_url(self, client, sample_config):
        sample_config["schedule"]["ovpn_update"]["enabled"] = True
        sample_config["schedule"]["ovpn_update"]["download_url"] = ""
        resp = client.post("/api/config", json=sample_config)
        assert resp.status_code == 400

    def test_preserves_last_run(self, client, paths, sample_config):
        """POST config should keep existing last_run timestamps."""
        sample_config["schedule"]["vpn_speedtest"]["last_run"] = "2026-03-20 15:00"
        with open(paths["config"], "w") as f:
            yaml.dump(sample_config, f)

        # Post update without last_run
        new_cfg = {"schedule": {"vpn_speedtest": {"enabled": False, "interval": "daily", "time": "03:00"}}}
        resp = client.post("/api/config", json=new_cfg)
        assert resp.status_code == 200

        with open(paths["config"]) as f:
            saved = yaml.safe_load(f)
        assert saved["schedule"]["vpn_speedtest"]["last_run"] == "2026-03-20 15:00"

    def test_preserves_theme(self, client, paths, sample_config):
        """POST config should not overwrite theme (managed by /api/theme)."""
        resp = client.post("/api/config", json={"schedule": sample_config["schedule"]})
        assert resp.status_code == 200
        with open(paths["config"]) as f:
            saved = yaml.safe_load(f)
        assert saved["theme"]["palette"] == "default"

    def test_no_data_returns_400(self, client):
        resp = client.post("/api/config", content_type="application/json", data="")
        # Flask parses empty as None
        assert resp.status_code == 400


# ===================================================================
# /api/credentials
# ===================================================================

class TestCredentials:

    def test_get_credentials_no_env(self, client):
        resp = client.get("/api/credentials")
        data = resp.get_json()
        assert data["vpn_password_set"] is False
        assert data["vpn_username_masked"] == ""

    def test_set_and_get_credentials(self, client, paths):
        resp = client.post("/api/credentials", json={
            "vpn_username": "testuser",
            "vpn_password": "secret123"
        })
        assert resp.status_code == 200

        resp = client.get("/api/credentials")
        data = resp.get_json()
        assert data["vpn_password_set"] is True
        assert data["vpn_username_masked"] == "tes***"
        # Password should NOT be returned
        assert "vpn_password" not in data
        assert "secret123" not in json.dumps(data)

    def test_partial_update_username(self, client, paths):
        client.post("/api/credentials", json={"vpn_username": "user1", "vpn_password": "pass1"})
        client.post("/api/credentials", json={"vpn_username": "user2"})
        with open(paths["env"]) as f:
            content = f.read()
        assert "user2" in content
        assert "pass1" in content  # password preserved

    def test_no_credentials_400(self, client):
        resp = client.post("/api/credentials", json={})
        assert resp.status_code == 400


# ===================================================================
# /api/config/test-notification
# ===================================================================

class TestNotification:

    def test_not_enabled(self, client, sample_config):
        resp = client.post("/api/config/test-notification")
        assert resp.status_code == 400

    def test_enabled_success(self, client, paths, sample_config):
        sample_config["notifications"]["ntfy"]["enabled"] = True
        sample_config["notifications"]["ntfy"]["url"] = "https://ntfy.example.com/test"
        with open(paths["config"], "w") as f:
            yaml.dump(sample_config, f)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("web.app.http_requests.post", return_value=mock_resp) as mock_post:
            resp = client.post("/api/config/test-notification")
        assert resp.status_code == 200
        mock_post.assert_called_once()


# ===================================================================
# /api/schedule/run
# ===================================================================

class TestScheduleRun:

    def test_unknown_job(self, client):
        resp = client.post("/api/schedule/run", json={"job": "bogus"})
        assert resp.status_code == 400

    def test_valid_jobs(self, client):
        for job in ["vpn_speedtest", "geolite_update", "ovpn_update", "servers_update"]:
            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                resp = client.post("/api/schedule/run", json={"job": job})
                assert resp.status_code == 200, f"Failed for job={job}"


# ===================================================================
# /api/schedule/next
# ===================================================================

class TestScheduleNext:

    def test_returns_dict(self, client):
        resp = client.get("/api/schedule/next")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), dict)


# ===================================================================
# Config robustness
# ===================================================================

class TestConfigRobustness:

    def test_missing_new_schedule_key_default(self, client, paths):
        """If saved config is missing a new schedule key, defaults fill in."""
        import yaml
        partial = {"schedule": {"vpn_speedtest": {"enabled": True, "interval": "daily", "time": "05:00"}}}
        with open(paths["config"], "w") as f:
            yaml.dump(partial, f)
        resp = client.get("/api/config")
        cfg = resp.get_json()
        # latency_scan should exist with defaults even though not in saved config
        assert "latency_scan" in cfg["schedule"]
        assert cfg["schedule"]["latency_scan"]["enabled"] is False

    def test_corrupt_config_falls_back(self, client, paths):
        """A corrupt YAML file should fall back to defaults gracefully."""
        with open(paths["config"], "w") as f:
            f.write(": invalid: yaml: {{{\n")
        resp = client.get("/api/config")
        assert resp.status_code == 200
        cfg = resp.get_json()
        assert "schedule" in cfg
