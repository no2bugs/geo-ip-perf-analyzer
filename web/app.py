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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Add parent directory to sys.path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate.scan import Scanner

app = Flask(__name__)

# Log buffer for Web UI
class LogBufferHandler(logging.Handler):
    def __init__(self, capacity=100):
        super().__init__()
        self.capacity = capacity
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

DEFAULT_CONFIG = {
    'schedule': {
        'vpn_speedtest': {
            'enabled': False,
            'interval': 'daily',
            'day': 'monday',
            'days': [],
            'dom': 1,
            'time': '03:00'
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
            'time': '05:00'
        },
        'servers_update': {
            'enabled': False,
            'interval': 'weekly',
            'day': 'sunday',
            'days': [],
            'dom': 1,
            'time': '06:00',
            'command': ''
        }
    },
    'notifications': {
        'ntfy': {
            'enabled': False,
            'url': '',
            'events': {
                'vpn_speedtest_complete': False,
                'vpn_speedtest_error': True,
                'geolite_updated': False,
                'geolite_update_error': True,
                'ovpn_updated': False,
                'ovpn_update_error': True,
                'servers_updated': False,
                'servers_update_error': True
            }
        }
    },
    'ovpn': {
        'download_url': ''
    }
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                if isinstance(cfg, dict):
                    return cfg
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
    return copy.deepcopy(DEFAULT_CONFIG)

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

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
scan_active = False
scan_progress = {"done": 0, "total": 0, "status": "idle", "message": ""}
stop_event = threading.Event()
last_error = None

# File-based state sharing for multi-worker gunicorn
SCAN_STATE_FILE = os.path.join(tempfile.gettempdir(), 'geo_ip_scan_state.json')

def _flush_scan_state():
    """Persist current scan state to file for cross-worker access."""
    state = {
        "active": scan_active,
        "progress": dict(scan_progress),
        "error": last_error,
        "stop_requested": stop_event.is_set()
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

def _state_flusher():
    """Background thread that periodically flushes state and checks for stop requests."""
    while scan_active:
        _flush_scan_state()
        # Check if another worker requested stop
        try:
            state = _read_scan_state()
            if state.get("stop_requested") and not stop_event.is_set():
                stop_event.set()
        except Exception:
            pass
        time.sleep(1)
    _flush_scan_state()

def run_scan_in_background(pings, timeout, workers, vpn_speedtest=False):
    global scan_active, scan_progress, last_error, stop_event
    
    stop_event.clear()
    scan_active = True
    scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Initializing..."}
    last_error = None
    
    flusher = threading.Thread(target=_state_flusher, daemon=True)
    flusher.start()
    
    try:
        # Check if DBs exist
        if not (os.path.exists(GEOIP_CITY) and os.path.exists(GEOIP_COUNTRY)):
            raise FileNotFoundError(f"GeoIP databases not found at {GEOIP_CITY} or {GEOIP_COUNTRY}")
            
        scanner = Scanner(
            targets_file=SERVERS_FILE,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list' # varying based on mount
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

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    global scan_active
    
    state = _read_scan_state()
    if scan_active or state.get('active'):
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
        
    data = request.json or {}
    
    # Check if servers.list exists and is not empty
    if not os.path.exists(SERVERS_FILE):
        return jsonify({
            "status": "error", 
            "message": f"Servers list file missing at: {SERVERS_FILE}. Please create a file named 'servers.list' in the project root directory on your HOST machine."
        }), 400
        
    if os.path.getsize(SERVERS_FILE) == 0:
        return jsonify({
            "status": "error", 
            "message": f"Servers list file is empty: {SERVERS_FILE}. Please add domains to 'servers.list' in your project root on the HOST machine (one domain per line)."
        }), 400

    pings = int(data.get('pings', 1))
    timeout = int(data.get('timeout', 1000))
    workers = int(data.get('workers', 10))
    vpn_speedtest = data.get('vpn_speedtest', False)
    
    thread = threading.Thread(target=run_scan_in_background, args=(pings, timeout, workers, vpn_speedtest))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scan/status')
def get_status():
    # Read from shared file for cross-worker compatibility
    state = _read_scan_state()
    return jsonify({
        "active": state.get("active", scan_active),
        "progress": state.get("progress", scan_progress),
        "error": state.get("error", last_error),
        "stopping": state.get("stop_requested", stop_event.is_set())
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

@app.route('/api/vpn-speedtest', methods=['POST'])
def vpn_speedtest():
    global scan_active
    
    state = _read_scan_state()
    if scan_active or state.get('active'):
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
    
    data = request.json or {}
    selected_domains = data.get('domains', [])
    
    # Run VPN speedtest on selected (or all) domains
    def run_vpn_speedtest_background():
        global scan_active, scan_progress, last_error, stop_event
        print("DEBUG: Background thread run_vpn_speedtest_background started", file=sys.stderr, flush=True)
        stop_event.clear()
        scan_active = True
        scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running VPN speedtest..."}
        last_error = None
        
        flusher = threading.Thread(target=_state_flusher, daemon=True)
        flusher.start()
        
        try:
            print(f"DEBUG: Checking for results file: {RESULTS_FILE}", file=sys.stderr, flush=True)
            if not (os.path.exists(RESULTS_FILE)):
                raise FileNotFoundError(f"Results file not found. Please run a scan first.")
            
            # Load existing results
            print("DEBUG: Loading results.json", file=sys.stderr, flush=True)
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                results = json.load(f)
            print(f"DEBUG: Loaded {len(results)} domains from results.json", file=sys.stderr, flush=True)
            
            # Auto-migrate results to dictionary-of-dictionaries format if needed
            migrated = False
            if isinstance(results, list):
                print("DEBUG: Migrating list results", file=sys.stderr, flush=True)
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
                        print("DEBUG: Migrating dict-of-list results", file=sys.stderr, flush=True)
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
                print("DEBUG: Saving migrated results", file=sys.stderr, flush=True)
                # Save migrated version immediately
                with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
            
            if not isinstance(results, dict):
                raise ValueError("Results file is in an invalid format and could not be migrated.")
            
            # If no domains specified, test all domains from results
            domains_to_test = selected_domains if selected_domains else list(results.keys())
            
            # Verify selected domains exist in results
            missing_domains = [d for d in domains_to_test if d not in results]
            if missing_domains:
                print(f"DEBUG: Missing domains: {missing_domains}", file=sys.stderr, flush=True)
                logging.warning(f"Selected domains not found in results: {missing_domains}")
            
            # Filter to only domains that exist
            valid_domains = [d for d in domains_to_test if d in results]
            print(f"DEBUG: Valid domains for speedtest: {valid_domains}", file=sys.stderr, flush=True)
            
            scan_progress['total'] = len(valid_domains)
            scan_logger.info(f'VPN speedtest started: {len(valid_domains)} domains')
            
            print("DEBUG: Initializing Scanner", file=sys.stderr, flush=True)
            scanner = Scanner(
                targets_file=SERVERS_FILE,
                city_db=GEOIP_CITY,
                country_db=GEOIP_COUNTRY,
                results_json=RESULTS_FILE,
                excl_countries_fle='exclude_countries.list'
            )
            print("DEBUG: Scanner initialized", file=sys.stderr, flush=True)
            
            vpn_start_time = time.time()
            # Perform speedtests only on selected domains
            if valid_domains:
                print("DEBUG: Calling scanner._perform_vpn_speedtests", file=sys.stderr, flush=True)
                scanner._perform_vpn_speedtests(
                    results,
                    VPN_OVPN_DIR,
                    VPN_USERNAME,
                    VPN_PASSWORD,
                    scan_progress,
                    batch_size=999,  # No batching in Web UI
                    interactive=False,
                    selected_domains=valid_domains,
                    stop_event=stop_event
                )
                print("DEBUG: scanner._perform_vpn_speedtests finished", file=sys.stderr, flush=True)
            else:
                raise ValueError("None of the selected domains were found in the scan results")
            
            # Save updated results
            print("DEBUG: Saving final results", file=sys.stderr, flush=True)
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print("DEBUG: Final results saved", file=sys.stderr, flush=True)
            
            scan_progress['status'] = 'completed'
            scan_progress['message'] = 'VPN speedtest completed'
            scan_logger.info(f'VPN speedtest completed: {len(valid_domains)} domains ({_format_duration(time.time() - vpn_start_time)})')
        except Exception as e:
            last_error = str(e)
            scan_progress['status'] = 'error'
            scan_progress['message'] = str(e)
            logging.error(f"VPN speedtest failed: {e}")
            print(f"DEBUG: VPN speedtest failed with exception: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
        finally:
            scan_active = False
            _flush_scan_state()
    
    thread = threading.Thread(target=run_vpn_speedtest_background)
    thread.daemon = True
    thread.start()
    print("DEBUG: Thread started, returning started response", file=sys.stderr, flush=True)
    
    return jsonify({"status": "started"})

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    global stop_event, scan_active
    state = _read_scan_state()
    if not scan_active and not state.get('active'):
        return jsonify({"status": "error", "message": "No scan in progress"}), 400
    
    stop_event.set()
    # Write stop request to file for cross-worker communication
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
            old.unlink()

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
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))
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
                old.unlink()

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
        url = config.get('ovpn', {}).get('download_url', '')
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
    save_config(data)
    apply_schedules()
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
        'geolite_update': lambda: threading.Thread(target=scheduled_geolite_update, daemon=True).start(),
        'ovpn_update': lambda: threading.Thread(target=scheduled_ovpn_update, daemon=True).start(),
        'servers_update': lambda: threading.Thread(target=scheduled_servers_update, daemon=True).start(),
    }
    runner = runners.get(job_name)
    if not runner:
        return jsonify({'status': 'error', 'message': f'Unknown job: {job_name}'}), 400
    runner()
    return jsonify({'status': 'ok', 'message': f'{job_name} started'})

# ============================================================
# Top Results API (for programmatic access)
# ============================================================
@app.route('/api/v1/top/latency')
def top_latency():
    n = request.args.get('n', 5, type=int)
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict):
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
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('rx_speed_mbps') is not None:
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
    if not os.path.exists(RESULTS_FILE):
        return jsonify([])
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('tx_speed_mbps') is not None:
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

@app.route('/api/logs')
def get_logs():
    return jsonify(log_buffer.get_logs())

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    log_buffer.clear()
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

def scheduled_vpn_speedtest():
    global scan_active, scan_progress, last_error, stop_event
    state = _read_scan_state()
    if scan_active or state.get('active'):
        logging.info("Scheduled VPN speedtest skipped: operation already in progress")
        return
    if not os.path.exists(RESULTS_FILE):
        logging.error("Scheduled VPN speedtest skipped: no results.json (run a scan first)")
        send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed',
                  'No results.json found. Run a scan first.', priority='high')
        return
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
        all_domains = list(results.keys()) if isinstance(results, dict) else []
        if not all_domains:
            logging.error("Scheduled VPN speedtest skipped: no domains in results")
            return
        logging.info(f"Starting scheduled VPN speedtest on {len(all_domains)} servers...")
        scan_logger.info(f'Scheduled VPN speedtest started: {len(all_domains)} servers')
        vpn_start_time = time.time()
        stop_event.clear()
        scan_active = True
        scan_progress = {"done": 0, "total": len(all_domains), "status": "running", "message": "Running scheduled VPN speedtest..."}
        last_error = None
        flusher = threading.Thread(target=_state_flusher, daemon=True)
        flusher.start()
        scanner = Scanner(
            targets_file=SERVERS_FILE,
            city_db=GEOIP_CITY,
            country_db=GEOIP_COUNTRY,
            results_json=RESULTS_FILE,
            excl_countries_fle='exclude_countries.list'
        )
        scanner._perform_vpn_speedtests(
            results, VPN_OVPN_DIR, VPN_USERNAME, VPN_PASSWORD,
            scan_progress, batch_size=999, interactive=False,
            selected_domains=all_domains, stop_event=stop_event
        )
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        scan_progress['status'] = 'completed'
        scan_progress['message'] = 'Scheduled VPN speedtest completed'
        scan_logger.info(f'Scheduled VPN speedtest completed: {len(all_domains)} servers ({_format_duration(time.time() - vpn_start_time)})')
        send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete',
                  f'Tested {len(all_domains)} servers')
    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scheduled VPN speedtest failed: {e}")
        send_ntfy('vpn_speedtest_error', 'VPN Speedtest Failed', str(e), priority='high')
    finally:
        scan_active = False
        _flush_scan_state()

def scheduled_geolite_update():
    try:
        downloaded = _do_geolite_update()
        if downloaded:
            send_ntfy('geolite_updated', 'GeoLite2 Updated', f'Updated: {", ".join(downloaded)}')
    except Exception as e:
        logging.error(f'Scheduled GeoLite2 update failed: {e}')
        send_ntfy('geolite_update_error', 'GeoLite2 Update Failed', str(e), priority='high')

def scheduled_ovpn_update():
    config = load_config()
    url = config.get('ovpn', {}).get('download_url', '')
    if not url:
        logging.info("Scheduled OVPN update skipped: no download URL configured")
        return
    try:
        count = _download_ovpn_from_url(url)
        send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{count} UDP configs extracted')
    except Exception as e:
        logging.error(f'Scheduled OVPN update failed: {e}')
        send_ntfy('ovpn_update_error', 'OVPN Update Failed', str(e), priority='high')

def _run_servers_update_command(command):
    """Run a shell command and update servers.list from its stdout."""
    logging.info(f"Running servers update command...")
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command exited with code {result.returncode}: {result.stderr.strip()}")
    lines = [line.strip() for line in result.stdout.splitlines()]
    lines = list(dict.fromkeys(line for line in lines if line))
    if not lines:
        raise RuntimeError("Command produced no output")
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    logging.info(f"servers.list updated from command: {len(lines)} entries")
    return len(lines)

def scheduled_servers_update():
    config = load_config()
    command = config.get('schedule', {}).get('servers_update', {}).get('command', '')
    if not command:
        logging.info("Scheduled servers update skipped: no command configured")
        return
    try:
        count = _run_servers_update_command(command)
        send_ntfy('servers_updated', 'Servers List Updated', f'{count} servers loaded')
    except Exception as e:
        logging.error(f'Scheduled servers update failed: {e}')
        send_ntfy('servers_update_error', 'Servers List Update Failed', str(e), priority='high')

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
    if srv_cfg.get('enabled') and srv_cfg.get('command'):
        kw = _build_cron_kwargs(srv_cfg)
        scheduler.add_job(scheduled_servers_update, CronTrigger(**kw), id='servers_update', replace_existing=True)

    jobs = scheduler.get_jobs()
    logging.info(f"Scheduler updated: {len(jobs)} job(s) active")

# Initialize scheduler on startup
apply_schedules()
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
