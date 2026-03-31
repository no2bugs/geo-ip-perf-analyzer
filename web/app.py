"""
Flask application — route handlers and startup initialization.

Shared state and utility functions live in web.state.
Scheduler functions live in web.scheduler.
"""

import csv
import io
import os
import sys
import json
import time
import logging
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_from_directory
import requests as http_requests
import geoip2.database

import web.state as state
from web.state import Scanner
from web.scheduler import (
    scheduler, apply_schedules, _build_cron_kwargs,
    scheduled_vpn_speedtest, scheduled_latency_scan,
    scheduled_geolite_update, scheduled_ovpn_update, scheduled_servers_update,
)

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


# ============================================================
# Page routes
# ============================================================

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

@app.route('/statistics')
def statistics_page():
    return render_template('statistics.html')


# ============================================================
# Scan API
# ============================================================

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    if state._is_scan_active():
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409

    data = request.json or {}

    if not os.path.exists(state.SERVERS_FILE):
        return jsonify({
            "status": "error",
            "message": "Servers list file is missing. Please create 'servers.list' in the project root directory on your HOST machine."
        }), 400

    if os.path.getsize(state.SERVERS_FILE) == 0:
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

    thread = threading.Thread(target=state.run_scan_in_background, args=(pings, timeout, workers, vpn_speedtest, countries))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})

@app.route('/api/scan/status')
def get_status():
    active = state._is_scan_active()
    ss = state._read_scan_state()
    return jsonify({
        "active": active,
        "progress": ss.get("progress", state.scan_progress),
        "error": ss.get("error", state.last_error),
        "stopping": ss.get("stop_requested", state.stop_event.is_set()),
        "start_time": ss.get("start_time")
    })

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    if not state._is_scan_active():
        return jsonify({"status": "error", "message": "No scan in progress"}), 400

    state.stop_event.set()
    ss = state._read_scan_state()
    ss['stop_requested'] = True
    try:
        tmp = state.SCAN_STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(ss, f)
        os.replace(tmp, state.SCAN_STATE_FILE)
    except Exception:
        pass
    logging.info("Stop signal sent to scanner...")
    return jsonify({"status": "stopping"})


# ============================================================
# VPN Speedtest
# ============================================================

@app.route('/api/vpn-speedtest', methods=['POST'])
def vpn_speedtest():
    if state._is_scan_active():
        return jsonify({"status": "error", "message": "Scan already in progress"}), 409

    data = request.json or {}
    selected_domains = data.get('domains', [])

    def run_vpn_speedtest_background():
        state.stop_event.clear()
        state.scan_active = True
        state.scan_start_time = time.time()
        state.scan_progress = {"done": 0, "total": 0, "status": "running", "message": "Running VPN speedtest..."}
        state.last_error = None
        state._flush_scan_state()

        flusher = threading.Thread(target=state._state_flusher, daemon=True)
        flusher.start()

        try:
            if not os.path.exists(state.RESULTS_FILE):
                raise FileNotFoundError("Results file not found. Please run a scan first.")

            with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
                results = json.load(f)

            if not isinstance(results, dict):
                raise ValueError("Results file is in an invalid format.")

            domains_to_test = selected_domains if selected_domains else list(results.keys())
            missing_domains = [d for d in domains_to_test if d not in results]
            if missing_domains:
                logging.warning(f"Selected domains not found in results: {missing_domains}")
            valid_domains = [d for d in domains_to_test if d in results]

            state.scan_progress['total'] = len(valid_domains)
            state.scan_logger.info(f'VPN speedtest started: {len(valid_domains)} domains')

            scanner = Scanner(
                targets_file=state.SERVERS_FILE,
                city_db=state.GEOIP_CITY,
                country_db=state.GEOIP_COUNTRY,
                results_json=state.RESULTS_FILE,
                excl_countries_fle='exclude_countries.list'
            )

            vpn_start_time = time.time()
            if valid_domains:
                report = scanner._perform_vpn_speedtests(
                    results,
                    state.VPN_OVPN_DIR,
                    state.VPN_USERNAME,
                    state.VPN_PASSWORD,
                    state.scan_progress,
                    batch_size=999,
                    interactive=False,
                    selected_domains=valid_domains,
                    stop_event=state.stop_event,
                    results_file=state.RESULTS_FILE
                ) or {}
            else:
                raise ValueError("None of the selected domains were found in the scan results")

            duration = state._format_duration(time.time() - vpn_start_time)
            report_msg = f"{report.get('succeeded', 0)} succeeded, {report.get('vpn_failed', 0)} VPN failed, {report.get('speedtest_failed', 0)} speedtest failed"
            if state.stop_event.is_set():
                state.scan_progress['status'] = 'completed'
                state.scan_progress['message'] = f'VPN speedtest interrupted \u2014 {report_msg}'
                state.scan_logger.info(f'VPN speedtest interrupted: {state.scan_progress["done"]}/{len(valid_domains)} domains ({duration}) \u2014 {report_msg}')
            else:
                state.scan_progress['status'] = 'completed'
                state.scan_progress['message'] = f'VPN speedtest completed \u2014 {report_msg}'
                state.scan_logger.info(f'VPN speedtest completed: {len(valid_domains)} domains ({duration}) \u2014 {report_msg}')
                state.send_ntfy('vpn_speedtest_complete', 'VPN Speedtest Complete',
                                f'{len(valid_domains)} servers tested ({duration})\n{report_msg}')
        except Exception as e:
            state.last_error = str(e)
            state.scan_progress['status'] = 'error'
            state.scan_progress['message'] = str(e)
            logging.error(f"VPN speedtest failed: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
        finally:
            state.scan_active = False
            state._flush_scan_state()
            state._update_last_run('vpn_speedtest')

    thread = threading.Thread(target=run_vpn_speedtest_background)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})


# ============================================================
# Queue API
# ============================================================

@app.route('/api/queue/add', methods=['POST'])
def queue_add():
    """Add domains to the server-side speedtest queue."""
    data = request.json or {}
    domains = data.get('domains', [])
    job_type = data.get('type', 'untested')
    label = data.get('label', '')
    if not domains:
        return jsonify({"status": "error", "message": "No domains provided"}), 400
    pending = state._queue_add_job(domains, job_type, label)
    state._ensure_queue_processor()
    return jsonify({"status": "queued", "pending": pending})

@app.route('/api/queue/status')
def queue_status():
    """Return current queue info from shared file."""
    qs = state._read_queue_file()
    pending_jobs = qs.get("pending", [])
    active = qs.get("active")
    total_domains = sum(len(j.get("domains", [])) for j in pending_jobs)
    jobs = [{"domains": len(j.get("domains", [])), "type": j.get("type", ""), "label": j.get("label", "")} for j in pending_jobs]
    scan_state = state._read_scan_state()
    progress = scan_state.get("progress", {})
    scan_running = state._is_scan_active()
    return jsonify({
        "pending": len(jobs), "total_domains": total_domains, "jobs": jobs,
        "active": active, "scan_active": scan_running,
        "progress_done": progress.get("done", 0) if scan_running else 0,
        "progress_total": progress.get("total", 0) if scan_running else 0
    })

@app.route('/api/queue/clear', methods=['POST'])
def queue_clear():
    """Clear all pending queue items (does not stop a running scan)."""
    count = state._queue_clear_all()
    return jsonify({"status": "cleared", "removed": count})


# ============================================================
# Results / Export
# ============================================================

@app.route('/api/results')
def get_results():
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify({})
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/results/export/<fmt>')
def export_results(fmt):
    """Export all results as CSV or JSON file download."""
    if fmt not in ('csv', 'json'):
        return jsonify({'status': 'error', 'message': 'Format must be csv or json'}), 400
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify({'status': 'error', 'message': 'No results available'}), 404
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
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

    buf = io.StringIO()
    writer = csv.writer(buf)
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
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
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


# ============================================================
# Server History
# ============================================================

@app.route('/api/server/<domain>/history')
def get_server_history(domain):
    """Return the history array for a given domain."""
    if not all(c.isalnum() or c in '.-' for c in domain):
        return jsonify({'status': 'error', 'message': 'Invalid domain'}), 400
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify({'status': 'ok', 'history': []})
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        entry = data.get(domain)
        if not entry or not isinstance(entry, dict):
            return jsonify({'status': 'ok', 'history': []})
        return jsonify({'status': 'ok', 'history': entry.get('history', [])})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# Geo Results (map view)
# ============================================================

@app.route('/api/results/geo')
def get_results_geo():
    """Return results with lat/lon resolved from GeoIP City database."""
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    if not os.path.exists(state.GEOIP_CITY):
        return jsonify({'error': 'GeoIP City database not found'}), 500
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        reader = geoip2.database.Reader(state.GEOIP_CITY)
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
                    'tx_speed_mbps': entry.get('tx_speed_mbps'),
                    'speedtest_timestamp': entry.get('speedtest_timestamp'),
                    'speedtest_failed_timestamp': entry.get('speedtest_failed_timestamp')
                })
        finally:
            reader.close()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# Origin (vantage point)
# ============================================================

@app.route('/api/origin')
def get_origin():
    """Return the measurement origin (vantage point) location."""
    config = state.load_config()
    mt = config.get('theme', {}).get('map_thresholds', {})
    origin_mode = mt.get('origin_mode', 'auto')

    if origin_mode == 'manual':
        addr = mt.get('origin_address', {})
        cached = state._origin_cache.get('manual')
        if cached and cached.get('_addr') == addr:
            resp_data = {k: v for k, v in cached.items() if k != '_addr'}
            return jsonify(resp_data)
        result = state._geocode_address(
            addr.get('country', ''),
            addr.get('city', ''),
            addr.get('zipcode', '')
        )
        if result:
            result['_addr'] = addr
            state._origin_cache['manual'] = result
            resp_data = {k: v for k, v in result.items() if k != '_addr'}
            return jsonify(resp_data)

    if state._origin_cache['auto']:
        return jsonify(state._origin_cache['auto'])

    return jsonify({'error': 'Could not determine origin location'}), 500


# ============================================================
# Theme / Wallpaper
# ============================================================

@app.route('/api/theme')
def get_theme():
    config = state.load_config()
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

@app.route('/api/theme', methods=['POST'])
def post_theme():
    data = request.json or {}
    palette = data.get('palette', 'default')
    wallpaper = data.get('wallpaper', 'none')
    wallpaper_mode = data.get('wallpaper_mode', 'tile')
    map_thresholds = data.get('map_thresholds')
    if palette not in state.VALID_PALETTES:
        palette = 'default'
    if wallpaper not in state.VALID_WALLPAPERS:
        wallpaper = 'none'
    if wallpaper_mode not in state.VALID_WALLPAPER_MODES:
        wallpaper_mode = 'tile'
    with state._config_lock:
        config = state.load_config()
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
        state.save_config(config)
    state._origin_cache['manual'] = None
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
    if ext not in state.ALLOWED_IMAGE_EXTENSIONS:
        allowed = ', '.join(sorted(state.ALLOWED_IMAGE_EXTENSIONS))
        return jsonify({'status': 'error', 'message': f'Allowed types: {allowed}'}), 400
    data = uploaded.read()
    if len(data) > state.MAX_WALLPAPER_SIZE:
        return jsonify({'status': 'error', 'message': 'File exceeds 5 MB limit'}), 400
    wp_dir = Path(state.WALLPAPER_DIR)
    wp_dir.mkdir(parents=True, exist_ok=True)
    for old in wp_dir.iterdir():
        if old.stem == 'custom':
            old.unlink()
    target = wp_dir / f'custom{ext}'
    target.write_bytes(data)
    with state._config_lock:
        config = state.load_config()
        theme = config.get('theme', {})
        theme['wallpaper'] = 'custom'
        config['theme'] = theme
        state.save_config(config)
    logging.info(f'Custom wallpaper uploaded: {uploaded.filename} ({len(data)} bytes)')
    return jsonify({'status': 'ok', 'url': '/api/wallpaper/custom'})


@app.route('/api/wallpaper/custom')
def serve_custom_wallpaper():
    """Serve the uploaded custom wallpaper image."""
    wp_dir = Path(state.WALLPAPER_DIR)
    for ext in state.ALLOWED_IMAGE_EXTENSIONS:
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
    wp_dir = Path(state.WALLPAPER_DIR)
    deleted = False
    for ext in state.ALLOWED_IMAGE_EXTENSIONS:
        candidate = wp_dir / f'custom{ext}'
        if candidate.exists():
            candidate.unlink()
            deleted = True
    with state._config_lock:
        config = state.load_config()
        theme = config.get('theme', {})
        if theme.get('wallpaper') == 'custom':
            theme['wallpaper'] = 'none'
            config['theme'] = theme
            state.save_config(config)
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
    if ext not in state.ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({'status': 'error', 'message': 'Allowed types: .mp4, .webm'}), 400
    data = uploaded.read()
    if len(data) > state.MAX_VIDEO_WALLPAPER_SIZE:
        return jsonify({'status': 'error', 'message': 'File exceeds 50 MB limit'}), 400
    wp_dir = Path(state.WALLPAPER_DIR)
    wp_dir.mkdir(parents=True, exist_ok=True)
    for old in wp_dir.iterdir():
        if old.stem == 'video_custom':
            old.unlink()
    target = wp_dir / f'video_custom{ext}'
    target.write_bytes(data)
    with state._config_lock:
        config = state.load_config()
        theme = config.get('theme', {})
        theme['wallpaper'] = 'video_custom'
        config['theme'] = theme
        state.save_config(config)
    logging.info(f'Custom video wallpaper uploaded: {uploaded.filename} ({len(data)} bytes)')
    return jsonify({'status': 'ok'})


@app.route('/api/wallpaper/video')
def serve_video_wallpaper():
    """Serve the uploaded custom video wallpaper."""
    wp_dir = Path(state.WALLPAPER_DIR)
    for ext in state.ALLOWED_VIDEO_EXTENSIONS:
        candidate = wp_dir / f'video_custom{ext}'
        if candidate.exists():
            mime = {'.mp4': 'video/mp4', '.webm': 'video/webm'}
            return send_from_directory(str(wp_dir), candidate.name,
                                      mimetype=mime.get(ext, 'video/mp4'))
    return jsonify({'status': 'error', 'message': 'No custom video found'}), 404


@app.route('/api/wallpaper/video', methods=['DELETE'])
def delete_video_wallpaper():
    """Delete the custom video wallpaper."""
    wp_dir = Path(state.WALLPAPER_DIR)
    deleted = False
    for ext in state.ALLOWED_VIDEO_EXTENSIONS:
        candidate = wp_dir / f'video_custom{ext}'
        if candidate.exists():
            candidate.unlink()
            deleted = True
    with state._config_lock:
        config = state.load_config()
        theme = config.get('theme', {})
        if theme.get('wallpaper') == 'video_custom':
            theme['wallpaper'] = 'none'
            config['theme'] = theme
            state.save_config(config)
    return jsonify({'status': 'ok', 'deleted': deleted})


# ============================================================
# Config API
# ============================================================

@app.route('/api/config')
def get_config():
    return jsonify(state.load_config())

@app.route('/api/config', methods=['POST'])
def post_config():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    ovpn_sched = data.get('schedule', {}).get('ovpn_update', {})
    if ovpn_sched.get('enabled') and not ovpn_sched.get('download_url', '').strip():
        return jsonify({'status': 'error', 'message': 'OVPN Config Update requires a Download URL. Disable the schedule or provide a URL.'}), 400
    data.pop('ovpn', None)
    with state._config_lock:
        existing = state.load_config()
        for key in ['vpn_speedtest', 'geolite_update', 'ovpn_update', 'servers_update']:
            lr = existing.get('schedule', {}).get(key, {}).get('last_run')
            if lr:
                data.setdefault('schedule', {}).setdefault(key, {}).setdefault('last_run', lr)
        theme = existing.get('theme')
        if theme:
            data['theme'] = theme
        state.save_config(data)
    apply_schedules()
    return jsonify({'status': 'ok'})


# ============================================================
# VPN Credentials
# ============================================================

@app.route('/api/credentials')
def get_credentials():
    env = state._read_env_file()
    username = env.get('VPN_USERNAME', '')
    password = env.get('VPN_PASSWORD', '')
    return jsonify({
        'vpn_password_set': bool(password),
        'vpn_username_masked': (username[:3] + '***') if len(username) > 3 else ('***' if username else '')
    })

@app.route('/api/credentials', methods=['POST'])
def post_credentials():
    data = request.json or {}
    username = data.get('vpn_username')
    password = data.get('vpn_password')
    if username is None and password is None:
        return jsonify({'status': 'error', 'message': 'No credentials provided'}), 400
    env = state._read_env_file()
    if username is not None:
        env['VPN_USERNAME'] = username
        state.VPN_USERNAME = username
    if password is not None:
        env['VPN_PASSWORD'] = password
        state.VPN_PASSWORD = password
    state._write_env_file(env)
    return jsonify({'status': 'ok'})

@app.route('/api/config/test-notification', methods=['POST'])
def test_notification():
    config = state.load_config()
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


# ============================================================
# Schedule API
# ============================================================

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
    """Return next scheduled run times for all active jobs.

    Computed from config on disk so every gunicorn worker returns
    consistent results (only one worker owns the APScheduler lock).
    """
    from apscheduler.triggers.cron import CronTrigger
    from datetime import datetime, timezone

    config = state.load_config()
    schedule_cfg = config.get('schedule', {})
    job_keys = {
        'vpn_speedtest': 'vpn_speedtest',
        'latency_scan': 'latency_scan',
        'geolite_update': 'geolite',
        'ovpn_update': 'ovpn',
        'servers_update': 'servers_update',
    }
    result = {}
    now = datetime.now(timezone.utc)
    for cfg_key, job_id in job_keys.items():
        cfg = schedule_cfg.get(cfg_key, {})
        if not cfg.get('enabled'):
            continue
        try:
            trigger = CronTrigger(**_build_cron_kwargs(cfg))
            nrt = trigger.get_next_fire_time(None, now)
            if nrt:
                result[job_id] = nrt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            pass
    return jsonify(result)


# ============================================================
# Statistics
# ============================================================

@app.route('/api/statistics')
def get_statistics():
    """Return per-country statistics."""
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify({'countries': [], 'top5': []})
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return jsonify({'countries': [], 'top5': []})

    countries = {}
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
        fts = entry.get('speedtest_failed_timestamp')
        if lat is not None and lat > 0:
            if c['lowest_latency'] is None or lat < c['lowest_latency']:
                c['lowest_latency'] = lat
                c['lowest_latency_server'] = domain
        has_recent_failure = fts and (not ts or fts > ts)
        has_speed = rx is not None and rx > 0
        if has_recent_failure:
            c['failed'] += 1
            c['failed_domains'].append(domain)
        elif has_speed:
            c['succeeded'] += 1
            if c['highest_download'] is None or rx > c['highest_download']:
                c['highest_download'] = rx
                c['highest_download_server'] = domain
        else:
            c['untested'] += 1
            c['untested_domains'].append(domain)
        if tx is not None and tx > 0:
            if c['highest_upload'] is None or tx > c['highest_upload']:
                c['highest_upload'] = tx
                c['highest_upload_server'] = domain

    stats_list = sorted(countries.values(), key=lambda x: x['country'])
    for s in stats_list:
        del s['untested_domains']
        del s['failed_domains']

    top_n = max(1, min(100, request.args.get('top', 5, type=int)))
    best_per_country = []
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if state._is_failed_server(entry):
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
    best_map = {}
    for s in best_per_country:
        c = s['country']
        if c not in best_map or s['rx_speed_mbps'] > best_map[c]['rx_speed_mbps']:
            best_map[c] = s
    top_sorted = sorted(best_map.values(), key=lambda x: x['rx_speed_mbps'], reverse=True)
    top_list = top_sorted[:top_n] if top_n < len(top_sorted) else top_sorted

    return jsonify({'countries': stats_list, 'top': top_list, 'total_countries': len(best_map)})


@app.route('/api/statistics/domains')
def get_statistics_domains():
    """Return untested/failed domain lists per country."""
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify({'untested': [], 'failed': []})
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
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
        fts = entry.get('speedtest_failed_timestamp')
        has_speed = rx is not None and rx > 0
        has_recent_failure = fts and (not ts or fts > ts)
        if has_recent_failure:
            failed.append(domain)
        elif has_speed:
            continue
        else:
            untested.append(domain)
    return jsonify({'untested': untested, 'failed': failed})


@app.route('/api/top-servers')
def get_top_servers():
    """Return top N servers (best download per country)."""
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    try:
        with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return jsonify([])
    n = max(1, min(100, request.args.get('n', 5, type=int)))
    include_failed = request.args.get('include_failed', 'false').lower() in ('true', '1', 'yes')
    best_map = {}
    for domain, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if not include_failed and state._is_failed_server(entry):
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


# ============================================================
# Prune stale results
# ============================================================

@app.route('/api/prune-stale', methods=['POST'])
def prune_stale():
    try:
        pruned, remaining = state._prune_stale_results()
        if pruned == 0:
            return jsonify({'status': 'ok', 'message': 'No stale servers found'})
        return jsonify({'status': 'ok', 'message': f'Removed {pruned} stale servers ({remaining} remaining)'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# ============================================================
# GeoLite / OVPN / Servers file management
# ============================================================

@app.route('/api/geolite/status')
def geolite_status():
    """Check local GeoLite2 file dates and latest available release."""
    city_path = Path(state.GEOIP_CITY)
    country_path = Path(state.GEOIP_COUNTRY)

    local_city_mtime = None
    local_country_mtime = None
    if city_path.exists():
        local_city_mtime = datetime.fromtimestamp(city_path.stat().st_mtime, tz=timezone.utc).isoformat()
    if country_path.exists():
        local_country_mtime = datetime.fromtimestamp(country_path.stat().st_mtime, tz=timezone.utc).isoformat()

    latest_release_date = None
    latest_tag = None
    update_available = False
    try:
        resp = http_requests.get(state.GEOLITE_RELEASE_URL, timeout=10)
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
        downloaded = state._do_geolite_update()
        if not downloaded:
            return jsonify({'status': 'error', 'message': 'No matching assets found in release'}), 404
        state.send_ntfy('geolite_updated', 'GeoLite2 Updated', f'Updated: {", ".join(downloaded)}')
        return jsonify({'status': 'ok', 'updated': downloaded})
    except Exception as e:
        logging.error(f'GeoLite2 update failed: {e}')
        state.send_ntfy('geolite_update_error', 'GeoLite2 Update Failed', str(e), priority='high')
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/servers', methods=['GET'])
def get_servers():
    """Return the current servers.list content."""
    if not os.path.exists(state.SERVERS_FILE):
        return jsonify({'servers': ''})
    with open(state.SERVERS_FILE, 'r', encoding='utf-8') as f:
        return jsonify({'servers': f.read()})

@app.route('/api/servers', methods=['POST'])
def save_servers():
    """Save servers.list content."""
    data = request.json or {}
    content = data.get('servers', '')
    lines = [line.strip() for line in content.splitlines()]
    lines = list(dict.fromkeys(line for line in lines if line))
    tmp = state.SERVERS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))
    os.replace(tmp, state.SERVERS_FILE)
    logging.info(f'servers.list updated: {len(lines)} entries')
    return jsonify({'status': 'ok', 'count': len(lines)})

@app.route('/api/ovpn/status')
def ovpn_status():
    """Return ovpn folder stats: file count and newest file mtime."""
    ovpn_path = Path(state.VPN_OVPN_DIR)
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

            ovpn_path = Path(state.VPN_OVPN_DIR)
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
        state.send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{extracted} UDP configs extracted')
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
        config = state.load_config()
        url = config.get('schedule', {}).get('ovpn_update', {}).get('download_url', '')
    if not url:
        return jsonify({'status': 'error', 'message': 'No download URL configured'}), 400
    try:
        count = state._download_ovpn_from_url(url)
        state.send_ntfy('ovpn_updated', 'OVPN Configs Updated', f'{count} UDP configs extracted')
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
    if not all(c.isalnum() or c in '.-' for c in domain):
        return jsonify({'status': 'error', 'message': 'Invalid domain'}), 400
    ovpn_path = Path(state.VPN_OVPN_DIR)
    for pattern in [f'{domain}.udp.ovpn', f'{domain}.tcp.ovpn', f'{domain}.ovpn']:
        candidate = ovpn_path / pattern
        if candidate.exists():
            return jsonify({'status': 'ok', 'filename': candidate.name,
                            'content': candidate.read_text(encoding='utf-8', errors='replace')})
    return jsonify({'status': 'error', 'message': f'No OVPN config found for {domain}'}), 404


# ============================================================
# Top Results API (programmatic)
# ============================================================

@app.route('/api/v1/top/latency')
def top_latency():
    n = request.args.get('n', 5, type=int)
    countries = state._parse_countries(request.args)
    include_failed = request.args.get('include_failed', 'false').lower() in ('true', '1', 'yes')
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict):
            if not include_failed and state._is_failed_server(entry):
                continue
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
    countries = state._parse_countries(request.args)
    include_failed = request.args.get('include_failed', 'false').lower() in ('true', '1', 'yes')
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('rx_speed_mbps') is not None:
            if not include_failed and state._is_failed_server(entry):
                continue
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
    countries = state._parse_countries(request.args)
    include_failed = request.args.get('include_failed', 'false').lower() in ('true', '1', 'yes')
    if not os.path.exists(state.RESULTS_FILE):
        return jsonify([])
    with open(state.RESULTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for domain, entry in data.items():
        if isinstance(entry, dict) and entry.get('tx_speed_mbps') is not None:
            if not include_failed and state._is_failed_server(entry):
                continue
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


# ============================================================
# Logs API
# ============================================================

@app.route('/api/logs')
def get_logs():
    """Return last 200 log entries from the shared general.log file."""
    fpath = os.path.join(state.LOG_DIR, 'general.log')
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
        m = state._LOG_LINE_RE.match(line)
        if m:
            entries.append({"timestamp": m.group(2), "level": m.group(3), "message": m.group(4)})
        elif entries:
            entries[-1]["message"] += "\n" + line
    return jsonify(entries)

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Truncate the general.log file."""
    fpath = os.path.join(state.LOG_DIR, 'general.log')
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            pass
    except Exception:
        pass
    return jsonify({"status": "cleared"})

@app.route('/api/logs/files')
def list_log_files():
    """List available log files with sizes."""
    files = []
    for key, fname in state.LOG_FILE_MAP.items():
        fpath = os.path.join(state.LOG_DIR, fname)
        if os.path.exists(fpath):
            files.append({'name': key, 'file': fname, 'size': os.path.getsize(fpath)})
        else:
            files.append({'name': key, 'file': fname, 'size': 0})
    return jsonify(files)

@app.route('/api/logs/file/<name>')
def get_log_file(name):
    """Return tail of a log file. ?lines=N (default 200)."""
    fname = state.LOG_FILE_MAP.get(name)
    if not fname:
        return jsonify({'error': 'Unknown log file'}), 404
    fpath = os.path.join(state.LOG_DIR, fname)
    if not os.path.exists(fpath):
        return jsonify({'lines': [], 'total': 0})
    lines_n = request.args.get('lines', 500, type=int)
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    tail = all_lines[-lines_n:] if len(all_lines) > lines_n else all_lines
    return jsonify({'lines': [l.rstrip() for l in tail], 'total': len(all_lines)})


# ============================================================
# Startup
# ============================================================

# Clear stale scan state from previous container crash/restart
state._clear_stale_state()

# Detect vantage point once at startup (before VPN tunnels)
state._init_origin()

# Initialize scheduler on startup — use file lock so only one gunicorn worker runs it
import fcntl as _fcntl
_sched_lock_file = open('/tmp/.geo-ip-scheduler.lock', 'w')
try:
    _fcntl.flock(_sched_lock_file, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    apply_schedules()
    scheduler.start()
    logging.info('Scheduler started (this worker owns the lock)')
except OSError:
    logging.info('Scheduler skipped (another worker owns the lock)')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
