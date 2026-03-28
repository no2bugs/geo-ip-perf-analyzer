"""
Shared state, configuration, utilities, and background functions.

All mutable globals (scan_active, scan_progress, etc.) live here so that
both route handlers (web/app.py) and scheduled tasks (web/scheduler.py)
reference the same module-level variables.
"""

import csv
import os
import sys
import threading
import time
import json
import logging
import logging.handlers
import subprocess
import zipfile
import io
import copy
import tempfile
import re as _re
from datetime import datetime, timezone
from pathlib import Path

import requests as http_requests
import yaml
import geoip2.database

# Add parent directory to sys.path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate.scan import Scanner

# ============================================================
# Logging
# ============================================================

class LogBufferHandler(logging.Handler):
    def __init__(self, capacity=100):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
        self.lock = threading.RLock()

    def emit(self, record):
        log_entry = {
            "timestamp": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "message": self.format(record)
        }
        try:
            with self.lock:
                self.buffer.append(log_entry)
                if len(self.buffer) > self.capacity:
                    self.buffer.pop(0)
        except Exception:
            pass

    def get_logs(self):
        with self.lock:
            return list(self.buffer)

    def clear(self):
        with self.lock:
            self.buffer = []

log_buffer = LogBufferHandler(capacity=200)
log_buffer.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(log_buffer)
logging.getLogger().setLevel(logging.INFO)

# File-based logging with rotation
LOG_DIR = os.environ.get('LOG_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs'))
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

_FILE_FORMAT = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def _make_file_handler(filename, max_bytes=2*1024*1024, backup_count=3):
    h = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, filename), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    h.setFormatter(_FILE_FORMAT)
    return h

# general.log — everything INFO+
_general_handler = _make_file_handler('general.log')
_general_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_general_handler)

# error.log — ERROR+ only
_error_handler = _make_file_handler('error.log')
_error_handler.setLevel(logging.ERROR)
logging.getLogger().addHandler(_error_handler)

# scan.log — scan-specific logger
scan_logger = logging.getLogger('scan')
scan_logger.setLevel(logging.INFO)
scan_logger.addHandler(_make_file_handler('scan.log'))

# ============================================================
# Constants
# ============================================================
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
SERVERS_FILE = os.environ.get('SERVERS_FILE', 'servers.list')
GEOIP_CITY = os.environ.get('GEOIP_CITY', 'GeoLite2-City.mmdb')
GEOIP_COUNTRY = os.environ.get('GEOIP_COUNTRY', 'GeoLite2-Country.mmdb')
VPN_OVPN_DIR = os.environ.get('VPN_OVPN_DIR', 'ovpn')
VPN_USERNAME = os.environ.get('VPN_USERNAME', '')
VPN_PASSWORD = os.environ.get('VPN_PASSWORD', '')
CONFIG_FILE = os.environ.get('CONFIG_FILE', 'config.yaml')
WALLPAPER_DIR = os.environ.get('WALLPAPER_DIR', '/data/wallpapers')

# ============================================================
# Configuration
# ============================================================
DEFAULT_CONFIG = {
    'schedule': {
        'vpn_speedtest': {
            'enabled': False,
            'interval': 'daily',
            'day': 'monday',
            'days': [],
            'dom': 1,
            'time': '03:00',
            'countries': []
        },
        'latency_scan': {
            'enabled': False,
            'interval': 'daily',
            'day': 'monday',
            'days': [],
            'dom': 1,
            'time': '02:00',
            'pings': 1,
            'timeout': 1000,
            'workers': 20,
            'countries': []
        },
        'geolite_update': {
            'enabled': False,
            'interval': 'weekly',
            'day': 'sunday',
            'days': [],
            'dom': 1,
            'time': '04:00'
        },
        'ovpn_update': {
            'enabled': False,
            'interval': 'weekly',
            'day': 'sunday',
            'days': [],
            'dom': 1,
            'time': '05:00',
            'download_url': ''
        },
        'servers_update': {
            'enabled': False,
            'interval': 'weekly',
            'day': 'sunday',
            'days': [],
            'dom': 1,
            'time': '06:00',
            'commands': [],
            'prune_stale': False
        }
    },
    'notifications': {
        'ntfy': {
            'enabled': False,
            'url': '',
            'events': {
                'vpn_speedtest_complete': False,
                'vpn_speedtest_error': True,
                'latency_scan_complete': False,
                'latency_scan_error': True,
                'geolite_updated': False,
                'geolite_update_error': True,
                'ovpn_updated': False,
                'ovpn_update_error': True,
                'servers_updated': False,
                'servers_update_error': True
            }
        }
    }
}

def _deep_merge(base, override):
    """Deep-merge override into base, returning base with updates."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                if isinstance(cfg, dict):
                    # Migrate: move ovpn.download_url -> schedule.ovpn_update.download_url
                    old_url = cfg.get('ovpn', {}).get('download_url', '')
                    if old_url and not cfg.get('schedule', {}).get('ovpn_update', {}).get('download_url'):
                        cfg.setdefault('schedule', {}).setdefault('ovpn_update', {})['download_url'] = old_url
                    cfg.pop('ovpn', None)
                    # Deep-merge saved config into defaults so new keys are always present
                    merged = copy.deepcopy(DEFAULT_CONFIG)
                    _deep_merge(merged, cfg)
                    return merged
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
    return copy.deepcopy(DEFAULT_CONFIG)

def save_config(config):
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp, CONFIG_FILE)

def _format_duration(seconds):
    """Format seconds into human-readable duration like '1 hour and 27 minutes'."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours == 1:
        parts.append("1 hour")
    elif hours > 1:
        parts.append(f"{hours} hours")
    if minutes == 1:
        parts.append("1 minute")
    elif minutes > 1:
        parts.append(f"{minutes} minutes")
    if not parts:
        parts.append(f"{secs} seconds")
    return " and ".join(parts)

_config_lock = threading.Lock()

def _update_last_run(schedule_key):
    """Update last_run timestamp for a schedule."""
    with _config_lock:
        config = load_config()
        config.setdefault('schedule', {}).setdefault(schedule_key, {})['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        save_config(config)

def send_ntfy(event, title, message, priority='default'):
    config = load_config()
    ntfy = config.get('notifications', {}).get('ntfy', {})
    if not ntfy.get('enabled') or not ntfy.get('url'):
        return
    if not ntfy.get('events', {}).get(event, False):
        return
    try:
        http_requests.post(
            ntfy['url'],
            data=message.encode('utf-8'),
            headers={'Title': title, 'Priority': priority},
            timeout=10
        )
    except Exception as e:
        logging.error(f"ntfy notification failed: {e}")

# ============================================================
# Global scan state
# ============================================================
scan_lock = threading.Lock()
_scan_state_lock = threading.Lock()
scan_active = False
scan_progress = {"done": 0, "total": 0, "status": "idle", "message": ""}
stop_event = threading.Event()
last_error = None
scan_start_time = None

# Server-side speedtest queue — file is single source of truth across workers
_queue_processor_started = False
_queue_active_job = None
_queue_file_lock = threading.Lock()

# File-based state sharing for multi-worker gunicorn
SCAN_STATE_FILE = os.path.join(tempfile.gettempdir(), 'geo_ip_scan_state.json')
QUEUE_STATE_FILE = os.path.join(tempfile.gettempdir(), 'geo_ip_queue_state.json')

STALE_HEARTBEAT_SECONDS = 30

def _flush_scan_state():
    """Persist current scan state to file for cross-worker access."""
    st = {
        "active": scan_active,
        "progress": dict(scan_progress),
        "error": last_error,
        "stop_requested": stop_event.is_set(),
        "start_time": scan_start_time,
        "heartbeat": time.time()
    }
    try:
        tmp = SCAN_STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(st, f)
        os.replace(tmp, SCAN_STATE_FILE)
    except Exception:
        pass

def _read_scan_state():
    """Read scan state from shared file."""
    try:
        with open(SCAN_STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"active": False, "progress": {"done": 0, "total": 0, "status": "idle", "message": ""}, "error": None, "stop_requested": False}

def _is_scan_active():
    """Check if a scan is truly active, with heartbeat-based stale detection."""
    if scan_active:
        return True
    st = _read_scan_state()
    if not st.get('active'):
        return False
    heartbeat = st.get('heartbeat', 0)
    if time.time() - heartbeat > STALE_HEARTBEAT_SECONDS:
        logging.warning("Clearing stale scan state (no heartbeat for >%ds — likely container restart)", STALE_HEARTBEAT_SECONDS)
        _clear_stale_state()
        return False
    return True

def _clear_stale_state():
    """Reset scan state file after detecting a stale lock from a crashed process."""
    global scan_active, scan_progress, last_error, scan_start_time
    with _scan_state_lock:
        scan_active = False
        scan_progress = {"done": 0, "total": 0, "status": "idle", "message": ""}
        last_error = None
        scan_start_time = None
    _flush_scan_state()

def _state_flusher():
    """Background thread that periodically flushes state and checks for stop requests."""
    while scan_active:
        try:
            st = _read_scan_state()
            if st.get("stop_requested") and not stop_event.is_set():
                stop_event.set()
        except Exception:
            pass
        _flush_scan_state()
        time.sleep(1)
    _flush_scan_state()

# ============================================================
# File-based queue
# ============================================================

def _read_queue_file():
    """Read queue from shared file. Returns {"pending": [...], "active": ...}."""
    try:
        with open(QUEUE_STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"pending": [], "active": None}

def _write_queue_file(st):
    """Atomically write queue state to shared file."""
    try:
        tmp = QUEUE_STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(st, f)
        os.replace(tmp, QUEUE_STATE_FILE)
    except Exception:
        pass

def _queue_add_job(domains, job_type, label):
    """Append a job to the file-based queue (safe across workers)."""
    with _queue_file_lock:
        st = _read_queue_file()
        st.setdefault("pending", []).append({"domains": domains, "type": job_type, "label": label})
        _write_queue_file(st)
        return len(st["pending"])

def _queue_pop_job():
    """Pop the first pending job from the file-based queue. Returns job or None."""
    with _queue_file_lock:
        st = _read_queue_file()
        pending = st.get("pending", [])
        if not pending:
            return None
        job = pending.pop(0)
        st["pending"] = pending
        st["active"] = {"domains_count": len(job["domains"]), "type": job.get("type", ""), "label": job.get("label", "")}
        _write_queue_file(st)
        return job

def _queue_set_active(active_info):
    """Update the active job in the queue file."""
    with _queue_file_lock:
        st = _read_queue_file()
        st["active"] = active_info
        _write_queue_file(st)

def _queue_clear_all():
    """Clear all pending items from file-based queue. Returns count removed."""
    with _queue_file_lock:
        st = _read_queue_file()
        count = len(st.get("pending", []))
        st["pending"] = []
        _write_queue_file(st)
        return count

def _ensure_queue_processor():
    """Start the queue processor thread if not already running."""
    global _queue_processor_started
    if _queue_processor_started:
        return
    _queue_processor_started = True
    t = threading.Thread(target=_queue_processor_loop, daemon=True)
    t.start()

def _queue_processor_loop():
    """Background loop: wait for scan idle, then dispatch next queued job."""
    global _queue_processor_started, _queue_active_job
    while True:
        st = _read_queue_file()
        if not st.get("pending"):
            _queue_processor_started = False
            _queue_active_job = None
            _queue_set_active(None)
            return

        while _is_scan_active():
            time.sleep(5)

        job = _queue_pop_job()
        if not job:
            _queue_processor_started = False
            _queue_active_job = None
            return

        _queue_active_job = job
        logging.info("Queue: dispatching %d domains (%s)", len(job['domains']), job.get('label', ''))
        scan_logger.info('Queue dispatching %d domains (%s)', len(job['domains']), job.get('label', ''))
        try:
            _run_vpn_speedtest_sync(job['domains'])
        except Exception as e:
            logging.error("Queue job failed: %s", e)
            scan_logger.error('Queue job failed: %s', e)
        finally:
            _queue_active_job = None
            _queue_set_active(None)

def _run_vpn_speedtest_sync(domains):
    """Run VPN speedtest synchronously (blocking). Used by queue processor."""
    global scan_active, scan_progress, last_error, scan_start_time
    stop_event.clear()
    scan_active = True
    scan_start_time = time.time()
    scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running VPN speedtest (queued)..."}
    last_error = None
    _flush_scan_state()

    flusher = threading.Thread(target=_state_flusher, daemon=True)
    flusher.start()

    scan_logger.info('VPN speedtest (queued) started: %d domains', len(domains))

    try:
        if not os.path.exists(RESULTS_FILE):
            raise FileNotFoundError("Results file not found. Please run a scan first.")

        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)

        if not isinstance(results, dict):
            raise ValueError("Results file is in an invalid format.")

        valid_domains = [d for d in domains if d in results]
        if not valid_domains:
            raise ValueError("No matching domains found in results.")

        scan_progress['total'] = len(valid_domains)

        scanner = Scanner(
            targets_file=SERVERS_FILE,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )

        vpn_start_time = time.time()
        report = scanner._perform_vpn_speedtests(
            results,
            VPN_OVPN_DIR,
            VPN_USERNAME,
            VPN_PASSWORD,
            scan_progress,
            batch_size=999,
            interactive=False,
            selected_domains=valid_domains,
            stop_event=stop_event,
            results_file=RESULTS_FILE
        ) or {}

        duration = _format_duration(time.time() - vpn_start_time)
        report_msg = f"{report.get('succeeded', 0)} succeeded, {report.get('vpn_failed', 0)} VPN failed, {report.get('speedtest_failed', 0)} speedtest failed"
        if stop_event.is_set():
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'VPN speedtest interrupted — {report_msg}'
            scan_logger.info('VPN speedtest (queued) interrupted: %d/%d domains (%s) — %s', scan_progress['done'], len(valid_domains), duration, report_msg)
        else:
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'VPN speedtest completed — {report_msg}'
            scan_logger.info('VPN speedtest (queued) completed: %d domains (%s) — %s', len(valid_domains), duration, report_msg)
            send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete (Queue)',
                      f'{len(valid_domains)} servers tested ({duration})\n{report_msg}')

    except Exception as e:
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        last_error = str(e)
        logging.error("Queue VPN speedtest error: %s", e)
        scan_logger.error('VPN speedtest (queued) error: %s', e)
    finally:
        scan_active = False
        _flush_scan_state()
        _update_last_run('vpn_speedtest')

# ============================================================
# Background scan / VPN helpers
# ============================================================

def _filtered_servers_file(countries):
    """Create a temp servers file with only domains matching the given countries.
    Returns (path, is_temp). Caller must delete temp file after use."""
    if not countries:
        return SERVERS_FILE, False
    country_set = {c.casefold() for c in countries}
    if not os.path.exists(RESULTS_FILE):
        return SERVERS_FILE, False
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception:
        return SERVERS_FILE, False
    if not os.path.exists(SERVERS_FILE):
        return SERVERS_FILE, False
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        all_domains = [line.strip() for line in f if line.strip()]
    filtered = []
    for d in all_domains:
        entry = results.get(d)
        if isinstance(entry, dict) and entry.get('country', '').casefold() in country_set:
            filtered.append(d)
    if not filtered:
        return SERVERS_FILE, False
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.list', delete=False, dir='/tmp')
    tmp.write('\n'.join(filtered) + '\n')
    tmp.close()
    return tmp.name, True

def run_scan_in_background(pings, timeout, workers, vpn_speedtest=False, countries=None):
    global scan_active, scan_progress, last_error, scan_start_time

    stop_event.clear()
    scan_active = True
    scan_start_time = time.time()
    scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Initializing..."}
    last_error = None
    _flush_scan_state()

    flusher = threading.Thread(target=_state_flusher, daemon=True)
    flusher.start()

    servers_file, is_temp = _filtered_servers_file(countries)
    try:
        if not (os.path.exists(GEOIP_CITY) and os.path.exists(GEOIP_COUNTRY)):
            raise FileNotFoundError(f"GeoIP databases not found at {GEOIP_CITY} or {GEOIP_COUNTRY}")

        scanner = Scanner(
            targets_file=servers_file,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )

        scan_logger.info(f'Scan started: pings={pings}, timeout={timeout}, workers={workers}, vpn={vpn_speedtest}')
        _results, failed_domains = scanner.scan(
            pings_num=pings,
            timeout_ms=timeout,
            workers=workers,
            progress_container=scan_progress,
            vpn_speedtest=vpn_speedtest,
            vpn_ovpn_dir=VPN_OVPN_DIR,
            vpn_username=VPN_USERNAME,
            vpn_password=VPN_PASSWORD,
            stop_event=stop_event
        )
        # Remove failed domains from servers.list (full scans only)
        if failed_domains and not is_temp:
            try:
                with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
                cleaned = [d for d in lines if d not in failed_domains]
                if cleaned:
                    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(cleaned) + '\n')
                    scan_logger.info(f'Removed {len(failed_domains)} failed servers from servers.list')
            except Exception as e:
                logging.error(f"Failed to clean servers.list: {e}")
        if stop_event.is_set():
            scan_progress['status'] = 'completed'
            scan_progress['message'] = 'Scan interrupted by stop request'
            scan_logger.info(f'Scan interrupted by stop request: {scan_progress["done"]}/{scan_progress["total"]} servers')
        else:
            scan_progress['status'] = 'completed'
            scan_progress['message'] = 'Scan completed successfully'
            scan_logger.info(f'Scan completed: {scan_progress["total"]} servers')
            send_ntfy('latency_scan_complete', 'Latency Scan Complete',
                      f'Scanned {scan_progress["total"]} servers successfully')

    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scan failed: {e}")
        scan_logger.error(f'Scan failed: {e}')
        send_ntfy('latency_scan_error', 'Scan Failed', str(e), priority='high')
    finally:
        scan_active = False
        _flush_scan_state()
        _update_last_run('latency_scan')
        if is_temp:
            try:
                os.unlink(servers_file)
            except OSError:
                pass

# ============================================================
# GeoLite update
# ============================================================
GEOLITE_RELEASE_URL = 'https://api.github.com/repos/P3TERX/GeoLite.mmdb/releases/latest'
GEOLITE_CITY_FILENAME = 'GeoLite2-City.mmdb'
GEOLITE_COUNTRY_FILENAME = 'GeoLite2-Country.mmdb'

def _do_geolite_update():
    """Download latest GeoLite2 databases. Returns list of updated filenames."""
    logging.info('Fetching latest GeoLite2 release info...')
    resp = http_requests.get(GEOLITE_RELEASE_URL, timeout=10)
    resp.raise_for_status()
    release = resp.json()
    assets = release.get('assets', [])

    downloaded = []
    for asset in assets:
        name = asset.get('name', '')
        if name in (GEOLITE_CITY_FILENAME, GEOLITE_COUNTRY_FILENAME):
            download_url = asset.get('browser_download_url')
            if not download_url:
                continue
            target = GEOIP_CITY if name == GEOLITE_CITY_FILENAME else GEOIP_COUNTRY
            logging.info(f'Downloading {name}...')
            dl = http_requests.get(download_url, timeout=120, stream=True)
            dl.raise_for_status()
            tmp_path = target + '.tmp'
            with open(tmp_path, 'wb') as f:
                for chunk in dl.iter_content(chunk_size=8192):
                    f.write(chunk)
            os.replace(tmp_path, target)
            downloaded.append(name)
            logging.info(f'{name} updated successfully')
    return downloaded

# ============================================================
# OVPN download
# ============================================================

def _download_ovpn_from_url(url):
    """Download and extract OVPN configs from a URL. Returns count of extracted files."""
    logging.info(f'Downloading OVPN configs from URL...')
    resp = http_requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()

    zip_bytes = resp.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if os.path.isabs(name) or '..' in name:
                raise ValueError(f'Invalid path in zip: {name}')

        ovpn_path = Path(VPN_OVPN_DIR)
        ovpn_path.mkdir(parents=True, exist_ok=True)

        for old in ovpn_path.glob('*.ovpn'):
            old.unlink(missing_ok=True)

        extracted = 0
        for name in zf.namelist():
            basename = os.path.basename(name)
            if basename.lower().endswith('.ovpn') and 'udp' in basename.lower():
                target = ovpn_path / basename
                target.write_bytes(zf.read(name))
                extracted += 1

    logging.info(f'OVPN configs updated: {extracted} UDP files extracted')
    return extracted

# ============================================================
# Prune stale results
# ============================================================

def _prune_stale_results():
    """Remove results entries whose domain is not in servers.list."""
    if not os.path.exists(SERVERS_FILE):
        raise RuntimeError("servers.list not found")
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        current_servers = {line.strip() for line in f if line.strip()}
    if not current_servers:
        raise RuntimeError("servers.list is empty — refusing to prune (would delete all data)")
    if not os.path.exists(RESULTS_FILE):
        return 0, 0
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        results = json.load(f)
    if not isinstance(results, dict):
        return 0, 0
    stale_keys = [d for d in results if d not in current_servers]
    if not stale_keys:
        return 0, len(results)
    for key in stale_keys:
        del results[key]
    tmp = RESULTS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    os.replace(tmp, RESULTS_FILE)
    logging.info(f"Pruned {len(stale_keys)} stale servers from results ({len(results)} remaining)")
    return len(stale_keys), len(results)

# ============================================================
# Origin detection
# ============================================================
_origin_cache = {'auto': None, 'manual': None}

def _detect_origin_from_geoip():
    """Detect origin using public IP resolved through local GeoIP DB."""
    if not os.path.exists(GEOIP_CITY):
        return None
    try:
        ip_resp = http_requests.get('https://api.ipify.org', timeout=10)
        public_ip = ip_resp.text.strip()
        reader = geoip2.database.Reader(GEOIP_CITY)
        try:
            geo = reader.city(public_ip)
            return {
                'ip': public_ip,
                'lat': geo.location.latitude,
                'lon': geo.location.longitude,
                'country': geo.country.name or 'Unknown',
                'city': geo.city.name or 'Unknown',
                'source': 'auto'
            }
        finally:
            reader.close()
    except Exception:
        return None

def _geocode_address(country, city, zipcode):
    """Geocode a manual address via Nominatim (OpenStreetMap)."""
    parts = [p for p in [zipcode, city, country] if p]
    if not parts:
        return None
    query = ', '.join(parts)
    try:
        resp = http_requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'GeoIP-Performance-Analyzer/1.0'},
            timeout=10
        )
        results = resp.json()
        if results:
            return {
                'ip': '',
                'lat': float(results[0]['lat']),
                'lon': float(results[0]['lon']),
                'country': country or 'Unknown',
                'city': city or 'Unknown',
                'source': 'manual'
            }
    except Exception:
        pass
    return None

def _init_origin():
    """Detect auto origin once at startup (before any VPN tunnels are up)."""
    result = _detect_origin_from_geoip()
    if result:
        _origin_cache['auto'] = result
        logging.info('Vantage point detected at startup: %s, %s (%s)',
                     result.get('city'), result.get('country'), result.get('ip'))
    else:
        logging.warning('Could not auto-detect vantage point at startup (GeoIP DB may be missing)')

# ============================================================
# .env credentials helpers
# ============================================================
ENV_FILE = os.path.join(os.path.dirname(CONFIG_FILE) if os.path.dirname(CONFIG_FILE) else '.', '.env')

def _read_env_file():
    """Read key=value pairs from .env file."""
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    env[key.strip()] = val.strip()
    return env

def _write_env_file(env):
    """Write key=value pairs to .env file atomically, preserving unknown keys."""
    tmp = ENV_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for key, val in env.items():
            f.write(f"{key}={val}\n")
    os.replace(tmp, ENV_FILE)

# ============================================================
# Servers update commands
# ============================================================

def _get_servers_commands(config):
    """Get list of enabled commands from config, with backward compat for single 'command' field."""
    srv = config.get('schedule', {}).get('servers_update', {})
    commands = srv.get('commands', [])
    if commands:
        return [c for c in commands if c.get('enabled', True) and c.get('command', '').strip()]
    cmd = srv.get('command', '').strip()
    if cmd:
        return [{'command': cmd, 'label': '', 'enabled': True}]
    return []

def _run_servers_update_commands(commands):
    """Run multiple shell commands and merge their output into servers.list."""
    import shlex
    BLOCKED_PATTERNS = ['rm ', 'rm\t', 'mkfs', 'dd ', ':(){', 'fork', '> /dev/', 'shutdown', 'reboot',
                        'passwd', 'chmod 777', 'curl|', 'wget|', '| bash', '| sh',
                        'bash -c', 'sh -c', 'python -c', 'perl -e', 'ruby -e',
                        '$(', '`']
    all_hosts = []
    for entry in commands:
        cmd = entry['command']
        label = entry.get('label', '') or 'unnamed'
        cmd_lower = cmd.lower().strip()
        for pattern in BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                raise RuntimeError(f"Command '{label}' contains blocked pattern '{pattern}'")
        logging.info(f"Running servers update command: {label}")
        result = subprocess.run(
            ['bash', '-c', cmd], capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"Command '{label}' exited with code {result.returncode}: {result.stderr.strip()}")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        logging.info(f"  {label}: {len(lines)} hosts")
        all_hosts.extend(lines)
    all_hosts = list(dict.fromkeys(all_hosts))
    if not all_hosts:
        raise RuntimeError("All commands produced no output")
    tmp = SERVERS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_hosts) + '\n')
    os.replace(tmp, SERVERS_FILE)
    logging.info(f"servers.list updated: {len(all_hosts)} unique entries")
    return len(all_hosts)

# ============================================================
# Misc route helpers
# ============================================================

VALID_PALETTES = {'default', 'midnight', 'emerald', 'sunset', 'arctic', 'rose', 'sandstorm', 'carbon', 'pihole', 'backstage', 'dracula', 'nord'}
VALID_WALLPAPERS = {'none', 'grid', 'dots', 'hexagons', 'circuit_board', 'network', 'globe', 'radar', 'city_lights', 'data_flow', 'topology', 'server_rack', 'signal_waves', 'matrix', 'constellation', 'diamonds', 'crosses', 'waves', 'triangles', 'custom', 'video_matrix', 'video_starfield', 'video_particles', 'video_aurora', 'video_fireflies', 'video_blue_polygon', 'video_black_hole', 'video_digital_globe', 'video_blue_code', 'video_white_lines', 'video_custom'}
VALID_WALLPAPER_MODES = {'tile', 'cover', 'contain'}
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.svg'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm'}
MAX_WALLPAPER_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_VIDEO_WALLPAPER_SIZE = 50 * 1024 * 1024  # 50 MB

LOG_FILE_MAP = {'general': 'general.log', 'error': 'error.log', 'scan': 'scan.log'}

_LOG_LINE_RE = _re.compile(r'^(\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2}))\s+\[(\w+)]\s+(.*)')

def _parse_countries(args):
    """Parse country filter from query args. Supports comma-separated and repeated params."""
    raw = args.getlist('country')
    countries = set()
    for val in raw:
        for part in val.split(','):
            part = part.strip()
            if part:
                countries.add(part.lower())
    return countries
