"""
Shared fixtures for geo-ip-perf-analyzer E2E tests.

All file paths are redirected to a temporary directory so tests
never touch production data.  External HTTP calls and GeoIP lookups
are mocked to keep the suite fast and deterministic.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Temp workspace that mirrors the layout the app expects
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path, monkeypatch):
    """Redirect every file-path constant the app uses into *tmp_path*."""

    results_file = str(tmp_path / "results.json")
    servers_file = str(tmp_path / "servers.list")
    config_file = str(tmp_path / "config.yaml")
    env_file = str(tmp_path / ".env")
    city_db = str(tmp_path / "GeoLite2-City.mmdb")
    country_db = str(tmp_path / "GeoLite2-Country.mmdb")
    ovpn_dir = str(tmp_path / "ovpn")
    wallpaper_dir = str(tmp_path / "wallpapers")
    log_dir = str(tmp_path / "logs")
    scan_state = str(tmp_path / "scan_state.json")
    queue_state = str(tmp_path / "queue_state.json")

    os.makedirs(ovpn_dir, exist_ok=True)
    os.makedirs(wallpaper_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # Create minimal placeholder "GeoIP databases" (just empty files; reader is mocked)
    Path(city_db).touch()
    Path(country_db).touch()

    import web.state as state_mod

    monkeypatch.setattr(state_mod, "RESULTS_FILE", results_file)
    monkeypatch.setattr(state_mod, "SERVERS_FILE", servers_file)
    monkeypatch.setattr(state_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(state_mod, "ENV_FILE", env_file)
    monkeypatch.setattr(state_mod, "GEOIP_CITY", city_db)
    monkeypatch.setattr(state_mod, "GEOIP_COUNTRY", country_db)
    monkeypatch.setattr(state_mod, "VPN_OVPN_DIR", ovpn_dir)
    monkeypatch.setattr(state_mod, "WALLPAPER_DIR", wallpaper_dir)
    monkeypatch.setattr(state_mod, "LOG_DIR", log_dir)
    monkeypatch.setattr(state_mod, "SCAN_STATE_FILE", scan_state)
    monkeypatch.setattr(state_mod, "QUEUE_STATE_FILE", queue_state)

    # Reset global scan state between tests
    monkeypatch.setattr(state_mod, "scan_active", False)
    monkeypatch.setattr(state_mod, "scan_progress", {"done": 0, "total": 0, "status": "idle", "message": ""})
    monkeypatch.setattr(state_mod, "last_error", None)
    monkeypatch.setattr(state_mod, "scan_start_time", None)
    state_mod.stop_event.clear()
    monkeypatch.setattr(state_mod, "_queue_processor_started", False)
    monkeypatch.setattr(state_mod, "_queue_active_job", None)

    # Expose paths for use by individual tests
    monkeypatch.setattr(state_mod, "_test_paths", {
        "results": results_file,
        "servers": servers_file,
        "config": config_file,
        "env": env_file,
        "city_db": city_db,
        "country_db": country_db,
        "ovpn_dir": ovpn_dir,
        "wallpaper_dir": wallpaper_dir,
        "log_dir": log_dir,
    }, raising=False)

    yield


@pytest.fixture()
def client():
    """Flask test client."""
    from web.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Convenience helpers for writing test data files
# ---------------------------------------------------------------------------

@pytest.fixture()
def paths():
    """Return the redirected path dict (set by _isolated_workspace)."""
    import web.state as state_mod
    return state_mod._test_paths


@pytest.fixture()
def sample_results(paths):
    """Write a realistic results.json and return the dict."""
    data = {
        "server1.example.com": {
            "latency_ms": 25.4,
            "ip": "93.184.216.34",
            "country": "United States",
            "city": "Los Angeles",
            "rx_speed_mbps": 120.5,
            "tx_speed_mbps": 45.2,
            "scan_timestamp": "2026-03-20T10:00:00",
            "speedtest_timestamp": "2026-03-20T10:05:00"
        },
        "server2.example.com": {
            "latency_ms": 42.1,
            "ip": "198.51.100.1",
            "country": "Germany",
            "city": "Frankfurt",
            "rx_speed_mbps": 85.3,
            "tx_speed_mbps": 30.7,
            "scan_timestamp": "2026-03-20T10:00:00",
            "speedtest_timestamp": "2026-03-20T10:06:00"
        },
        "server3.example.com": {
            "latency_ms": 15.0,
            "ip": "203.0.113.50",
            "country": "United States",
            "city": "New York",
            "rx_speed_mbps": None,
            "tx_speed_mbps": None,
            "scan_timestamp": "2026-03-20T10:00:00",
            "speedtest_timestamp": None
        },
        "server4.example.com": {
            "latency_ms": 60.0,
            "ip": "192.0.2.10",
            "country": "Germany",
            "city": "Berlin",
            "rx_speed_mbps": 0,
            "tx_speed_mbps": 0,
            "scan_timestamp": "2026-03-20T10:00:00",
            "speedtest_timestamp": "2026-03-20T10:08:00",
            "speedtest_failed_timestamp": "2026-03-20T10:10:00",
            "speedtest_failed_reason": "vpn_failed"
        }
    }
    with open(paths["results"], "w") as f:
        json.dump(data, f)
    return data


@pytest.fixture()
def sample_servers(paths):
    """Write a servers.list and return the domain list."""
    domains = ["server1.example.com", "server2.example.com", "server3.example.com", "server4.example.com"]
    with open(paths["servers"], "w") as f:
        f.write("\n".join(domains) + "\n")
    return domains


@pytest.fixture()
def sample_config(paths):
    """Write a minimal config.yaml and return the dict."""
    cfg = {
        "schedule": {
            "vpn_speedtest": {"enabled": False, "interval": "daily", "time": "03:00"},
            "geolite_update": {"enabled": False, "interval": "weekly", "day": "sunday", "time": "04:00"},
            "ovpn_update": {"enabled": False, "interval": "weekly", "day": "sunday", "time": "05:00", "download_url": ""},
            "servers_update": {"enabled": False, "interval": "weekly", "day": "sunday", "time": "06:00", "commands": []},
        },
        "notifications": {
            "ntfy": {"enabled": False, "url": "", "events": {}}
        },
        "theme": {
            "palette": "default",
            "wallpaper": "none",
            "wallpaper_mode": "tile",
            "map_thresholds": {
                "auto_color_latency": False,
                "auto_color_speed": False,
                "show_all_servers": False,
                "latency": {"green": 50, "yellow": 150},
                "speed": {"red": 50, "yellow": 200}
            }
        }
    }
    with open(paths["config"], "w") as f:
        yaml.dump(cfg, f)
    return cfg
