"""
E2E tests for /api/results, /api/results/export, /api/countries, /api/results/geo, /api/top-servers,
/api/statistics, /api/statistics/domains, /api/prune-stale, and /api/v1/top/* endpoints.
"""

import json
from unittest.mock import MagicMock, patch


# ===================================================================
# /api/results
# ===================================================================

class TestResults:

    def test_no_results_file_returns_empty(self, client):
        resp = client.get("/api/results")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_returns_results(self, client, sample_results):
        resp = client.get("/api/results")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "server1.example.com" in data
        assert data["server1.example.com"]["latency_ms"] == 25.4

    def test_malformed_json(self, client, paths):
        with open(paths["results"], "w") as f:
            f.write("NOT JSON")
        resp = client.get("/api/results")
        assert resp.status_code == 500


# ===================================================================
# /api/results/export/<fmt>
# ===================================================================

class TestExportResults:

    def test_invalid_format(self, client):
        resp = client.get("/api/results/export/xml")
        assert resp.status_code == 400

    def test_no_results_file_returns_404(self, client):
        resp = client.get("/api/results/export/csv")
        assert resp.status_code == 404

    def test_export_json(self, client, sample_results):
        resp = client.get("/api/results/export/json")
        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        data = json.loads(resp.data)
        assert "server1.example.com" in data

    def test_export_csv(self, client, sample_results):
        resp = client.get("/api/results/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        text = resp.data.decode()
        assert "Domain" in text
        assert "server1.example.com" in text


# ===================================================================
# /api/countries
# ===================================================================

class TestCountries:

    def test_no_results_empty_list(self, client):
        resp = client.get("/api/countries")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_aggregates_countries(self, client, sample_results):
        resp = client.get("/api/countries")
        data = resp.get_json()
        countries = {item["country"]: item["count"] for item in data}
        assert countries["United States"] == 2
        assert countries["Germany"] == 2


# ===================================================================
# /api/results/geo (requires GeoIP mock)
# ===================================================================

class TestResultsGeo:

    def test_no_results_file(self, client):
        resp = client.get("/api/results/geo")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_results_geo_with_mock_reader(self, client, sample_results, paths):
        """Mock the geoip2 Reader so we don't need real .mmdb files."""
        mock_geo = MagicMock()
        mock_geo.location.latitude = 34.05
        mock_geo.location.longitude = -118.25

        mock_reader_instance = MagicMock()
        mock_reader_instance.city.return_value = mock_geo
        mock_reader_instance.__enter__ = lambda s: s
        mock_reader_instance.__exit__ = MagicMock(return_value=False)

        with patch("geoip2.database.Reader", return_value=mock_reader_instance):
            resp = client.get("/api/results/geo")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert data[0]["lat"] == 34.05

    def test_results_geo_missing_city_db(self, client, sample_results, paths):
        import os
        os.remove(paths["city_db"])
        resp = client.get("/api/results/geo")
        assert resp.status_code == 500


# ===================================================================
# /api/top-servers
# ===================================================================

class TestTopServers:

    def test_no_results(self, client):
        resp = client.get("/api/top-servers")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_top_servers_default_n(self, client, sample_results):
        resp = client.get("/api/top-servers")
        data = resp.get_json()
        # Should return best per country (server1=US 120.5, server2=DE 85.3)
        assert len(data) == 2
        # Sorted by rx_speed desc
        assert data[0]["rx_speed_mbps"] > data[1]["rx_speed_mbps"]

    def test_top_servers_n_param(self, client, sample_results):
        resp = client.get("/api/top-servers?n=1")
        data = resp.get_json()
        assert len(data) == 1

    def test_top_servers_n_clamped(self, client, sample_results):
        """n is clamped to [1, 100]."""
        resp = client.get("/api/top-servers?n=-5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1  # clamped to 1


# ===================================================================
# /api/statistics
# ===================================================================

class TestStatistics:

    def test_no_results(self, client):
        resp = client.get("/api/statistics")
        data = resp.get_json()
        assert data["countries"] == []

    def test_statistics_shape(self, client, sample_results):
        resp = client.get("/api/statistics")
        data = resp.get_json()
        assert "countries" in data
        assert "top" in data
        assert "total_countries" in data
        countries = data["countries"]
        assert len(countries) == 2  # US and Germany
        us = next(c for c in countries if c["country"] == "United States")
        assert us["servers"] == 2
        assert us["lowest_latency"] == 15.0

    def test_statistics_top_param(self, client, sample_results):
        resp = client.get("/api/statistics?top=1")
        data = resp.get_json()
        assert len(data["top"]) <= 1


# ===================================================================
# /api/statistics/domains
# ===================================================================

class TestStatisticsDomains:

    def test_no_results(self, client):
        resp = client.get("/api/statistics/domains")
        data = resp.get_json()
        assert data == {"untested": [], "failed": []}

    def test_classifies_domains(self, client, sample_results):
        resp = client.get("/api/statistics/domains")
        data = resp.get_json()
        assert "server3.example.com" in data["untested"]  # no speedtest_timestamp
        assert "server4.example.com" in data["failed"]  # has timestamp but rx=0

    def test_country_filter(self, client, sample_results):
        resp = client.get("/api/statistics/domains?country=Germany")
        data = resp.get_json()
        assert "server3.example.com" not in data["untested"]
        assert "server4.example.com" in data["failed"]


# ===================================================================
# /api/prune-stale
# ===================================================================

class TestPruneStale:

    def test_prune_removes_stale(self, client, sample_results, paths):
        """Write a servers.list with only 2 of the 4 servers — prune should remove 2."""
        with open(paths["servers"], "w") as f:
            f.write("server1.example.com\nserver2.example.com\n")

        resp = client.post("/api/prune-stale")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Removed 2" in data["message"]

        with open(paths["results"]) as f:
            remaining = json.load(f)
        assert len(remaining) == 2
        assert "server3.example.com" not in remaining

    def test_prune_nothing_stale(self, client, sample_results, sample_servers):
        resp = client.post("/api/prune-stale")
        data = resp.get_json()
        assert "No stale" in data["message"]

    def test_prune_empty_servers_list(self, client, sample_results, paths):
        with open(paths["servers"], "w") as f:
            f.write("")
        resp = client.post("/api/prune-stale")
        assert resp.status_code == 400

    def test_prune_no_servers_file(self, client, sample_results):
        resp = client.post("/api/prune-stale")
        assert resp.status_code == 400


# ===================================================================
# /api/v1/top/latency
# ===================================================================

class TestV1TopLatency:

    def test_no_results(self, client):
        resp = client.get("/api/v1/top/latency")
        assert resp.get_json() == []

    def test_sorted_by_latency_asc(self, client, sample_results):
        resp = client.get("/api/v1/top/latency")
        data = resp.get_json()
        latencies = [d["latency_ms"] for d in data]
        assert latencies == sorted(latencies)

    def test_n_param(self, client, sample_results):
        resp = client.get("/api/v1/top/latency?n=2")
        assert len(resp.get_json()) == 2

    def test_country_filter(self, client, sample_results):
        resp = client.get("/api/v1/top/latency?country=Germany")
        data = resp.get_json()
        assert all(d["country"] == "Germany" for d in data)

    def test_country_filter_multi(self, client, sample_results):
        resp = client.get("/api/v1/top/latency?country=Germany,United States")
        data = resp.get_json()
        assert len(data) == 4


# ===================================================================
# /api/v1/top/download
# ===================================================================

class TestV1TopDownload:

    def test_sorted_desc(self, client, sample_results):
        resp = client.get("/api/v1/top/download")
        data = resp.get_json()
        speeds = [d["rx_speed_mbps"] for d in data]
        assert speeds == sorted(speeds, reverse=True)

    def test_excludes_null_rx(self, client, sample_results):
        """server3 has rx_speed_mbps=None — should be excluded."""
        resp = client.get("/api/v1/top/download")
        domains = [d["domain"] for d in resp.get_json()]
        assert "server3.example.com" not in domains


# ===================================================================
# /api/v1/top/upload
# ===================================================================

class TestV1TopUpload:

    def test_sorted_desc(self, client, sample_results):
        resp = client.get("/api/v1/top/upload")
        data = resp.get_json()
        speeds = [d["tx_speed_mbps"] for d in data]
        assert speeds == sorted(speeds, reverse=True)


# ===================================================================
# /api/server/<domain>/history
# ===================================================================

class TestServerHistory:

    def test_valid_domain_with_history(self, client, paths):
        data = {
            "server1.example.com": {
                "latency_ms": 25,
                "ip": "1.2.3.4",
                "country": "US",
                "history": [
                    {"event": "success", "timestamp": "2026-03-20T10:00:00"},
                    {"event": "success", "timestamp": "2026-03-21T10:00:00"},
                ]
            }
        }
        with open(paths["results"], "w") as f:
            json.dump(data, f)
        resp = client.get("/api/server/server1.example.com/history")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert len(body["history"]) == 2

    def test_unknown_domain_empty(self, client, sample_results):
        resp = client.get("/api/server/no-such-server.example.com/history")
        assert resp.status_code == 200
        assert resp.get_json()["history"] == []

    def test_invalid_domain_chars(self, client):
        resp = client.get("/api/server/bad;domain/history")
        assert resp.status_code == 400

    def test_no_results_file(self, client):
        resp = client.get("/api/server/any.example.com/history")
        assert resp.status_code == 200
        assert resp.get_json()["history"] == []

    def test_domain_without_history_key(self, client, sample_results):
        resp = client.get("/api/server/server1.example.com/history")
        assert resp.status_code == 200
        assert resp.get_json()["history"] == []


# ===================================================================
# Status classification edge cases
# ===================================================================

class TestStatusClassification:
    """Test that /api/statistics/domains classifies servers correctly
    based on speedtest_timestamp, speedtest_failed_timestamp, and speed data."""

    def test_old_success_newer_failure_is_failed(self, client, paths):
        data = {
            "s1.example.com": {
                "ip": "1.1.1.1", "country": "US",
                "rx_speed_mbps": 50, "tx_speed_mbps": 10,
                "speedtest_timestamp": "2026-03-20T10:00:00",
                "speedtest_failed_timestamp": "2026-03-21T10:00:00",
                "speedtest_failed_reason": "vpn_failed"
            }
        }
        with open(paths["results"], "w") as f:
            json.dump(data, f)
        resp = client.get("/api/statistics/domains")
        body = resp.get_json()
        assert "s1.example.com" in body["failed"]
        assert "s1.example.com" not in body["untested"]

    def test_newer_success_after_old_failure_is_succeeded(self, client, paths):
        data = {
            "s1.example.com": {
                "ip": "1.1.1.1", "country": "US",
                "rx_speed_mbps": 100, "tx_speed_mbps": 20,
                "speedtest_timestamp": "2026-03-22T10:00:00",
                "speedtest_failed_timestamp": "2026-03-21T10:00:00",
            }
        }
        with open(paths["results"], "w") as f:
            json.dump(data, f)
        resp = client.get("/api/statistics/domains")
        body = resp.get_json()
        assert "s1.example.com" not in body["failed"]
        assert "s1.example.com" not in body["untested"]

    def test_no_speedtest_at_all_is_untested(self, client, paths):
        data = {
            "s1.example.com": {
                "ip": "1.1.1.1", "country": "US",
                "latency_ms": 10,
                "rx_speed_mbps": None,
                "tx_speed_mbps": None,
                "speedtest_timestamp": None,
            }
        }
        with open(paths["results"], "w") as f:
            json.dump(data, f)
        resp = client.get("/api/statistics/domains")
        body = resp.get_json()
        assert "s1.example.com" in body["untested"]

    def test_statistics_counts_match(self, client, sample_results):
        """succeeded + failed + untested should sum to total servers for each country."""
        resp_stats = client.get("/api/statistics")
        stats = resp_stats.get_json()["countries"]
        for c in stats:
            assert c["succeeded"] + c["failed"] + c["untested"] == c["servers"], \
                f"Counts don't sum for {c['country']}"
