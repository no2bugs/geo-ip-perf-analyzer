import os
import sys
import threading
import time
import json
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

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

# Configuration
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
SERVERS_FILE = os.environ.get('SERVERS_FILE', 'servers.list')
GEOIP_CITY = os.environ.get('GEOIP_CITY', 'GeoLite2-City.mmdb')
GEOIP_COUNTRY = os.environ.get('GEOIP_COUNTRY', 'GeoLite2-Country.mmdb')
VPN_OVPN_DIR = os.environ.get('VPN_OVPN_DIR', 'ovpn')
VPN_USERNAME = os.environ.get('VPN_USERNAME', '')
VPN_PASSWORD = os.environ.get('VPN_PASSWORD', '')

# Global state
scan_lock = threading.Lock()
scan_active = False
scan_progress = {"done": 0, "total": 0, "status": "idle", "message": ""}
stop_event = threading.Event()
last_error = None

def run_scan_in_background(pings, timeout, workers, vpn_speedtest=False):
    global scan_active, scan_progress, last_error, stop_event
    
    stop_event.clear()
    scan_active = True
    scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Initializing..."}
    last_error = None
    
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
        
    except Exception as e:
        last_error = str(e)
        scan_progress['status'] = 'error'
        scan_progress['message'] = str(e)
        logging.error(f"Scan failed: {e}")
    finally:
        scan_active = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    global scan_active
    
    if scan_active:
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
        
    data = request.json or {}
    pings = int(data.get('pings', 1))
    timeout = int(data.get('timeout', 1000))
    workers = int(data.get('workers', 20))
    vpn_speedtest = data.get('vpn_speedtest', False)
    
    thread = threading.Thread(target=run_scan_in_background, args=(pings, timeout, workers, vpn_speedtest))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scan/status')
def get_status():
    return jsonify({
        "active": scan_active,
        "progress": scan_progress,
        "error": last_error,
        "stopping": stop_event.is_set()
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
    
    if scan_active:
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409
    
    data = request.json or {}
    selected_domains = data.get('domains', [])
    
    if not selected_domains:
        return jsonify({"status": "error", "message": "No domains selected"}), 400
    
    # Run VPN speedtest on selected domains
    def run_vpn_speedtest_background():
        global scan_active, scan_progress, last_error, stop_event
        print("DEBUG: Background thread run_vpn_speedtest_background started", file=sys.stderr, flush=True)
        stop_event.clear()
        scan_active = True
        scan_progress = {"done": 0, "total": len(selected_domains), "status": "running", "message": "Running VPN speedtest..."}
        last_error = None
        
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
            
            # Verify selected domains exist in results
            missing_domains = [d for d in selected_domains if d not in results]
            if missing_domains:
                print(f"DEBUG: Missing domains: {missing_domains}", file=sys.stderr, flush=True)
                logging.warning(f"Selected domains not found in results: {missing_domains}")
            
            # Filter to only domains that exist
            valid_domains = [d for d in selected_domains if d in results]
            print(f"DEBUG: Valid domains for speedtest: {valid_domains}", file=sys.stderr, flush=True)
            
            print("DEBUG: Initializing Scanner", file=sys.stderr, flush=True)
            scanner = Scanner(
                targets_file=SERVERS_FILE,
                city_db=GEOIP_CITY,
                country_db=GEOIP_COUNTRY,
                results_json=RESULTS_FILE,
                excl_countries_fle='exclude_countries.list'
            )
            print("DEBUG: Scanner initialized", file=sys.stderr, flush=True)
            
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
    
    print(f"DEBUG: Starting thread for {len(selected_domains)} domains", file=sys.stderr, flush=True)
    thread = threading.Thread(target=run_vpn_speedtest_background)
    thread.daemon = True
    thread.start()
    print("DEBUG: Thread started, returning started response", file=sys.stderr, flush=True)
    
    return jsonify({"status": "started"})

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    global stop_event, scan_active
    if not scan_active:
        return jsonify({"status": "error", "message": "No scan in progress"}), 400
    
    stop_event.set()
    logging.info("Stop signal sent to scanner...")
    return jsonify({"status": "stopping"})

@app.route('/api/logs')
def get_logs():
    return jsonify(log_buffer.get_logs())

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    log_buffer.clear()
    return jsonify({"status": "cleared"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
