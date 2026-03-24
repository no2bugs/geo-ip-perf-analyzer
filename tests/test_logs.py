"""
E2E tests for /api/logs, /api/logs/clear, /api/logs/files, /api/logs/file/<name>.
"""

import os
from pathlib import Path


# ===================================================================
# /api/logs
# ===================================================================

class TestGetLogs:

    def test_no_log_file(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_parse_log_entries(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        with open(log_path, "w") as f:
            f.write("2026-03-20 10:00:00 [INFO] Scan started\n")
            f.write("2026-03-20 10:00:01 [WARNING] Slow response\n")
            f.write("2026-03-20 10:00:02 [ERROR] Connection timeout\n")
        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 3
        assert data[0]["level"] == "INFO"
        assert data[0]["timestamp"] == "10:00:00"
        assert data[2]["level"] == "ERROR"

    def test_continuation_lines(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        with open(log_path, "w") as f:
            f.write("2026-03-20 10:00:00 [ERROR] Traceback:\n")
            f.write("  File 'app.py', line 42\n")
            f.write("  ValueError: bad input\n")
        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 1
        assert "Traceback" in data[0]["message"]
        assert "ValueError" in data[0]["message"]

    def test_max_200_entries(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        with open(log_path, "w") as f:
            for i in range(300):
                f.write(f"2026-03-20 10:00:00 [INFO] Entry {i}\n")
        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 200


# ===================================================================
# /api/logs/clear
# ===================================================================

class TestClearLogs:

    def test_clear_truncates(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        with open(log_path, "w") as f:
            f.write("2026-03-20 10:00:00 [INFO] data\n" * 50)

        resp = client.post("/api/logs/clear")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cleared"

        assert os.path.getsize(log_path) == 0


# ===================================================================
# /api/logs/files
# ===================================================================

class TestLogFiles:

    def test_list_files(self, client, paths):
        # Create all expected log files
        for name in ["general.log", "error.log", "scan.log"]:
            with open(os.path.join(paths["log_dir"], name), "w") as f:
                f.write("test data\n")

        resp = client.get("/api/logs/files")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [f["name"] for f in data]
        assert "general" in names
        assert "error" in names
        assert "scan" in names

    def test_missing_files_zero_size(self, client, paths):
        resp = client.get("/api/logs/files")
        data = resp.get_json()
        for item in data:
            assert item["size"] == 0


# ===================================================================
# /api/logs/file/<name>
# ===================================================================

class TestGetLogFile:

    def test_get_general_log(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        lines = [f"Line {i}\n" for i in range(10)]
        with open(log_path, "w") as f:
            f.writelines(lines)

        resp = client.get("/api/logs/file/general")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 10
        assert len(data["lines"]) == 10

    def test_lines_param(self, client, paths):
        log_path = os.path.join(paths["log_dir"], "general.log")
        with open(log_path, "w") as f:
            for i in range(100):
                f.write(f"Line {i}\n")

        resp = client.get("/api/logs/file/general?lines=5")
        data = resp.get_json()
        assert len(data["lines"]) == 5
        assert data["total"] == 100

    def test_unknown_log_name(self, client):
        resp = client.get("/api/logs/file/nonexistent")
        assert resp.status_code == 404

    def test_missing_file_empty(self, client):
        resp = client.get("/api/logs/file/scan")
        data = resp.get_json()
        assert data["lines"] == []
        assert data["total"] == 0
