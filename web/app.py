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
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
import requests as http_requests
import yaml
import geoip2.database
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Add parent directory to sys.path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate.scan import Scanner

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Log buffer for Web UI
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

# Configuration
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
SERVERS_FILE = os.environ.get('SERVERS_FILE', 'servers.list')
GEOIP_CITY = os.environ.get('GEOIP_CITY', 'GeoLite2-City.mmdb')
GEOIP_COUNTRY = os.environ.get('GEOIP_COUNTRY', 'GeoLite2-Country.mmdb')
VPN_OVPN_DIR = os.environ.get('VPN_OVPN_DIR', 'ovpn')
VPN_USERNAME = os.environ.get('VPN_USERNAME', '')
VPN_PASSWORD = os.environ.get('VPN_PASSWORD', '')
CONFIG_FILE = os.environ.get('CONFIG_FILE', 'config.yaml')
WALLPAPER_DIR = os.environ.get('WALLPAPER_DIR', '/data/wallpapers')

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
                    return cfg
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
    from datetime import datetime
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

# Global state
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
_queue_file_lock = threading.Lock()  # Thread-level lock for file operations

# File-based state sharing for multi-worker gunicorn
SCAN_STATE_FILE = os.path.join(tempfile.gettempdir(), 'geo_ip_scan_state.json')
QUEUE_STATE_FILE = os.path.join(tempfile.gettempdir(), 'geo_ip_queue_state.json')

STALE_HEARTBEAT_SECONDS = 30  # no heartbeat for 30s = stale (crashed process)

def _flush_scan_state():
    """Persist current scan state to file for cross-worker access."""
    state = {
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
            json.dump(state, f)
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
    state = _read_scan_state()
    if not state.get('active'):
        return False
    # State file says active — verify heartbeat is fresh
    heartbeat = state.get('heartbeat', 0)
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
        # Check for stop requests from other workers BEFORE flushing
        try:
            state = _read_scan_state()
            if state.get("stop_requested") and not stop_event.is_set():
                stop_event.set()
        except Exception:
            pass
        _flush_scan_state()
        time.sleep(1)
    _flush_scan_state()


# ---- File-based queue (single source of truth across gunicorn workers) ----

def _read_queue_file():
    """Read queue from shared file. Returns {"pending": [...], "active": ...}."""
    try:
        with open(QUEUE_STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"pending": [], "active": None}


def _write_queue_file(state):
    """Atomically write queue state to shared file."""
    try:
        tmp = QUEUE_STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(state, f)
        os.replace(tmp, QUEUE_STATE_FILE)
    except Exception:
        pass


def _queue_add_job(domains, job_type, label):
    """Append a job to the file-based queue (safe across workers)."""
    with _queue_file_lock:
        state = _read_queue_file()
        state.setdefault("pending", []).append({"domains": domains, "type": job_type, "label": label})
        _write_queue_file(state)
        return len(state["pending"])


def _queue_pop_job():
    """Pop the first pending job from the file-based queue. Returns job or None."""
    with _queue_file_lock:
        state = _read_queue_file()
        pending = state.get("pending", [])
        if not pending:
            return None
        job = pending.pop(0)
        state["pending"] = pending
        state["active"] = {"domains_count": len(job["domains"]), "type": job.get("type", ""), "label": job.get("label", "")}
        _write_queue_file(state)
        return job


def _queue_set_active(active_info):
    """Update the active job in the queue file."""
    with _queue_file_lock:
        state = _read_queue_file()
        state["active"] = active_info
        _write_queue_file(state)


def _queue_clear_all():
    """Clear all pending items from file-based queue. Returns count removed."""
    with _queue_file_lock:
        state = _read_queue_file()
        count = len(state.get("pending", []))
        state["pending"] = []
        _write_queue_file(state)
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
        # Check if there are pending jobs in the file
        state = _read_queue_file()
        if not state.get("pending"):
            _queue_processor_started = False
            _queue_active_job = None
            _queue_set_active(None)
            return

        # Wait until no scan is active
        while _is_scan_active():
            time.sleep(5)

        # Pop the next job from the file
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
    global scan_active, scan_progress, last_error, stop_event, scan_start_time
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

def _filtered_servers_file(countries):
    """Create a temp servers file with only domains matching the given countries (using results.json).
    Returns the temp file path, or SERVERS_FILE if no filtering needed.
    Caller must delete the temp file after use."""
    if not countries:
        return SERVERS_FILE, False
    country_set = {c.casefold() for c in countries}
    # Load results.json for country lookup
    if not os.path.exists(RESULTS_FILE):
        return SERVERS_FILE, False
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception:
        return SERVERS_FILE, False
    # Read all servers
    if not os.path.exists(SERVERS_FILE):
        return SERVERS_FILE, False
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        all_domains = [line.strip() for line in f if line.strip()]
    # Filter: include domain only if its country matches
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
    global scan_active, scan_progress, last_error, stop_event, scan_start_time
    
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
        # Check if DBs exist
        if not (os.path.exists(GEOIP_CITY) and os.path.exists(GEOIP_COUNTRY)):
            raise FileNotFoundError(f"GeoIP databases not found at {GEOIP_CITY} or {GEOIP_COUNTRY}")
        
        scanner = Scanner(
            targets_file=servers_file,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )
        
        # Override exclude/include if needed or just use defaults
        
        scan_logger.info(f'Scan started: pings={pings}, timeout={timeout}, workers={workers}, vpn={vpn_speedtest}')
        scanner.scan(
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
        if stop_event.is_set():
            scan_progress['status'] = 'completed'
            scan_progress['message'] = 'Scan interrupted by stop request'
            scan_logger.info(f'Scan interrupted by stop request: {scan_progress["done"]}/{scan_progress["total"]} servers')
        else:
            scan_progress['status'] = 'completed'
            scan_progress['message'] = 'Scan completed successfully'
            scan_logger.info(f'Scan completed: {scan_progress["total"]} servers')
            send_ntfy('vpn_speedtest_complete', 'Scan Complete',
                      f'Scanned {scan_progress["total"]} servers successfully')
        
    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scan failed: {e}")
        scan_logger.error(f'Scan failed: {e}')
        send_ntfy('vpn_speedtest_error', 'Scan Failed', str(e), priority='high')
    finally:
        scan_active = False
        _flush_scan_state()
        if is_temp:
            try:
                os.unlink(servers_file)
            except OSError:
                pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def config_page():
    return render_template('config.html')

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/logs')
def logs_page():
    return render_template('logs.html')

@app.route('/map')
def map_page():
    return render_template('map.html')

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    global scan_active
    
    if _is_scan_active():
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
        
    data = request.json or {}
    
    # Check if servers.list exists and is not empty
    if not os.path.exists(SERVERS_FILE):
        return jsonify({
            "status": "error", 
            "message": "Servers list file is missing. Please create 'servers.list' in the project root directory on your HOST machine."
        }), 400
        
    if os.path.getsize(SERVERS_FILE) == 0:
        return jsonify({
            "status": "error", 
            "message": "Servers list file is empty. Please add domains to 'servers.list' on your HOST machine (one domain per line)."
        }), 400

    pings = max(1, min(20, int(data.get('pings', 1))))
    timeout = max(100, min(30000, int(data.get('timeout', 1000))))
    workers = max(1, min(100, int(data.get('workers', 10))))
    vpn_speedtest = bool(data.get('vpn_speedtest', False))
    countries = data.get('countries', [])
    if not isinstance(countries, list):
        countries = []
    
    thread = threading.Thread(target=run_scan_in_background, args=(pings, timeout, workers, vpn_speedtest, countries))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scan/status')
def get_status():
    # Use heartbeat-aware check so stale state from crashes is auto-cleared
    active = _is_scan_active()
    state = _read_scan_state()
    return jsonify({
        "active": active,
        "progress": state.get("progress", scan_progress),
        "error": state.get("error", last_error),
        "stopping": state.get("stop_requested", stop_event.is_set()),
        "start_time": state.get("start_time")
    })

@app.route('/api/results')
def get_results():
    if not os.path.exists(RESULTS_FILE):
        return jsonify({})
    
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/results/export/<fmt>')
def export_results(fmt):
    """Export all results as CSV or JSON file download."""
    if fmt not in ('csv', 'json'):
        return jsonify({'status': 'error', 'message': 'Format must be csv or json'}), 400
    if not os.path.exists(RESULTS_FILE):
        return jsonify({'status': 'error', 'message': 'No results available'}), 404
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    if fmt == 'json':
        resp = app.response_class(
            json.dumps(data, indent=2, ensure_ascii=False),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=results.json'}
        )
        return resp

    # CSV export
    import csv as csv_mod
    import io as io_mod
    buf = io_mod.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(['Domain', 'IP', 'Latency (ms)', 'Country', 'City',
                     'Download (Mbps)', 'Upload (Mbps)'])
    for domain, entry in sorted(data.items()):
        if not isinstance(entry, dict):
            continue
        writer.writerow([
            domain,
            entry.get('ip', ''),
            entry.get('latency_ms', ''),
            entry.get('country', ''),
            entry.get('city', ''),
            entry.get('rx_speed_mbps', ''),
            entry.get('tx_speed_mbps', ''),
        ])
    resp = app.response_class(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=results.csv'}
    )
    return resp


@app.route('/api/countries')
def get_countries():
    """Return list of countries with server counts from results.json."""
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        counts = {}
        for domain, entry in data.items():
            if isinstance(entry, dict):
                country = entry.get('country', 'Unknown')
            elif isinstance(entry, list) and len(entry) > 2:
                country = entry[2] or 'Unknown'
            else:
                country = 'Unknown'
            counts[country] = counts.get(country, 0) + 1
        result = [{'country': c, 'count': n} for c, n in sorted(counts.items())]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/vpn-speedtest', methods=['POST'])
def vpn_speedtest():
    global scan_active
    
    if _is_scan_active():
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
    
    data = request.json or {}
    selected_domains = data.get('domains', [])
    
    # Run VPN speedtest on selected (or all) domains
    def run_vpn_speedtest_background():
        global scan_active, scan_progress, last_error, stop_event, scan_start_time
        stop_event.clear()
        scan_active = True
        scan_start_time = time.time()
        scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running VPN speedtest..."}
        last_error = None
        _flush_scan_state()
        
        flusher = threading.Thread(target=_state_flusher, daemon=True)
        flusher.start()
        
        try:
            if not (os.path.exists(RESULTS_FILE)):
                raise FileNotFoundError(f"Results file not found. Please run a scan first.")
            
            # Load existing results
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                results = json.load(f)
            
            # Auto-migrate results to dictionary-of-dictionaries format if needed
            migrated = False
            if isinstance(results, list):
                logging.info("Migrating results.json from list to dictionary-of-dictionaries format")
                new_results = {}
                for entry in results:
                    if isinstance(entry, dict) and 'domain' in entry:
                        domain = entry.pop('domain')
                        new_results[domain] = entry
                results = new_results
                migrated = True
            elif isinstance(results, dict):
                # Check for dictionary-of-lists format (legacy compatible)
                for domain, data in results.items():
                    if isinstance(data, list):
                        logging.info("Migrating results.json from dictionary-of-lists to dictionary-of-dictionaries format")
                        new_results = {}
                        for d, entry in results.items():
                            if isinstance(entry, list) and len(entry) >= 4:
                                new_results[d] = {
                                    "latency_ms": entry[0],
                                    "ip": entry[1],
                                    "country": entry[2],
                                    "city": entry[3],
                                    "rx_speed_mbps": None,
                                    "tx_speed_mbps": None,
                                    "speedtest_performed": False
                                }
                            else:
                                new_results[d] = entry
                        results = new_results
                        migrated = True
                        break
            
            if migrated:
                # Save migrated version immediately (atomic)
                _tmp = RESULTS_FILE + '.tmp'
                with open(_tmp, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
                os.replace(_tmp, RESULTS_FILE)
            
            if not isinstance(results, dict):
                raise ValueError("Results file is in an invalid format and could not be migrated.")
            
            # If no domains specified, test all domains from results
            domains_to_test = selected_domains if selected_domains else list(results.keys())
            
            # Verify selected domains exist in results
            missing_domains = [d for d in domains_to_test if d not in results]
            if missing_domains:
                logging.warning(f"Selected domains not found in results: {missing_domains}")
            
            # Filter to only domains that exist
            valid_domains = [d for d in domains_to_test if d in results]
            
            scan_progress['total'] = len(valid_domains)
            scan_logger.info(f'VPN speedtest started: {len(valid_domains)} domains')
            
            scanner = Scanner(
                targets_file=SERVERS_FILE,
                city_db=GEOIP_CITY,
                country_db=GEOIP_COUNTRY,
                results_json=RESULTS_FILE,
                excl_countries_fle='exclude_countries.list'
            )
            
            vpn_start_time = time.time()
            # Perform speedtests only on selected domains
            if valid_domains:
                report = scanner._perform_vpn_speedtests(
                    results,
                    VPN_OVPN_DIR,
                    VPN_USERNAME,
                    VPN_PASSWORD,
                    scan_progress,
                    batch_size=999,  # No batching in Web UI
                    interactive=False,
                    selected_domains=valid_domains,
                    stop_event=stop_event,
                    results_file=RESULTS_FILE
                ) or {}
            else:
                raise ValueError("None of the selected domains were found in the scan results")
            
            duration = _format_duration(time.time() - vpn_start_time)
            report_msg = f"{report.get('succeeded', 0)} succeeded, {report.get('vpn_failed', 0)} VPN failed, {report.get('speedtest_failed', 0)} speedtest failed"
            if stop_event.is_set():
                scan_progress['status'] = 'completed'
                scan_progress['message'] = f'VPN speedtest interrupted \u2014 {report_msg}'
                scan_logger.info(f'VPN speedtest interrupted: {scan_progress["done"]}/{len(valid_domains)} domains ({duration}) \u2014 {report_msg}')
            else:
                scan_progress['status'] = 'completed'
                scan_progress['message'] = f'VPN speedtest completed \u2014 {report_msg}'
                scan_logger.info(f'VPN speedtest completed: {len(valid_domains)} domains ({duration}) \u2014 {report_msg}')
                send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete',
                          f'{len(valid_domains)} servers tested ({duration})\n{report_msg}')
        except Exception as e:
            last_error = str(e)
            scan_progress['status'] = 'error'
            scan_progress['message'] = str(e)
            logging.error(f"VPN speedtest failed: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
        finally:
            scan_active = False
            _flush_scan_state()
            _update_last_run('vpn_speedtest')
    
    thread = threading.Thread(target=run_vpn_speedtest_background)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    global stop_event, scan_active
    if not _is_scan_active():
        return jsonify({"status": "error", "message": "No scan in progress"}), 400
    
    stop_event.set()
    # Write stop request to file for cross-worker communication
    state = _read_scan_state()
    state['stop_requested'] = True
    try:
        tmp = SCAN_STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(state, f)
        os.replace(tmp, SCAN_STATE_FILE)
    except Exception:
        pass
    logging.info("Stop signal sent to scanner...")
    return jsonify({"status": "stopping"})

# ---- Speedtest Queue API ----

@app.route('/api/queue/add', methods=['POST'])
def queue_add():
    """Add domains to the server-side speedtest queue."""
    data = request.json or {}
    domains = data.get('domains', [])
    job_type = data.get('type', 'untested')
    label = data.get('label', '')
    if not domains:
        return jsonify({"status": "error", "message": "No domains provided"}), 400
    pending = _queue_add_job(domains, job_type, label)
    _ensure_queue_processor()
    return jsonify({"status": "queued", "pending": pending})

@app.route('/api/queue/status')
def queue_status():
    """Return current queue info from shared file (works across gunicorn workers)."""
    qs = _read_queue_file()
    pending_jobs = qs.get("pending", [])
    active = qs.get("active")
    total_domains = sum(len(j.get("domains", [])) for j in pending_jobs)
    jobs = [{"domains": len(j.get("domains", [])), "type": j.get("type", ""), "label": j.get("label", "")} for j in pending_jobs]
    scan_state = _read_scan_state()
    progress = scan_state.get("progress", {})
    scan_running = _is_scan_active()
    return jsonify({
        "pending": len(jobs), "total_domains": total_domains, "jobs": jobs,
        "active": active, "scan_active": scan_running,
        "progress_done": progress.get("done", 0) if scan_running else 0,
        "progress_total": progress.get("total", 0) if scan_running else 0
    })

@app.route('/api/queue/clear', methods=['POST'])
def queue_clear():
    """Clear all pending queue items (does not stop a running scan)."""
    count = _queue_clear_all()
    return jsonify({"status": "cleared", "removed": count})

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

@app.route('/api/geolite/status')
def geolite_status():
    """Check local GeoLite2 file dates and latest available release."""
    city_path = Path(GEOIP_CITY)
    country_path = Path(GEOIP_COUNTRY)

    local_city_mtime = None
    local_country_mtime = None
    if city_path.exists():
        local_city_mtime = datetime.fromtimestamp(city_path.stat().st_mtime, tz=timezone.utc).isoformat()
    if country_path.exists():
        local_country_mtime = datetime.fromtimestamp(country_path.stat().st_mtime, tz=timezone.utc).isoformat()

    # Fetch latest release info from GitHub
    latest_release_date = None
    latest_tag = None
    update_available = False
    try:
        resp = http_requests.get(GEOLITE_RELEASE_URL, timeout=10)
        resp.raise_for_status()
        release = resp.json()
        latest_tag = release.get('tag_name', '')
        latest_release_date = release.get('published_at', '')
        if local_city_mtime and latest_release_date:
            local_dt = city_path.stat().st_mtime
            release_dt = datetime.fromisoformat(latest_release_date.replace('Z', '+00:00')).timestamp()
            update_available = release_dt > local_dt
        elif not local_city_mtime:
            update_available = True
    except Exception:
        pass

    return jsonify({
        'city_last_modified': local_city_mtime,
        'country_last_modified': local_country_mtime,
        'latest_release_tag': latest_tag,
        'latest_release_date': latest_release_date,
        'update_available': update_available
    })

@app.route('/api/geolite/update', methods=['POST'])
def geolite_update():
    """Download latest GeoLite2 databases from GitHub releases."""
    try:
        downloaded = _do_geolite_update()
        if not downloaded:
            return jsonify({'status': 'error', 'message': 'No matching assets found in release'}), 404
        send_ntfy('geolite_updated', 'GeoLite2 Updated', f'Updated: {", ".join(downloaded)}')
        return jsonify({'status': 'ok', 'updated': downloaded})
    except Exception as e:
        logging.error(f'GeoLite2 update failed: {e}')
        send_ntfy('geolite_update_error', 'GeoLite2 Update Failed', str(e), priority='high')
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/servers', methods=['GET'])
def get_servers():
    """Return the current servers.list content."""
    if not os.path.exists(SERVERS_FILE):
        return jsonify({'servers': ''})
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        return jsonify({'servers': f.read()})

@app.route('/api/servers', methods=['POST'])
def save_servers():
    """Save servers.list content."""
    data = request.json or {}
    content = data.get('servers', '')
    # Normalize: strip each line, remove blanks, deduplicate while preserving order
    lines = [line.strip() for line in content.splitlines()]
    lines = list(dict.fromkeys(line for line in lines if line))
    tmp = SERVERS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))
    os.replace(tmp, SERVERS_FILE)
    logging.info(f'servers.list updated: {len(lines)} entries')
    return jsonify({'status': 'ok', 'count': len(lines)})

@app.route('/api/ovpn/status')
def ovpn_status():
    """Return ovpn folder stats: file count and newest file mtime."""
    ovpn_path = Path(VPN_OVPN_DIR)
    if not ovpn_path.is_dir():
        return jsonify({'count': 0, 'last_updated': None})
    files = list(ovpn_path.glob('*.ovpn'))
    count = len(files)
    newest = None
    if files:
        newest_mtime = max(f.stat().st_mtime for f in files)
        newest = datetime.fromtimestamp(newest_mtime, tz=timezone.utc).isoformat()
    return jsonify({'count': count, 'last_updated': newest})

@app.route('/api/ovpn/upload', methods=['POST'])
def ovpn_upload():
    """Accept a ZIP upload, extract *udp*.ovpn files into the ovpn directory."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
    uploaded = request.files['file']
    if not uploaded.filename.lower().endswith('.zip'):
        return jsonify({'status': 'error', 'message': 'File must be a .zip'}), 400

    try:
        zip_bytes = uploaded.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if os.path.isabs(name) or '..' in name:
                    return jsonify({'status': 'error', 'message': f'Invalid path in zip: {name}'}), 400

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
        send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{extracted} UDP configs extracted')
        return jsonify({'status': 'ok', 'count': extracted})
    except zipfile.BadZipFile:
        return jsonify({'status': 'error', 'message': 'Invalid ZIP file'}), 400
    except Exception as e:
        logging.error(f'OVPN upload failed: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ovpn/download', methods=['POST'])
def ovpn_download():
    """Download OVPN configs from configured or provided URL."""
    data = request.json or {}
    url = data.get('url', '')
    if not url:
        config = load_config()
        url = config.get('schedule', {}).get('ovpn_update', {}).get('download_url', '')
    if not url:
        return jsonify({'status': 'error', 'message': 'No download URL configured'}), 400
    try:
        count = _download_ovpn_from_url(url)
        send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{count} UDP configs extracted')
        return jsonify({'status': 'ok', 'count': count})
    except Exception as e:
        logging.error(f'OVPN download failed: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================================
# OVPN Config Viewer
# ============================================================
@app.route('/api/ovpn/config/<domain>')
def get_ovpn_config(domain):
    """Return the OVPN config text for a given domain."""
    # Sanitize: only allow valid domain characters
    if not all(c.isalnum() or c in '.-' for c in domain):
        return jsonify({'status': 'error', 'message': 'Invalid domain'}), 400
    ovpn_path = Path(VPN_OVPN_DIR)
    # Try common naming patterns
    for pattern in [f'{domain}.udp.ovpn', f'{domain}.tcp.ovpn', f'{domain}.ovpn']:
        candidate = ovpn_path / pattern
        if candidate.exists():
            return jsonify({'status': 'ok', 'filename': candidate.name,
                            'content': candidate.read_text(encoding='utf-8', errors='replace')})
    return jsonify({'status': 'error', 'message': f'No OVPN config found for {domain}'}), 404


# ============================================================
# Geo Results API (for map view)
# ============================================================
@app.route('/api/results/geo')
def get_results_geo():
    """Return results with lat/lon resolved from GeoIP City database."""
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    if not os.path.exists(GEOIP_CITY):
        return jsonify({'error': 'GeoIP City database not found'}), 500
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        reader = geoip2.database.Reader(GEOIP_CITY)
        results = []
        try:
            for domain, entry in data.items():
                if not isinstance(entry, dict):
                    continue
                ip = entry.get('ip')
                if not ip:
                    continue
                try:
                    geo = reader.city(ip)
                    lat = geo.location.latitude
                    lon = geo.location.longitude
                except Exception:
                    continue
                if lat is None or lon is None:
                    continue
                results.append({
                    'domain': domain,
                    'ip': ip,
                    'lat': lat,
                    'lon': lon,
                    'country': entry.get('country', 'Unknown'),
                    'city': entry.get('city', 'Unknown'),
                    'latency_ms': entry.get('latency_ms'),
                    'rx_speed_mbps': entry.get('rx_speed_mbps'),
                    'tx_speed_mbps': entry.get('tx_speed_mbps')
                })
        finally:
            reader.close()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Measurement origin (vantage point) ----
_origin_cache = {'auto': None, 'manual': None}

def _detect_origin_from_geoip():
    """Detect origin using public IP resolved through local GeoIP DB.
    Called once at service startup so VPN tunnels opened later don't affect it."""
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


@app.route('/api/origin')
def get_origin():
    """Return the measurement origin (vantage point) location."""
    config = load_config()
    mt = config.get('theme', {}).get('map_thresholds', {})
    origin_mode = mt.get('origin_mode', 'auto')

    if origin_mode == 'manual':
        # Re-geocode only if address changed (cache the last manual result)
        addr = mt.get('origin_address', {})
        cached = _origin_cache.get('manual')
        if cached and cached.get('_addr') == addr:
            return jsonify(cached)
        result = _geocode_address(
            addr.get('country', ''),
            addr.get('city', ''),
            addr.get('zipcode', '')
        )
        if result:
            result['_addr'] = addr
            _origin_cache['manual'] = result
            resp_data = {k: v for k, v in result.items() if k != '_addr'}
            return jsonify(resp_data)

    # Auto mode — return the startup-detected origin
    if _origin_cache['auto']:
        return jsonify(_origin_cache['auto'])

    return jsonify({'error': 'Could not determine origin location'}), 500
VALID_PALETTES = {'default', 'midnight', 'emerald', 'sunset', 'arctic', 'rose', 'sandstorm', 'carbon', 'pihole', 'backstage', 'dracula', 'nord'}
VALID_WALLPAPERS = {'none', 'grid', 'dots', 'hexagons', 'circuit_board', 'network', 'globe', 'radar', 'city_lights', 'data_flow', 'topology', 'server_rack', 'signal_waves', 'matrix', 'constellation', 'diamonds', 'crosses', 'waves', 'triangles', 'custom', 'video_matrix', 'video_starfield', 'video_particles', 'video_aurora', 'video_fireflies', 'video_blue_polygon', 'video_black_hole', 'video_digital_globe', 'video_blue_code', 'video_white_lines', 'video_custom'}
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.svg'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm'}
MAX_WALLPAPER_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_VIDEO_WALLPAPER_SIZE = 50 * 1024 * 1024  # 50 MB

@app.route('/api/theme')
def get_theme():
    config = load_config()
    theme = config.get('theme', {})
    return jsonify({
        'palette': theme.get('palette', 'default'),
        'wallpaper': theme.get('wallpaper', 'none'),
        'wallpaper_mode': theme.get('wallpaper_mode', 'tile'),
        'map_thresholds': theme.get('map_thresholds', {
            'auto_color_latency': False,
            'auto_color_speed': False,
            'show_all_servers': False,
            'latency': {'green': 50, 'yellow': 150},
            'speed': {'red': 50, 'yellow': 200}
        })
    })

VALID_WALLPAPER_MODES = {'tile', 'cover', 'contain'}

@app.route('/api/theme', methods=['POST'])
def post_theme():
    data = request.json or {}
    palette = data.get('palette', 'default')
    wallpaper = data.get('wallpaper', 'none')
    wallpaper_mode = data.get('wallpaper_mode', 'tile')
    map_thresholds = data.get('map_thresholds')
    if palette not in VALID_PALETTES:
        palette = 'default'
    if wallpaper not in VALID_WALLPAPERS:
        wallpaper = 'none'
    if wallpaper_mode not in VALID_WALLPAPER_MODES:
        wallpaper_mode = 'tile'
    with _config_lock:
        config = load_config()
        theme_data = {'palette': palette, 'wallpaper': wallpaper, 'wallpaper_mode': wallpaper_mode}
        if isinstance(map_thresholds, dict):
            theme_data['map_thresholds'] = map_thresholds
        else:
            theme_data['map_thresholds'] = config.get('theme', {}).get('map_thresholds', {
                'auto_color_latency': False,
                'auto_color_speed': False,
                'show_all_servers': False,
                'latency': {'green': 50, 'yellow': 150},
                'speed': {'red': 50, 'yellow': 200}
            })
        config['theme'] = theme_data
        save_config(config)
    # Invalidate manual origin cache so address changes take effect
    _origin_cache['manual'] = None
    return jsonify({'status': 'ok'})


@app.route('/api/wallpaper/upload', methods=['POST'])
def upload_wallpaper():
    """Upload a custom wallpaper image (png/jpg/webp/svg, max 5 MB)."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({'status': 'error', 'message': 'Empty filename'}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        return jsonify({'status': 'error', 'message': f'Allowed types: {allowed}'}), 400
    data = uploaded.read()
    if len(data) > MAX_WALLPAPER_SIZE:
        return jsonify({'status': 'error', 'message': 'File exceeds 5 MB limit'}), 400
    wp_dir = Path(WALLPAPER_DIR)
    wp_dir.mkdir(parents=True, exist_ok=True)
    # Remove any previous custom wallpaper
    for old in wp_dir.iterdir():
        if old.stem == 'custom':
            old.unlink()
    target = wp_dir / f'custom{ext}'
    target.write_bytes(data)
    # Auto-set theme wallpaper to custom
    with _config_lock:
        config = load_config()
        theme = config.get('theme', {})
        theme['wallpaper'] = 'custom'
        config['theme'] = theme
        save_config(config)
    logging.info(f'Custom wallpaper uploaded: {uploaded.filename} ({len(data)} bytes)')
    return jsonify({'status': 'ok', 'url': '/api/wallpaper/custom'})


@app.route('/api/wallpaper/custom')
def serve_custom_wallpaper():
    """Serve the uploaded custom wallpaper image."""
    wp_dir = Path(WALLPAPER_DIR)
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        candidate = wp_dir / f'custom{ext}'
        if candidate.exists():
            mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'webp': 'image/webp', 'svg': 'image/svg+xml'}
            return send_from_directory(str(wp_dir), candidate.name,
                                      mimetype=mime.get(ext.lstrip('.'), 'application/octet-stream'))
    return jsonify({'status': 'error', 'message': 'No custom wallpaper found'}), 404


@app.route('/api/wallpaper/custom', methods=['DELETE'])
def delete_custom_wallpaper():
    """Delete the custom wallpaper and reset to 'none'."""
    wp_dir = Path(WALLPAPER_DIR)
    deleted = False
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        candidate = wp_dir / f'custom{ext}'
        if candidate.exists():
            candidate.unlink()
            deleted = True
    with _config_lock:
        config = load_config()
        theme = config.get('theme', {})
        if theme.get('wallpaper') == 'custom':
            theme['wallpaper'] = 'none'
            config['theme'] = theme
            save_config(config)
    return jsonify({'status': 'ok', 'deleted': deleted})


@app.route('/api/wallpaper/video/upload', methods=['POST'])
def upload_video_wallpaper():
    """Upload a custom video wallpaper (mp4/webm, max 50 MB)."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({'status': 'error', 'message': 'Empty filename'}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({'status': 'error', 'message': 'Allowed types: .mp4, .webm'}), 400
    data = uploaded.read()
    if len(data) > MAX_VIDEO_WALLPAPER_SIZE:
        return jsonify({'status': 'error', 'message': 'File exceeds 50 MB limit'}), 400
    wp_dir = Path(WALLPAPER_DIR)
    wp_dir.mkdir(parents=True, exist_ok=True)
    for old in wp_dir.iterdir():
        if old.stem == 'video_custom':
            old.unlink()
    target = wp_dir / f'video_custom{ext}'
    target.write_bytes(data)
    with _config_lock:
        config = load_config()
        theme = config.get('theme', {})
        theme['wallpaper'] = 'video_custom'
        config['theme'] = theme
        save_config(config)
    logging.info(f'Custom video wallpaper uploaded: {uploaded.filename} ({len(data)} bytes)')
    return jsonify({'status': 'ok'})


@app.route('/api/wallpaper/video')
def serve_video_wallpaper():
    """Serve the uploaded custom video wallpaper."""
    wp_dir = Path(WALLPAPER_DIR)
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        candidate = wp_dir / f'video_custom{ext}'
        if candidate.exists():
            mime = {'.mp4': 'video/mp4', '.webm': 'video/webm'}
            return send_from_directory(str(wp_dir), candidate.name,
                                      mimetype=mime.get(ext, 'video/mp4'))
    return jsonify({'status': 'error', 'message': 'No custom video found'}), 404


@app.route('/api/wallpaper/video', methods=['DELETE'])
def delete_video_wallpaper():
    """Delete the custom video wallpaper."""
    wp_dir = Path(WALLPAPER_DIR)
    deleted = False
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        candidate = wp_dir / f'video_custom{ext}'
        if candidate.exists():
            candidate.unlink()
            deleted = True
    with _config_lock:
        config = load_config()
        theme = config.get('theme', {})
        if theme.get('wallpaper') == 'video_custom':
            theme['wallpaper'] = 'none'
            config['theme'] = theme
            save_config(config)
    return jsonify({'status': 'ok', 'deleted': deleted})

# ============================================================
# Config API
# ============================================================
@app.route('/api/config')
def get_config():
    return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def post_config():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    # Validate: OVPN schedule requires download URL
    ovpn_sched = data.get('schedule', {}).get('ovpn_update', {})
    if ovpn_sched.get('enabled') and not ovpn_sched.get('download_url', '').strip():
        return jsonify({'status': 'error', 'message': 'OVPN Config Update requires a Download URL. Disable the schedule or provide a URL.'}), 400
    # Strip legacy ovpn top-level key
    data.pop('ovpn', None)
    # Preserve last_run timestamps from existing config
    with _config_lock:
        existing = load_config()
        for key in ['vpn_speedtest', 'geolite_update', 'ovpn_update', 'servers_update']:
            lr = existing.get('schedule', {}).get(key, {}).get('last_run')
            if lr:
                data.setdefault('schedule', {}).setdefault(key, {}).setdefault('last_run', lr)
        # Preserve theme (managed separately via /api/theme)
        theme = existing.get('theme')
        if theme:
            data['theme'] = theme
        save_config(data)
    apply_schedules()
    return jsonify({'status': 'ok'})

# ============================================================
# VPN Credentials API (stored in .env, not in config.yaml)
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

@app.route('/api/credentials')
def get_credentials():
    env = _read_env_file()
    username = env.get('VPN_USERNAME', '')
    password = env.get('VPN_PASSWORD', '')
    return jsonify({
        'vpn_password_set': bool(password),
        'vpn_username_masked': (username[:3] + '***') if len(username) > 3 else ('***' if username else '')
    })

@app.route('/api/credentials', methods=['POST'])
def post_credentials():
    global VPN_USERNAME, VPN_PASSWORD
    data = request.json or {}
    username = data.get('vpn_username')
    password = data.get('vpn_password')
    if username is None and password is None:
        return jsonify({'status': 'error', 'message': 'No credentials provided'}), 400
    env = _read_env_file()
    if username is not None:
        env['VPN_USERNAME'] = username
        VPN_USERNAME = username
    if password is not None:
        env['VPN_PASSWORD'] = password
        VPN_PASSWORD = password
    _write_env_file(env)
    return jsonify({'status': 'ok'})

@app.route('/api/config/test-notification', methods=['POST'])
def test_notification():
    config = load_config()
    ntfy = config.get('notifications', {}).get('ntfy', {})
    if not ntfy.get('enabled') or not ntfy.get('url'):
        return jsonify({'status': 'error', 'message': 'ntfy is not enabled or URL is not set'}), 400
    try:
        resp = http_requests.post(
            ntfy['url'],
            data='This is a test notification from GeoIP Performance Analyzer.'.encode('utf-8'),
            headers={'Title': 'Test Notification', 'Priority': 'default'},
            timeout=10
        )
        resp.raise_for_status()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/schedule/run', methods=['POST'])
def run_schedule_now():
    data = request.json or {}
    job_name = data.get('job', '')
    runners = {
        'vpn_speedtest': lambda: threading.Thread(target=scheduled_vpn_speedtest, daemon=True).start(),
        'latency_scan': lambda: threading.Thread(target=scheduled_latency_scan, daemon=True).start(),
        'geolite_update': lambda: threading.Thread(target=scheduled_geolite_update, daemon=True).start(),
        'ovpn_update': lambda: threading.Thread(target=scheduled_ovpn_update, daemon=True).start(),
        'servers_update': lambda: threading.Thread(target=scheduled_servers_update, daemon=True).start(),
    }
    runner = runners.get(job_name)
    if not runner:
        return jsonify({'status': 'error', 'message': f'Unknown job: {job_name}'}), 400
    runner()
    return jsonify({'status': 'ok', 'message': f'{job_name} started'})


@app.route('/api/schedule/next')
def get_schedule_next_runs():
    """Return next scheduled run times for all active jobs."""
    result = {}
    for job in scheduler.get_jobs():
        nrt = job.next_run_time
        if nrt:
            result[job.id] = nrt.strftime('%Y-%m-%d %H:%M')
    return jsonify(result)


@app.route('/api/statistics')
def get_statistics():
    """Return per-country statistics for the statistics page."""
    if not os.path.exists(RESULTS_FILE):
        return jsonify({'countries': [], 'top5': []})
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return jsonify({'countries': [], 'top5': []})

    countries = {}  # country -> stats dict
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        country = entry.get('country', 'Unknown')
        if country not in countries:
            countries[country] = {
                'country': country,
                'servers': 0,
                'lowest_latency': None, 'lowest_latency_server': None,
                'highest_download': None, 'highest_download_server': None,
                'highest_upload': None, 'highest_upload_server': None,
                'succeeded': 0, 'failed': 0, 'untested': 0,
                'untested_domains': [], 'failed_domains': []
            }
        c = countries[country]
        c['servers'] += 1
        lat = entry.get('latency_ms')
        rx = entry.get('rx_speed_mbps')
        tx = entry.get('tx_speed_mbps')
        ts = entry.get('speedtest_timestamp')
        if lat is not None and lat > 0:
            if c['lowest_latency'] is None or lat < c['lowest_latency']:
                c['lowest_latency'] = lat
                c['lowest_latency_server'] = domain
        if rx is not None and rx > 0:
            c['succeeded'] += 1
            if c['highest_download'] is None or rx > c['highest_download']:
                c['highest_download'] = rx
                c['highest_download_server'] = domain
        elif ts:
            c['failed'] += 1
            c['failed_domains'].append(domain)
        else:
            c['untested'] += 1
            c['untested_domains'].append(domain)
        if tx is not None and tx > 0:
            if c['highest_upload'] is None or tx > c['highest_upload']:
                c['highest_upload'] = tx
                c['highest_upload_server'] = domain

    stats_list = sorted(countries.values(), key=lambda x: x['country'])
    # Remove domain lists from response (keep counts only, use separate lists for action)
    for s in stats_list:
        del s['untested_domains']
        del s['failed_domains']

    # Top N recommended: best download speed per country
    top_n = max(1, min(100, request.args.get('top', 5, type=int)))
    best_per_country = []
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        rx = entry.get('rx_speed_mbps')
        if rx and rx > 0:
            best_per_country.append({
                'domain': domain,
                'country': entry.get('country', 'Unknown'),
                'city': entry.get('city', 'Unknown'),
                'rx_speed_mbps': rx,
                'tx_speed_mbps': entry.get('tx_speed_mbps'),
                'latency_ms': entry.get('latency_ms')
            })
    # Group by country, pick best download per country
    best_map = {}
    for s in best_per_country:
        c = s['country']
        if c not in best_map or s['rx_speed_mbps'] > best_map[c]['rx_speed_mbps']:
            best_map[c] = s
    top_sorted = sorted(best_map.values(), key=lambda x: x['rx_speed_mbps'], reverse=True)
    top_list = top_sorted[:top_n] if top_n < len(top_sorted) else top_sorted

    return jsonify({'countries': stats_list, 'top': top_list, 'total_countries': len(best_map)})


@app.route('/api/top-servers')
def get_top_servers():
    """Return top N servers (best download per country). Query param: n (default 5)."""
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return jsonify([])
    n = max(1, min(100, request.args.get('n', 5, type=int)))
    best_map = {}
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        rx = entry.get('rx_speed_mbps')
        if rx and rx > 0:
            c = entry.get('country', 'Unknown')
            if c not in best_map or rx > best_map[c]['rx_speed_mbps']:
                best_map[c] = {
                    'domain': domain,
                    'country': c,
                    'city': entry.get('city', 'Unknown'),
                    'rx_speed_mbps': rx,
                    'tx_speed_mbps': entry.get('tx_speed_mbps'),
                    'latency_ms': entry.get('latency_ms')
                }
    top_sorted = sorted(best_map.values(), key=lambda x: x['rx_speed_mbps'], reverse=True)
    result = top_sorted[:n] if n < len(top_sorted) else top_sorted
    return jsonify(result)


@app.route('/api/statistics/domains')
def get_statistics_domains():
    """Return untested/failed domain lists per country (or all) for speedtest triggering."""
    if not os.path.exists(RESULTS_FILE):
        return jsonify({'untested': [], 'failed': []})
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return jsonify({'untested': [], 'failed': []})
    country_filter = request.args.get('country')
    untested = []
    failed = []
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if country_filter and entry.get('country') != country_filter:
            continue
        rx = entry.get('rx_speed_mbps')
        ts = entry.get('speedtest_timestamp')
        if rx is not None and rx > 0:
            continue  # succeeded
        if ts:
            failed.append(domain)
        else:
            untested.append(domain)
    return jsonify({'untested': untested, 'failed': failed})


@app.route('/statistics')
def statistics_page():
    return render_template('statistics.html')


# ============================================================
# Prune stale results (servers no longer in servers.list)
# ============================================================
def _prune_stale_results():
    """Remove results entries whose domain is not in servers.list.
    Returns (pruned_count, remaining_count) or raises on safety check failure."""
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

@app.route('/api/prune-stale', methods=['POST'])
def prune_stale():
    try:
        pruned, remaining = _prune_stale_results()
        if pruned == 0:
            return jsonify({'status': 'ok', 'message': 'No stale servers found'})
        return jsonify({'status': 'ok', 'message': f'Removed {pruned} stale servers ({remaining} remaining)'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# ============================================================
# Top Results API (for programmatic access)
# ============================================================
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

@app.route('/api/v1/top/latency')
def top_latency():
    n = request.args.get('n', 5, type=int)
    countries = _parse_countries(request.args)
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict):
            if countries and entry.get('country', '').lower() not in countries:
                continue
            items.append({
                'domain': domain,
                'latency_ms': entry.get('latency_ms', 9999),
                'ip': entry.get('ip', ''),
                'country': entry.get('country', ''),
                'city': entry.get('city', ''),
                'rx_speed_mbps': entry.get('rx_speed_mbps'),
                'tx_speed_mbps': entry.get('tx_speed_mbps')
            })
    items.sort(key=lambda x: x['latency_ms'])
    return jsonify(items[:n])

@app.route('/api/v1/top/download')
def top_download():
    n = request.args.get('n', 5, type=int)
    countries = _parse_countries(request.args)
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('rx_speed_mbps') is not None:
            if countries and entry.get('country', '').lower() not in countries:
                continue
            items.append({
                'domain': domain,
                'rx_speed_mbps': entry.get('rx_speed_mbps', 0),
                'tx_speed_mbps': entry.get('tx_speed_mbps', 0),
                'latency_ms': entry.get('latency_ms', 0),
                'ip': entry.get('ip', ''),
                'country': entry.get('country', ''),
                'city': entry.get('city', '')
            })
    items.sort(key=lambda x: x['rx_speed_mbps'], reverse=True)
    return jsonify(items[:n])

@app.route('/api/v1/top/upload')
def top_upload():
    n = request.args.get('n', 5, type=int)
    countries = _parse_countries(request.args)
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('tx_speed_mbps') is not None:
            if countries and entry.get('country', '').lower() not in countries:
                continue
            items.append({
                'domain': domain,
                'tx_speed_mbps': entry.get('tx_speed_mbps', 0),
                'rx_speed_mbps': entry.get('rx_speed_mbps', 0),
                'latency_ms': entry.get('latency_ms', 0),
                'ip': entry.get('ip', ''),
                'country': entry.get('country', ''),
                'city': entry.get('city', '')
            })
    items.sort(key=lambda x: x['tx_speed_mbps'], reverse=True)
    return jsonify(items[:n])

import re as _re
_LOG_LINE_RE = _re.compile(r'^(\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2}))\s+\[(\w+)]\s+(.*)')

@app.route('/api/logs')
def get_logs():
    """Return last 200 log entries from the shared general.log file."""
    fpath = os.path.join(LOG_DIR, 'general.log')
    if not os.path.exists(fpath):
        return jsonify([])
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    tail = all_lines[-200:]
    entries = []
    for line in tail:
        line = line.rstrip()
        if not line:
            continue
        m = _LOG_LINE_RE.match(line)
        if m:
            entries.append({"timestamp": m.group(2), "level": m.group(3), "message": m.group(4)})
        elif entries:
            # Continuation line — append to previous entry
            entries[-1]["message"] += "\n" + line
    return jsonify(entries)

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Truncate the general.log file."""
    fpath = os.path.join(LOG_DIR, 'general.log')
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            pass
    except Exception:
        pass
    return jsonify({"status": "cleared"})

LOG_FILE_MAP = {'general': 'general.log', 'error': 'error.log', 'scan': 'scan.log'}

@app.route('/api/logs/files')
def list_log_files():
    """List available log files with sizes."""
    files = []
    for key, fname in LOG_FILE_MAP.items():
        fpath = os.path.join(LOG_DIR, fname)
        if os.path.exists(fpath):
            files.append({'name': key, 'file': fname, 'size': os.path.getsize(fpath)})
        else:
            files.append({'name': key, 'file': fname, 'size': 0})
    return jsonify(files)

@app.route('/api/logs/file/<name>')
def get_log_file(name):
    """Return tail of a log file. ?lines=N (default 200)."""
    fname = LOG_FILE_MAP.get(name)
    if not fname:
        return jsonify({'error': 'Unknown log file'}), 404
    fpath = os.path.join(LOG_DIR, fname)
    if not os.path.exists(fpath):
        return jsonify({'lines': [], 'total': 0})
    lines_n = request.args.get('lines', 500, type=int)
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    tail = all_lines[-lines_n:] if len(all_lines) > lines_n else all_lines
    return jsonify({'lines': [l.rstrip() for l in tail], 'total': len(all_lines)})

# ============================================================
# Scheduler
# ============================================================
scheduler = BackgroundScheduler(daemon=True)

DAY_MAP = {
    'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
    'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
}

def _resolve_scheduled_domains():
    """Resolve the domain list for the scheduled VPN speedtest. Returns list or None on error."""
    if not os.path.exists(RESULTS_FILE):
        logging.error("Scheduled VPN speedtest skipped: no results.json (run a scan first)")
        send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed',
                  'No results.json found. Run a scan first.', priority='high')
        return None
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
        all_domains = list(results.keys()) if isinstance(results, dict) else []
        if not all_domains:
            logging.error("Scheduled VPN speedtest skipped: no domains in results")
            return None
        # Filter by countries if configured
        config = load_config()
        vpn_countries = config.get('schedule', {}).get('vpn_speedtest', {}).get('countries', [])
        if vpn_countries:
            country_set = {c.casefold() for c in vpn_countries}
            all_domains = [d for d in all_domains if isinstance(results.get(d), dict) and results[d].get('country', '').casefold() in country_set]
            if not all_domains:
                logging.error("Scheduled VPN speedtest skipped: no servers match selected countries")
                return None
        return all_domains
    except Exception as e:
        logging.error(f"Scheduled VPN speedtest failed to resolve domains: {e}")
        return None


def scheduled_vpn_speedtest():
    global scan_active, scan_progress, last_error, stop_event, scan_start_time

    all_domains = _resolve_scheduled_domains()
    if not all_domains:
        return

    # If another scan/test is running, queue instead of skipping
    if _is_scan_active():
        logging.info("Scheduled VPN speedtest queued: operation already in progress (%d domains)", len(all_domains))
        scan_logger.info('Scheduled VPN speedtest queued (scan in progress): %d domains', len(all_domains))
        _queue_add_job(all_domains, 'scheduled', f'Scheduled ({len(all_domains)} servers)')
        _ensure_queue_processor()
        return

    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
        logging.info(f"Starting scheduled VPN speedtest on {len(all_domains)} servers...")
        scan_logger.info(f'Scheduled VPN speedtest started: {len(all_domains)} servers')
        vpn_start_time = time.time()
        stop_event.clear()
        scan_active = True
        scan_start_time = vpn_start_time
        scan_progress = {"done": 0, "total": len(all_domains), "status": "running", "message": "Running scheduled VPN speedtest..."}
        last_error = None
        _flush_scan_state()
        flusher = threading.Thread(target=_state_flusher, daemon=True)
        flusher.start()
        scanner = Scanner(
            targets_file=SERVERS_FILE,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )
        report = scanner._perform_vpn_speedtests(
            results, VPN_OVPN_DIR, VPN_USERNAME, VPN_PASSWORD,
            scan_progress, batch_size=999, interactive=False,
            selected_domains=all_domains, stop_event=stop_event
        ) or {}
        _tmp = RESULTS_FILE + '.tmp'
        with open(_tmp, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        os.replace(_tmp, RESULTS_FILE)
        duration = _format_duration(time.time() - vpn_start_time)
        report_msg = f"{report.get('succeeded', 0)} succeeded, {report.get('vpn_failed', 0)} VPN failed, {report.get('speedtest_failed', 0)} speedtest failed"
        if stop_event.is_set():
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'Scheduled VPN speedtest interrupted — {report_msg}'
            scan_logger.info(f'Scheduled VPN speedtest interrupted: {scan_progress["done"]}/{len(all_domains)} servers ({duration}) — {report_msg}')
        else:
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'Scheduled VPN speedtest completed — {report_msg}'
            scan_logger.info(f'Scheduled VPN speedtest completed: {len(all_domains)} servers ({duration}) — {report_msg}')
            send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete',
                      f'{len(all_domains)} servers tested ({duration})\n{report_msg}')
    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scheduled VPN speedtest failed: {e}")
        send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed', str(e), priority='high')
    finally:
        scan_active = False
        _flush_scan_state()
        _update_last_run('vpn_speedtest')

def scheduled_latency_scan():
    global scan_active, scan_progress, last_error, stop_event, scan_start_time

    if _is_scan_active():
        logging.info("Scheduled latency scan skipped: operation already in progress")
        return

    try:
        if not (os.path.exists(GEOIP_CITY) and os.path.exists(GEOIP_COUNTRY)):
            raise FileNotFoundError(f"GeoIP databases not found at {GEOIP_CITY} or {GEOIP_COUNTRY}")

        config = load_config()
        lat_cfg = config.get('schedule', {}).get('latency_scan', {})
        lat_countries = lat_cfg.get('countries', [])
        pings_num = max(1, min(10, int(lat_cfg.get('pings', 1))))
        timeout_ms = max(100, min(10000, int(lat_cfg.get('timeout', 1000))))
        workers = max(1, min(100, int(lat_cfg.get('workers', 20))))

        servers_file, is_temp = _filtered_servers_file(lat_countries)
        scanner = Scanner(
            targets_file=servers_file,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )

        stop_event.clear()
        scan_active = True
        scan_start_time = time.time()
        scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running scheduled latency scan..."}
        last_error = None
        _flush_scan_state()
        flusher = threading.Thread(target=_state_flusher, daemon=True)
        flusher.start()

        logging.info("Starting scheduled latency scan...")
        scan_logger.info('Scheduled latency scan started')
        scanner.scan(
            pings_num=pings_num,
            timeout_ms=timeout_ms,
            workers=workers,
            progress_container=scan_progress,
            vpn_speedtest=False,
            stop_event=stop_event
        )
        duration = _format_duration(time.time() - scan_start_time)
        total = scan_progress.get('total', 0)
        if stop_event.is_set():
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'Scheduled latency scan interrupted — {scan_progress["done"]}/{total} servers'
            scan_logger.info(f'Scheduled latency scan interrupted: {scan_progress["done"]}/{total} servers ({duration})')
        else:
            scan_progress['status'] = 'completed'
            scan_progress['message'] = f'Scheduled latency scan completed — {total} servers'
            scan_logger.info(f'Scheduled latency scan completed: {total} servers ({duration})')
            send_ntfy('latency_scan_complete', 'Latency Scan Complete',
                      f'{total} servers scanned ({duration})')
    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scheduled latency scan failed: {e}")
        send_ntfy('latency_scan_error', 'Latency Scan Failed', str(e), priority='high')
    finally:
        scan_active = False
        _flush_scan_state()
        _update_last_run('latency_scan')
        if is_temp:
            try:
                os.unlink(servers_file)
            except OSError:
                pass

def scheduled_geolite_update():
    try:
        downloaded = _do_geolite_update()
        if downloaded:
            send_ntfy('geolite_updated', 'GeoLite2 Updated', f'Updated: {", ".join(downloaded)}')
    except Exception as e:
        logging.error(f'Scheduled GeoLite2 update failed: {e}')
        send_ntfy('geolite_update_error', 'GeoLite2 Update Failed', str(e), priority='high')
    finally:
        _update_last_run('geolite_update')

def scheduled_ovpn_update():
    config = load_config()
    url = config.get('schedule', {}).get('ovpn_update', {}).get('download_url', '')
    if not url:
        logging.info("Scheduled OVPN update skipped: no download URL configured")
        return
    try:
        count = _download_ovpn_from_url(url)
        send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{count} UDP configs extracted')
    except Exception as e:
        logging.error(f'Scheduled OVPN update failed: {e}')
        send_ntfy('ovpn_update_error', 'OVPN Update Failed', str(e), priority='high')
    finally:
        _update_last_run('ovpn_update')

def _get_servers_commands(config):
    """Get list of enabled commands from config, with backward compat for single 'command' field."""
    srv = config.get('schedule', {}).get('servers_update', {})
    commands = srv.get('commands', [])
    if commands:
        return [c for c in commands if c.get('enabled', True) and c.get('command', '').strip()]
    # Backward compat: single command string
    cmd = srv.get('command', '').strip()
    if cmd:
        return [{'command': cmd, 'label': '', 'enabled': True}]
    return []

def _run_servers_update_commands(commands):
    """Run multiple shell commands and merge their output into servers.list."""
    import shlex
    BLOCKED_PATTERNS = ['rm ', 'rm\t', 'mkfs', 'dd ', ':(){', 'fork', '> /dev/', 'shutdown', 'reboot',
                        'passwd', 'chmod 777', 'curl|', 'wget|', '| bash', '| sh']
    all_hosts = []
    for entry in commands:
        cmd = entry['command']
        label = entry.get('label', '') or 'unnamed'
        # Safety: reject obviously dangerous commands
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
    # Deduplicate while preserving order
    all_hosts = list(dict.fromkeys(all_hosts))
    if not all_hosts:
        raise RuntimeError("All commands produced no output")
    tmp = SERVERS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_hosts) + '\n')
    os.replace(tmp, SERVERS_FILE)
    logging.info(f"servers.list updated: {len(all_hosts)} unique entries")
    return len(all_hosts)

def scheduled_servers_update():
    config = load_config()
    commands = _get_servers_commands(config)
    if not commands:
        logging.info("Scheduled servers update skipped: no commands configured")
        return
    try:
        count = _run_servers_update_commands(commands)
        send_ntfy('servers_updated', 'Servers List Updated', f'{count} servers loaded')
        # Prune stale results if enabled
        if config.get('schedule', {}).get('servers_update', {}).get('prune_stale'):
            try:
                pruned, remaining = _prune_stale_results()
                if pruned:
                    logging.info(f"Auto-pruned {pruned} stale servers from results ({remaining} remaining)")
            except Exception as pe:
                logging.error(f"Auto-prune failed: {pe}")
    except Exception as e:
        logging.error(f'Scheduled servers update failed: {e}')
        send_ntfy('servers_update_error', 'Servers List Update Failed', str(e), priority='high')
    finally:
        _update_last_run('servers_update')

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
    config = load_config()
    scheduler.remove_all_jobs()

    # VPN speedtest schedule
    vpn_cfg = config.get('schedule', {}).get('vpn_speedtest', {})
    if vpn_cfg.get('enabled'):
        kw = _build_cron_kwargs(vpn_cfg)
        scheduler.add_job(scheduled_vpn_speedtest, CronTrigger(**kw), id='vpn_speedtest', replace_existing=True)

    # Latency scan schedule
    lat_cfg = config.get('schedule', {}).get('latency_scan', {})
    if lat_cfg.get('enabled'):
        kw = _build_cron_kwargs(lat_cfg)
        scheduler.add_job(scheduled_latency_scan, CronTrigger(**kw), id='latency_scan', replace_existing=True)

    # GeoLite2 schedule
    geo_cfg = config.get('schedule', {}).get('geolite_update', {})
    if geo_cfg.get('enabled'):
        kw = _build_cron_kwargs(geo_cfg)
        scheduler.add_job(scheduled_geolite_update, CronTrigger(**kw), id='geolite', replace_existing=True)

    # OVPN schedule
    ovpn_cfg = config.get('schedule', {}).get('ovpn_update', {})
    if ovpn_cfg.get('enabled'):
        kw = _build_cron_kwargs(ovpn_cfg)
        scheduler.add_job(scheduled_ovpn_update, CronTrigger(**kw), id='ovpn', replace_existing=True)

    # Servers update schedule
    srv_cfg = config.get('schedule', {}).get('servers_update', {})
    if srv_cfg.get('enabled') and _get_servers_commands(config):
        kw = _build_cron_kwargs(srv_cfg)
        scheduler.add_job(scheduled_servers_update, CronTrigger(**kw), id='servers_update', replace_existing=True)

    jobs = scheduler.get_jobs()
    logging.info(f"Scheduler updated: {len(jobs)} job(s) active")

# Clear stale scan state from previous container crash/restart
_clear_stale_state()

# Detect vantage point once at startup (before VPN tunnels)
_init_origin()

# Initialize scheduler on startup
apply_schedules()
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
