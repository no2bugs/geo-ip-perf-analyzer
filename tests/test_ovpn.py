"""
E2E tests for /api/ovpn/status, /api/ovpn/upload, /api/ovpn/download,
/api/ovpn/config/<domain>, /api/geolite/status, and /api/geolite/update.
"""

import io
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock


# ===================================================================
# /api/ovpn/status
# ===================================================================

class TestOvpnStatus:

    def test_empty_dir(self, client, paths):
        resp = client.get("/api/ovpn/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["last_updated"] is None

    def test_with_files(self, client, paths):
        ovpn_dir = Path(paths["ovpn_dir"])
        (ovpn_dir / "server1.udp.ovpn").write_text("client\nremote server1 1194\n")
        (ovpn_dir / "server2.udp.ovpn").write_text("client\nremote server2 1194\n")

        resp = client.get("/api/ovpn/status")
        data = resp.get_json()
        assert data["count"] == 2
        assert data["last_updated"] is not None


# ===================================================================
# /api/ovpn/upload
# ===================================================================

class TestOvpnUpload:

    def _make_zip(self, files):
        """Create an in-memory ZIP with the given {name: content} dict."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buf.seek(0)
        return buf

    def test_upload_zip(self, client, paths):
        zf = self._make_zip({
            "configs/server1.udp.ovpn": "client\nremote s1 1194\n",
            "configs/server2.udp.ovpn": "client\nremote s2 1194\n",
            "configs/server3.tcp.ovpn": "client\nremote s3 443\n",  # TCP — skipped
        })
        resp = client.post("/api/ovpn/upload", data={
            "file": (zf, "configs.zip")
        }, content_type="multipart/form-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2  # only UDP

    def test_upload_non_zip(self, client):
        resp = client.post("/api/ovpn/upload", data={
            "file": (io.BytesIO(b"plaintext"), "file.txt")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_no_file(self, client):
        resp = client.post("/api/ovpn/upload")
        assert resp.status_code == 400

    def test_upload_path_traversal(self, client):
        """ZIP entries with '..' should be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0:")
        buf.seek(0)
        resp = client.post("/api/ovpn/upload", data={
            "file": (buf, "evil.zip")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_bad_zip(self, client):
        resp = client.post("/api/ovpn/upload", data={
            "file": (io.BytesIO(b"not a zip"), "broken.zip")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400


# ===================================================================
# /api/ovpn/config/<domain>
# ===================================================================

class TestOvpnConfig:

    def test_get_config(self, client, paths):
        ovpn_dir = Path(paths["ovpn_dir"])
        (ovpn_dir / "example.com.udp.ovpn").write_text("client\nremote example.com 1194\n")

        resp = client.get("/api/ovpn/config/example.com")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "remote example.com" in data["content"]

    def test_not_found(self, client):
        resp = client.get("/api/ovpn/config/nonexistent.com")
        assert resp.status_code == 404

    def test_invalid_domain(self, client):
        resp = client.get("/api/ovpn/config/server%20name%20with%20spaces")
        assert resp.status_code == 400

    def test_domain_traversal_rejected(self, client):
        """Domain with path separators is blocked by Flask routing (404) or sanitization (400)."""
        resp = client.get("/api/ovpn/config/..%2F..%2Fetc")
        assert resp.status_code in (400, 404)


# ===================================================================
# /api/ovpn/download
# ===================================================================

class TestOvpnDownload:

    def test_no_url(self, client, sample_config):
        resp = client.post("/api/ovpn/download", json={})
        assert resp.status_code == 400

    def test_download_success(self, client, paths):
        """Mock the HTTP download and ZIP extraction."""
        zf_buf = io.BytesIO()
        with zipfile.ZipFile(zf_buf, "w") as zf:
            zf.writestr("s1.udp.ovpn", "client\nremote s1\n")
        zf_buf.seek(0)

        mock_resp = MagicMock()
        mock_resp.content = zf_buf.read()
        mock_resp.raise_for_status = MagicMock()

        with patch("web.app.http_requests.get", return_value=mock_resp):
            resp = client.post("/api/ovpn/download", json={
                "url": "https://example.com/ovpn.zip"
            })
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1


# ===================================================================
# /api/geolite/status
# ===================================================================

class TestGeoliteStatus:

    def test_status_with_files(self, client, paths):
        # databases exist (created in fixture)
        mock_release = {
            "tag_name": "2026.03.20",
            "published_at": "2026-03-20T00:00:00Z",
            "assets": []
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_release
        mock_resp.raise_for_status = MagicMock()

        with patch("web.app.http_requests.get", return_value=mock_resp):
            resp = client.get("/api/geolite/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "city_last_modified" in data
        assert data["latest_release_tag"] == "2026.03.20"


# ===================================================================
# /api/geolite/update
# ===================================================================

class TestGeoliteUpdate:

    def test_update_success(self, client, paths):
        city_content = b"mock city db"
        country_content = b"mock country db"

        mock_release = {
            "assets": [
                {"name": "GeoLite2-City.mmdb", "browser_download_url": "https://example.com/city.mmdb"},
                {"name": "GeoLite2-Country.mmdb", "browser_download_url": "https://example.com/country.mmdb"},
            ]
        }

        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "releases" in url:
                resp.json.return_value = mock_release
            elif "city" in url:
                resp.iter_content = MagicMock(return_value=[city_content])
            elif "country" in url:
                resp.iter_content = MagicMock(return_value=[country_content])
            return resp

        with patch("web.app.http_requests.get", side_effect=fake_get):
            resp = client.post("/api/geolite/update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "GeoLite2-City.mmdb" in data["updated"]
        assert "GeoLite2-Country.mmdb" in data["updated"]
