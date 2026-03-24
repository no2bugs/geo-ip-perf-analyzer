"""
E2E tests for HTML page rendering.
"""


class TestHTMLPages:
    """All six page routes should return 200 with expected HTML."""

    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

    def test_config(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200

    def test_help(self, client):
        resp = client.get("/help")
        assert resp.status_code == 200

    def test_logs(self, client):
        resp = client.get("/logs")
        assert resp.status_code == 200

    def test_map(self, client):
        resp = client.get("/map")
        assert resp.status_code == 200

    def test_statistics(self, client):
        resp = client.get("/statistics")
        assert resp.status_code == 200

    def test_nonexistent_page_404(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
