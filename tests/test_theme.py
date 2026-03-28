"""
E2E tests for /api/theme, /api/wallpaper/*, and /api/origin.
"""

import io
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml


# ===================================================================
# /api/theme (GET/POST)
# ===================================================================

class TestGetTheme:

    def test_default_theme(self, client):
        resp = client.get("/api/theme")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["palette"] == "default"
        assert data["wallpaper"] == "none"
        assert "map_thresholds" in data

    def test_returns_saved_theme(self, client, paths, sample_config):
        sample_config["theme"]["palette"] = "midnight"
        with open(paths["config"], "w") as f:
            yaml.dump(sample_config, f)
        resp = client.get("/api/theme")
        assert resp.get_json()["palette"] == "midnight"


class TestPostTheme:

    def test_set_theme(self, client, sample_config):
        resp = client.post("/api/theme", json={
            "palette": "emerald",
            "wallpaper": "grid",
            "wallpaper_mode": "cover"
        })
        assert resp.status_code == 200

        resp = client.get("/api/theme")
        data = resp.get_json()
        assert data["palette"] == "emerald"
        assert data["wallpaper"] == "grid"
        assert data["wallpaper_mode"] == "cover"

    def test_invalid_palette_falls_back(self, client, sample_config):
        resp = client.post("/api/theme", json={"palette": "INVALID"})
        assert resp.status_code == 200
        data = client.get("/api/theme").get_json()
        assert data["palette"] == "default"

    def test_invalid_wallpaper_falls_back(self, client, sample_config):
        resp = client.post("/api/theme", json={"wallpaper": "INVALID"})
        assert resp.status_code == 200
        data = client.get("/api/theme").get_json()
        assert data["wallpaper"] == "none"

    def test_invalid_wallpaper_mode_falls_back(self, client, sample_config):
        resp = client.post("/api/theme", json={"wallpaper_mode": "STRETCH"})
        assert resp.status_code == 200
        data = client.get("/api/theme").get_json()
        assert data["wallpaper_mode"] == "tile"

    def test_map_thresholds_preserved(self, client, sample_config):
        thresholds = {
            "auto_color_latency": True,
            "latency": {"green": 30, "yellow": 100},
            "speed": {"red": 20, "yellow": 80}
        }
        resp = client.post("/api/theme", json={"map_thresholds": thresholds})
        assert resp.status_code == 200
        data = client.get("/api/theme").get_json()
        assert data["map_thresholds"]["auto_color_latency"] is True
        assert data["map_thresholds"]["latency"]["green"] == 30


# ===================================================================
# /api/wallpaper/upload + /api/wallpaper/custom + DELETE
# ===================================================================

class TestWallpaperUpload:

    def _make_image(self, filename="test.png", data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100):
        return (io.BytesIO(data), filename)

    def test_upload_success(self, client, sample_config):
        data, name = self._make_image()
        resp = client.post("/api/wallpaper/upload", data={
            "file": (data, name)
        }, content_type="multipart/form-data")
        assert resp.status_code == 200
        assert resp.get_json()["url"] == "/api/wallpaper/custom"

    def test_upload_wrong_extension(self, client, sample_config):
        resp = client.post("/api/wallpaper/upload", data={
            "file": (io.BytesIO(b"data"), "malware.exe")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_too_large(self, client, sample_config):
        big = b"\x00" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
        resp = client.post("/api/wallpaper/upload", data={
            "file": (io.BytesIO(big), "huge.png")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_no_file(self, client):
        resp = client.post("/api/wallpaper/upload")
        assert resp.status_code == 400

    def test_serve_custom(self, client, sample_config, paths):
        """Upload then serve."""
        data, name = self._make_image()
        client.post("/api/wallpaper/upload", data={
            "file": (data, name)
        }, content_type="multipart/form-data")

        resp = client.get("/api/wallpaper/custom")
        assert resp.status_code == 200

    def test_serve_no_custom(self, client):
        resp = client.get("/api/wallpaper/custom")
        assert resp.status_code == 404

    def test_delete_custom(self, client, sample_config, paths):
        data, name = self._make_image()
        client.post("/api/wallpaper/upload", data={
            "file": (data, name)
        }, content_type="multipart/form-data")

        resp = client.delete("/api/wallpaper/custom")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True

        # Theme should reset to none
        theme = client.get("/api/theme").get_json()
        assert theme["wallpaper"] == "none"

    def test_delete_nonexistent(self, client, sample_config):
        resp = client.delete("/api/wallpaper/custom")
        data = resp.get_json()
        assert data["deleted"] is False


# ===================================================================
# /api/wallpaper/video/*
# ===================================================================

class TestVideoWallpaper:

    def test_upload_video(self, client, sample_config):
        resp = client.post("/api/wallpaper/video/upload", data={
            "file": (io.BytesIO(b"\x00" * 500), "bg.mp4")
        }, content_type="multipart/form-data")
        assert resp.status_code == 200

    def test_upload_video_wrong_type(self, client, sample_config):
        resp = client.post("/api/wallpaper/video/upload", data={
            "file": (io.BytesIO(b"data"), "video.avi")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_video_too_large(self, client, sample_config):
        big = b"\x00" * (51 * 1024 * 1024)
        resp = client.post("/api/wallpaper/video/upload", data={
            "file": (io.BytesIO(big), "huge.mp4")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_serve_video_not_found(self, client):
        resp = client.get("/api/wallpaper/video")
        assert resp.status_code == 404

    def test_delete_video(self, client, sample_config):
        client.post("/api/wallpaper/video/upload", data={
            "file": (io.BytesIO(b"\x00" * 100), "v.mp4")
        }, content_type="multipart/form-data")
        resp = client.delete("/api/wallpaper/video")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True


# ===================================================================
# /api/origin
# ===================================================================

class TestOrigin:

    def test_origin_auto_cached(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setitem(state_mod._origin_cache, "auto", {
            "ip": "1.2.3.4",
            "lat": 52.52,
            "lon": 13.405,
            "country": "Germany",
            "city": "Berlin",
            "source": "auto"
        })
        resp = client.get("/api/origin")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "auto"
        assert data["lat"] == 52.52

    def test_origin_no_cache_error(self, client, monkeypatch):
        import web.state as state_mod
        monkeypatch.setitem(state_mod._origin_cache, "auto", None)
        monkeypatch.setitem(state_mod._origin_cache, "manual", None)
        resp = client.get("/api/origin")
        assert resp.status_code == 500
