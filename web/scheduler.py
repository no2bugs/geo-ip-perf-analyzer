"""
APScheduler setup and all scheduled task functions.

Imports mutable state from web.state so scheduler and routes share
the same globals.
"""

import os
import json
import time
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import web.state as state
from web.state import Scanner

# ============================================================
# Scheduler instance
# ============================================================
scheduler = BackgroundScheduler(daemon=True)

DAY_MAP = {
    'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
    'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
}


def _resolve_scheduled_domains():
    """Resolve the domain list for the scheduled VPN speedtest. Returns (domains, results_dict) or (None, None) on error."""
    if not os.path.exists(state.RESULTS_FILE):
        logging.error("Scheduled VPN speedtest skipped: no results.json (run a scan first)")
        state.send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed',
                        'No results.json found. Run a scan first.', priority='high')
        return None, None
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
        all_domains = list(results.keys()) if isinstance(results, dict) else []
        if not all_domains:
            logging.error("Scheduled VPN speedtest skipped: no domains in results")
            return None, None
        config = state.load_config()
        vpn_countries = config.get('schedule', {}).get('vpn_speedtest', {}).get('countries', [])
        if vpn_countries:
            country_set = {c.casefold() for c in vpn_countries}
            all_domains = [d for d in all_domains if isinstance(results.get(d), dict) and results[d].get('country', '').casefold() in country_set]
            if not all_domains:
                logging.error("Scheduled VPN speedtest skipped: no servers match selected countries")
                return None, None
        return all_domains, results
    except Exception as e:
        logging.error(f"Scheduled VPN speedtest failed to resolve domains: {e}")
        return None, None


def scheduled_vpn_speedtest():
    all_domains, results = _resolve_scheduled_domains()
    if not all_domains:
        return

    if state._is_scan_active():
        logging.info("Scheduled VPN speedtest queued: operation already in progress (%d domains)", len(all_domains))
        state.scan_logger.info('Scheduled VPN speedtest queued (scan in progress): %d domains', len(all_domains))
        state._queue_add_job(all_domains, 'scheduled', f'Scheduled ({len(all_domains)} servers)')
        state._ensure_queue_processor()
        return

    try:
        logging.info(f"Starting scheduled VPN speedtest on {len(all_domains)} servers...")
        state.scan_logger.info(f'Scheduled VPN speedtest started: {len(all_domains)} servers')
        vpn_start_time = time.time()
        state.stop_event.clear()
        state.scan_active = True
        state.scan_start_time = vpn_start_time
        state.scan_progress = {"done": 0, "total": len(all_domains), "status": "running", "message": "Running scheduled VPN speedtest..."}
        state.last_error = None
        state._flush_scan_state()
        flusher = threading.Thread(target=state._state_flusher, daemon=True)
        flusher.start()
        scanner = Scanner(
            targets_file=state.SERVERS_FILE,
            city_db=state.GEOIP_CITY,
            country_db=state.GEOIP_COUNTRY,
            results_json=state.RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )
        report = scanner._perform_vpn_speedtests(
            results, state.VPN_OVPN_DIR, state.VPN_USERNAME, state.VPN_PASSWORD,
            state.scan_progress, batch_size=999, interactive=False,
            selected_domains=all_domains, stop_event=state.stop_event,
            results_file=state.RESULTS_FILE, source='scheduled'
        ) or {}
        duration = state._format_duration(time.time() - vpn_start_time)
        report_msg = f"{report.get('succeeded', 0)} succeeded, {report.get('vpn_failed', 0)} VPN failed, {report.get('speedtest_failed', 0)} speedtest failed"
        if state.stop_event.is_set():
            state.scan_progress['status'] = 'completed'
            state.scan_progress['message'] = f'Scheduled VPN speedtest interrupted — {report_msg}'
            state.scan_logger.info(f'Scheduled VPN speedtest interrupted: {state.scan_progress["done"]}/{len(all_domains)} servers ({duration}) — {report_msg}')
        else:
            state.scan_progress['status'] = 'completed'
            state.scan_progress['message'] = f'Scheduled VPN speedtest completed — {report_msg}'
            state.scan_logger.info(f'Scheduled VPN speedtest completed: {len(all_domains)} servers ({duration}) — {report_msg}')
            state.send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete',
                            f'{len(all_domains)} servers tested ({duration})\n{report_msg}')
    except Exception as e:
        state.last_error = str(e)
        state.scan_progress['status'] = 'error'
        state.scan_progress['message'] = str(e)
        logging.error(f"Scheduled VPN speedtest failed: {e}")
        state.send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed', str(e), priority='high')
    finally:
        state.scan_active = False
        state._flush_scan_state()
        state._update_last_run('vpn_speedtest')


def scheduled_latency_scan():
    if state._is_scan_active():
        logging.info("Scheduled latency scan skipped: operation already in progress")
        return

    is_temp = False
    try:
        if not (os.path.exists(state.GEOIP_CITY) and os.path.exists(state.GEOIP_COUNTRY)):
            raise FileNotFoundError(f"GeoIP databases not found at {state.GEOIP_CITY} or {state.GEOIP_COUNTRY}")

        config = state.load_config()
        lat_cfg = config.get('schedule', {}).get('latency_scan', {})
        lat_countries = lat_cfg.get('countries', [])
        pings_num = max(1, min(10, int(lat_cfg.get('pings', 1))))
        timeout_ms = max(100, min(10000, int(lat_cfg.get('timeout', 1000))))
        workers = max(1, min(100, int(lat_cfg.get('workers', 20))))

        servers_file, is_temp = state._filtered_servers_file(lat_countries)
        scanner = Scanner(
            targets_file=servers_file,
            city_db=state.GEOIP_CITY,
            country_db=state.GEOIP_COUNTRY,
            results_json=state.RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )

        state.stop_event.clear()
        state.scan_active = True
        state.scan_start_time = time.time()
        state.scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running scheduled latency scan..."}
        state.last_error = None
        state._flush_scan_state()
        flusher = threading.Thread(target=state._state_flusher, daemon=True)
        flusher.start()

        logging.info("Starting scheduled latency scan...")
        state.scan_logger.info('Scheduled latency scan started')
        _results, failed_domains = scanner.scan(
            pings_num=pings_num,
            timeout_ms=timeout_ms,
            workers=workers,
            progress_container=state.scan_progress,
            vpn_speedtest=False,
            stop_event=state.stop_event
        )
        if failed_domains and not is_temp:
            try:
                with open(state.SERVERS_FILE, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
                cleaned = [d for d in lines if d not in failed_domains]
                if cleaned:
                    with open(state.SERVERS_FILE, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(cleaned) + '\n')
                    state.scan_logger.info(f'Removed {len(failed_domains)} failed servers from servers.list')
            except Exception as e:
                logging.error(f"Failed to clean servers.list: {e}")
        duration = state._format_duration(time.time() - state.scan_start_time)
        total = state.scan_progress.get('total', 0)
        if state.stop_event.is_set():
            state.scan_progress['status'] = 'completed'
            state.scan_progress['message'] = f'Scheduled latency scan interrupted — {state.scan_progress["done"]}/{total} servers'
            state.scan_logger.info(f'Scheduled latency scan interrupted: {state.scan_progress["done"]}/{total} servers ({duration})')
        else:
            state.scan_progress['status'] = 'completed'
            state.scan_progress['message'] = f'Scheduled latency scan completed — {total} servers'
            state.scan_logger.info(f'Scheduled latency scan completed: {total} servers ({duration})')
            state.send_ntfy('latency_scan_complete', 'Latency Scan Complete',
                            f'{total} servers scanned ({duration})')
    except Exception as e:
        state.last_error = str(e)
        state.scan_progress['status'] = 'error'
        state.scan_progress['message'] = str(e)
        logging.error(f"Scheduled latency scan failed: {e}")
        state.send_ntfy('latency_scan_error', 'Latency Scan Failed', str(e), priority='high')
    finally:
        state.scan_active = False
        state._flush_scan_state()
        state._update_last_run('latency_scan')
        if is_temp:
            try:
                os.unlink(servers_file)
            except OSError:
                pass


def scheduled_geolite_update():
    try:
        downloaded = state._do_geolite_update()
        if downloaded:
            state.send_ntfy('geolite_updated', 'GeoLite2 Updated', f'Updated: {", ".join(downloaded)}')
    except Exception as e:
        logging.error(f'Scheduled GeoLite2 update failed: {e}')
        state.send_ntfy('geolite_update_error', 'GeoLite2 Update Failed', str(e), priority='high')
    finally:
        state._update_last_run('geolite_update')


def scheduled_ovpn_update():
    config = state.load_config()
    url = config.get('schedule', {}).get('ovpn_update', {}).get('download_url', '')
    if not url:
        logging.info("Scheduled OVPN update skipped: no download URL configured")
        return
    try:
        count = state._download_ovpn_from_url(url)
        state.send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{count} UDP configs extracted')
    except Exception as e:
        logging.error(f'Scheduled OVPN update failed: {e}')
        state.send_ntfy('ovpn_update_error', 'OVPN Update Failed', str(e), priority='high')
    finally:
        state._update_last_run('ovpn_update')


def scheduled_servers_update():
    config = state.load_config()
    commands = state._get_servers_commands(config)
    if not commands:
        logging.info("Scheduled servers update skipped: no commands configured")
        return
    try:
        count = state._run_servers_update_commands(commands)
        state.send_ntfy('servers_updated', 'Servers List Updated', f'{count} servers loaded')
        if config.get('schedule', {}).get('servers_update', {}).get('prune_stale'):
            try:
                pruned, remaining = state._prune_stale_results()
                if pruned:
                    logging.info(f"Auto-pruned {pruned} stale servers from results ({remaining} remaining)")
            except Exception as pe:
                logging.error(f"Auto-prune failed: {pe}")
    except Exception as e:
        logging.error(f'Scheduled servers update failed: {e}')
        state.send_ntfy('servers_update_error', 'Servers List Update Failed', str(e), priority='high')
    finally:
        state._update_last_run('servers_update')


def _build_cron_kwargs(cfg):
    """Build CronTrigger kwargs from a schedule config block."""
    parts = str(cfg.get('time', '03:00')).split(':')
    hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    kw = {'hour': hour, 'minute': minute}
    interval = cfg.get('interval', 'daily')
    if interval == 'weekly':
        kw['day_of_week'] = DAY_MAP.get(cfg.get('day', 'monday'), 'mon')
    elif interval == 'monthly':
        kw['day'] = max(1, min(28, int(cfg.get('dom', 1))))
    elif interval == 'custom':
        days = cfg.get('days', [])
        if days:
            kw['day_of_week'] = ','.join(DAY_MAP.get(d, d) for d in days)
    return kw


def apply_schedules():
    config = state.load_config()
    scheduler.remove_all_jobs()

    vpn_cfg = config.get('schedule', {}).get('vpn_speedtest', {})
    if vpn_cfg.get('enabled'):
        kw = _build_cron_kwargs(vpn_cfg)
        scheduler.add_job(scheduled_vpn_speedtest, CronTrigger(**kw), id='vpn_speedtest', replace_existing=True)

    lat_cfg = config.get('schedule', {}).get('latency_scan', {})
    if lat_cfg.get('enabled'):
        kw = _build_cron_kwargs(lat_cfg)
        scheduler.add_job(scheduled_latency_scan, CronTrigger(**kw), id='latency_scan', replace_existing=True)

    geo_cfg = config.get('schedule', {}).get('geolite_update', {})
    if geo_cfg.get('enabled'):
        kw = _build_cron_kwargs(geo_cfg)
        scheduler.add_job(scheduled_geolite_update, CronTrigger(**kw), id='geolite', replace_existing=True)

    ovpn_cfg = config.get('schedule', {}).get('ovpn_update', {})
    if ovpn_cfg.get('enabled'):
        kw = _build_cron_kwargs(ovpn_cfg)
        scheduler.add_job(scheduled_ovpn_update, CronTrigger(**kw), id='ovpn', replace_existing=True)

    srv_cfg = config.get('schedule', {}).get('servers_update', {})
    if srv_cfg.get('enabled') and state._get_servers_commands(config):
        kw = _build_cron_kwargs(srv_cfg)
        scheduler.add_job(scheduled_servers_update, CronTrigger(**kw), id='servers_update', replace_existing=True)

    jobs = scheduler.get_jobs()
    logging.info(f"Scheduler updated: {len(jobs)} job(s) active")
