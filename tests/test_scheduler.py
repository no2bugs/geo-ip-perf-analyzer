"""Tests for scheduler logic: cron kwargs, apply_schedules, resolve domains."""
import json
import yaml
import pytest


class TestBuildCronKwargs:
    """Test _build_cron_kwargs() with various schedule configurations."""

    def _build(self, **overrides):
        from web.scheduler import _build_cron_kwargs
        cfg = {'time': '03:00', 'interval': 'daily'}
        cfg.update(overrides)
        return _build_cron_kwargs(cfg)

    def test_daily_defaults(self):
        kw = self._build()
        assert kw == {'hour': 3, 'minute': 0}

    def test_daily_custom_time(self):
        kw = self._build(time='14:30')
        assert kw == {'hour': 14, 'minute': 30}

    def test_weekly_monday(self):
        kw = self._build(interval='weekly', day='monday', time='02:15')
        assert kw == {'hour': 2, 'minute': 15, 'day_of_week': 'mon'}

    def test_weekly_friday(self):
        kw = self._build(interval='weekly', day='friday')
        assert kw == {'hour': 3, 'minute': 0, 'day_of_week': 'fri'}

    def test_monthly(self):
        kw = self._build(interval='monthly', dom=15, time='06:00')
        assert kw == {'hour': 6, 'minute': 0, 'day': 15}

    def test_monthly_dom_clamped_high(self):
        kw = self._build(interval='monthly', dom=31)
        assert kw['day'] == 28

    def test_monthly_dom_clamped_low(self):
        kw = self._build(interval='monthly', dom=0)
        assert kw['day'] == 1

    def test_custom_days(self):
        kw = self._build(interval='custom', days=['monday', 'wednesday', 'friday'])
        assert kw['day_of_week'] == 'mon,wed,fri'

    def test_custom_no_days_no_key(self):
        kw = self._build(interval='custom', days=[])
        assert 'day_of_week' not in kw

    def test_hour_clamped_high(self):
        kw = self._build(time='25:00')
        assert kw['hour'] == 23, "Hour should be clamped to 23"

    def test_minute_clamped_high(self):
        kw = self._build(time='03:99')
        assert kw['minute'] == 59, "Minute should be clamped to 59"

    def test_hour_clamped_negative(self):
        kw = self._build(time='-1:30')
        assert kw['hour'] == 0

    def test_time_no_minute(self):
        kw = self._build(time='5')
        assert kw == {'hour': 5, 'minute': 0}

    def test_time_with_seconds_ignored(self):
        kw = self._build(time='03:00:00')
        assert kw == {'hour': 3, 'minute': 0}


class TestApplySchedules:
    """Test that apply_schedules creates/removes scheduler jobs correctly."""

    def test_no_enabled_schedules(self, client, paths, sample_config):
        from web.scheduler import scheduler, apply_schedules
        apply_schedules()
        assert len(scheduler.get_jobs()) == 0

    def test_enable_vpn_speedtest(self, client, paths):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'interval': 'daily', 'time': '03:00'},
                'latency_scan': {'enabled': False},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False},
                'servers_update': {'enabled': False},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import scheduler, apply_schedules
        apply_schedules()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert 'vpn_speedtest' in job_ids

    def test_enable_latency_scan(self, client, paths):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': False},
                'latency_scan': {'enabled': True, 'interval': 'weekly', 'day': 'tuesday', 'time': '02:00'},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False},
                'servers_update': {'enabled': False},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import scheduler, apply_schedules
        apply_schedules()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert 'latency_scan' in job_ids

    def test_enable_all_schedules(self, client, paths):
        import web.state as state_mod
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'interval': 'daily', 'time': '01:00'},
                'latency_scan': {'enabled': True, 'interval': 'daily', 'time': '02:00'},
                'geolite_update': {'enabled': True, 'interval': 'weekly', 'day': 'sunday', 'time': '03:00'},
                'ovpn_update': {'enabled': True, 'interval': 'weekly', 'day': 'sunday', 'time': '04:00', 'download_url': 'https://example.com/ovpn.zip'},
                'servers_update': {'enabled': True, 'interval': 'weekly', 'day': 'sunday', 'time': '05:00',
                                   'commands': [{'command': 'echo test', 'label': 'test', 'enabled': True}]},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import scheduler, apply_schedules
        apply_schedules()
        assert len(scheduler.get_jobs()) == 5

    def test_disable_removes_jobs(self, client, paths):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'interval': 'daily', 'time': '03:00'},
                'latency_scan': {'enabled': False},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False},
                'servers_update': {'enabled': False},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import scheduler, apply_schedules
        import web.state as state_mod
        apply_schedules()
        assert len(scheduler.get_jobs()) == 1
        # Disable the vpn_speedtest
        cfg['schedule']['vpn_speedtest']['enabled'] = False
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        state_mod.invalidate_config_cache()
        apply_schedules()
        assert len(scheduler.get_jobs()) == 0

    def test_servers_update_needs_commands(self, client, paths):
        """servers_update should NOT create a job if no commands configured."""
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': False},
                'latency_scan': {'enabled': False},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False},
                'servers_update': {'enabled': True, 'interval': 'daily', 'time': '06:00', 'commands': []},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import scheduler, apply_schedules
        apply_schedules()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert 'servers_update' not in job_ids


class TestResolveScheduledDomains:
    """Test _resolve_scheduled_domains() filtering logic."""

    def test_no_results_file(self, client, paths):
        from web.scheduler import _resolve_scheduled_domains
        domains, results = _resolve_scheduled_domains()
        assert domains is None
        assert results is None

    def test_empty_results(self, client, paths):
        with open(paths['results'], 'w') as f:
            json.dump({}, f)
        from web.scheduler import _resolve_scheduled_domains
        domains, results = _resolve_scheduled_domains()
        assert domains is None

    def test_returns_all_domains(self, client, paths, sample_results):
        from web.scheduler import _resolve_scheduled_domains
        domains, results = _resolve_scheduled_domains()
        assert set(domains) == set(sample_results.keys())
        assert isinstance(results, dict)

    def test_country_filter(self, client, paths, sample_results):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'countries': ['Germany']},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import _resolve_scheduled_domains
        domains, results = _resolve_scheduled_domains()
        assert all(
            sample_results[d]['country'] == 'Germany' for d in domains
        )

    def test_country_filter_no_match(self, client, paths, sample_results):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'countries': ['Antarctica']},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import _resolve_scheduled_domains
        domains, _ = _resolve_scheduled_domains()
        assert domains is None


class TestScheduleNextRuns:
    """Test /api/schedule/next endpoint."""

    def test_no_jobs_empty(self, client, paths, sample_config):
        resp = client.get('/api/schedule/next')
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_with_active_job(self, client, paths):
        cfg = {
            'schedule': {
                'vpn_speedtest': {'enabled': True, 'interval': 'daily', 'time': '03:00'},
                'latency_scan': {'enabled': False},
                'geolite_update': {'enabled': False},
                'ovpn_update': {'enabled': False},
                'servers_update': {'enabled': False},
            }
        }
        with open(paths['config'], 'w') as f:
            yaml.dump(cfg, f)
        from web.scheduler import apply_schedules
        apply_schedules()
        resp = client.get('/api/schedule/next')
        data = resp.get_json()
        assert 'vpn_speedtest' in data


class TestFormatDuration:
    """Test _format_duration helper."""

    def test_seconds(self):
        from web.state import _format_duration
        assert _format_duration(45) == '45 seconds'

    def test_one_minute(self):
        from web.state import _format_duration
        assert _format_duration(60) == '1 minute'

    def test_minutes(self):
        from web.state import _format_duration
        assert _format_duration(125) == '2 minutes'

    def test_one_hour(self):
        from web.state import _format_duration
        assert _format_duration(3600) == '1 hour'

    def test_hours_and_minutes(self):
        from web.state import _format_duration
        assert _format_duration(5220) == '1 hour and 27 minutes'

    def test_zero(self):
        from web.state import _format_duration
        assert _format_duration(0) == '0 seconds'
