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

# Configuration
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
SERVERS_FILE = os.environ.get('SERVERS_FILE', 'servers.list')
GEOIP_CITY = os.environ.get('GEOIP_CITY', 'GeoLite2-City.mmdb')
GEOIP_COUNTRY = os.environ.get('GEOIP_COUNTRY', 'GeoLite2-Country.mmdb')

# Global state
scan_lock = threading.Lock()
scan_active = False
scan_progress = {"done": 0, "total": 0, "status": "idle", "message": ""}
last_error = None

def run_scan_in_background(pings, timeout, workers):
    global scan_active, scan_progress, last_error
    
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
            progress_container=scan_progress
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
    
    thread = threading.Thread(target=run_scan_in_background, args=(pings, timeout, workers))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scan/status')
def get_status():
    return jsonify({
        "active": scan_active,
        "progress": scan_progress,
        "error": last_error
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
