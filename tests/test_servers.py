"""
E2E tests for /api/servers (GET and POST).
"""

import json


class TestGetServers:

    def test_no_file_returns_empty(self, client):
        resp = client.get("/api/servers")
        assert resp.status_code == 200
        assert resp.get_json()["servers"] == ""

    def test_returns_content(self, client, sample_servers, paths):
        resp = client.get("/api/servers")
        data = resp.get_json()
        assert "server1.example.com" in data["servers"]


class TestPostServers:

    def test_save_servers(self, client, paths):
        resp = client.post("/api/servers", json={
            "servers": "alpha.com\nbeta.com\ngamma.com\n"
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["count"] == 3

        with open(paths["servers"]) as f:
            content = f.read()
        assert "alpha.com" in content

    def test_deduplicates(self, client, paths):
        resp = client.post("/api/servers", json={
            "servers": "dup.com\ndup.com\ndup.com\n"
        })
        data = resp.get_json()
        assert data["count"] == 1

    def test_strips_blanks(self, client, paths):
        resp = client.post("/api/servers", json={
            "servers": "\n\n  a.com  \n\n  b.com  \n\n"
        })
        data = resp.get_json()
        assert data["count"] == 2

    def test_empty_input(self, client, paths):
        resp = client.post("/api/servers", json={"servers": ""})
        data = resp.get_json()
        assert data["count"] == 0
