"""Tests for geo results, map, origin, and top-servers endpoints."""
import json
from unittest.mock import patch, MagicMock
import pytest


class TestResultsGeo:
    """Test /api/results/geo endpoint."""

    def test_no_results_file(self, client, paths):
        resp = client.get('/api/results/geo')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_no_city_db(self, client, paths, sample_results):
        import os
        os.unlink(paths['city_db'])
        resp = client.get('/api/results/geo')
        assert resp.status_code == 500
        data = resp.get_json()
        assert 'error' in data

    def test_returns_geo_data(self, client, paths, sample_results):
        """Mock the GeoIP reader to return lat/lon data."""
        mock_reader = MagicMock()
        mock_city = MagicMock()
        mock_city.location.latitude = 34.05
        mock_city.location.longitude = -118.24
        mock_reader.city.return_value = mock_city
        mock_reader.close = MagicMock()

        with patch('geoip2.database.Reader', return_value=mock_reader):
            resp = client.get('/api/results/geo')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) > 0
        assert data[0]['lat'] == 34.05
        assert data[0]['lon'] == -118.24
        assert 'domain' in data[0]
        assert 'country' in data[0]

    def test_handles_geoip_exception_per_ip(self, client, paths, sample_results):
        """IPs that fail GeoIP lookup should be skipped, not cause 500."""
        mock_reader = MagicMock()
        mock_reader.city.side_effect = Exception("GeoIP lookup failed")
        mock_reader.close = MagicMock()

        with patch('geoip2.database.Reader', return_value=mock_reader):
            resp = client.get('/api/results/geo')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_skips_entries_without_ip(self, client, paths):
        data = {
            "no-ip.example.com": {
                "latency_ms": 10, "country": "US", "city": "NYC"
            }
        }
        with open(paths['results'], 'w') as f:
            json.dump(data, f)

        mock_reader = MagicMock()
        mock_reader.close = MagicMock()
        with patch('geoip2.database.Reader', return_value=mock_reader):
            resp = client.get('/api/results/geo')
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestOrigin:
    """Test /api/origin endpoint."""

    def test_auto_mode_cached(self, client, paths, sample_config):
        import web.state as state_mod
        state_mod._origin_cache['auto'] = {
            'ip': '1.2.3.4', 'lat': 47.0, 'lon': 8.0,
            'country': 'Switzerland', 'city': 'Zurich', 'source': 'auto'
        }
        resp = client.get('/api/origin')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['lat'] == 47.0
        assert data['source'] == 'auto'
        # Cleanup
        state_mod._origin_cache['auto'] = None

    def test_manual_mode(self, client, paths):
        import web.state as state_mod
        cfg = {
            'theme': {
                'map_thresholds': {
                    'origin_mode': 'manual',
                    'origin_address': {'country': 'Germany', 'city': 'Berlin', 'zipcode': '10115'}
                }
            }
        }
        import yaml
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        mock_result = {
            'ip': '', 'lat': 52.52, 'lon': 13.40,
            'country': 'Germany', 'city': 'Berlin', 'source': 'manual'
        }
        with patch.object(state_mod, '_geocode_address', return_value=mock_result):
            resp = client.get('/api/origin')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['lat'] == 52.52
        assert data['source'] == 'manual'
        # Cleanup
        state_mod._origin_cache['manual'] = None

    def test_no_cache_no_auto(self, client, paths, sample_config):
        import web.state as state_mod
        state_mod._origin_cache['auto'] = None
        resp = client.get('/api/origin')
        assert resp.status_code == 500

    def test_manual_geocode_failure_falls_back(self, client, paths):
        import web.state as state_mod
        import yaml
        cfg = {
            'theme': {
                'map_thresholds': {
                    'origin_mode': 'manual',
                    'origin_address': {'country': 'Nowhere', 'city': '', 'zipcode': ''}
                }
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        state_mod._origin_cache['auto'] = None
        with patch.object(state_mod, '_geocode_address', return_value=None):
            resp = client.get('/api/origin')
        assert resp.status_code == 500


class TestTopServers:
    """Test /api/top-servers endpoint."""

    def test_no_results(self, client, paths):
        resp = client.get('/api/top-servers')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_best_per_country(self, client, paths, sample_results):
        resp = client.get('/api/top-servers')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) > 0
        # Should be sorted by rx_speed_mbps descending
        speeds = [s['rx_speed_mbps'] for s in data]
        assert speeds == sorted(speeds, reverse=True)

    def test_n_param(self, client, paths, sample_results):
        resp = client.get('/api/top-servers?n=1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) <= 1

    def test_n_clamped(self, client, paths, sample_results):
        resp = client.get('/api/top-servers?n=999')
        assert resp.status_code == 200


class TestConfigCacheInvalidation:
    """Test that the config cache is properly invalidated on save."""

    def test_save_invalidates_cache(self, client, paths, sample_config):
        import web.state as state_mod
        # Load config to populate cache
        cfg1 = state_mod.load_config()
        assert state_mod._config_cache is not None
        # Save changes
        cfg1['schedule']['vpn_speedtest']['enabled'] = True
        state_mod.save_config(cfg1)
        # Cache should be invalidated
        assert state_mod._config_cache is None
        # Reload should see new value
        cfg2 = state_mod.load_config()
        assert cfg2['schedule']['vpn_speedtest']['enabled'] is True

    def test_cache_returns_deep_copy(self, client, paths, sample_config):
        import web.state as state_mod
        cfg1 = state_mod.load_config()
        cfg2 = state_mod.load_config()
        # Mutating cfg1 should not affect cfg2
        cfg1['schedule']['vpn_speedtest']['enabled'] = True
        assert cfg2['schedule']['vpn_speedtest']['enabled'] is False
