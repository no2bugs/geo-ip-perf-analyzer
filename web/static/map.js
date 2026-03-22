/**
 * map.js — Leaflet map with server markers color-coded by latency/speed.
 */
(function () {
    'use strict';

    const map = L.map('map', { zoomControl: true }).setView([48, 10], 4);

    // Dark tile layer (CartoDB Dark Matter — free, no API key)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    const metricSelect = document.getElementById('metricSelect');
    const legendLow = document.getElementById('legendLow');
    const legendHigh = document.getElementById('legendHigh');
    const legendBar = document.getElementById('legendBar');
    const mapStats = document.getElementById('mapStats');

    let serverData = [];
    let markers = [];
    let thresholds = { latency: { green: 50, yellow: 150 }, speed: { red: 50, yellow: 200 } };

    // ---- Color helpers (threshold-based) ----
    function colorForLatency(val) {
        if (val == null) return '#94a3b8';
        const g = thresholds.latency.green, y = thresholds.latency.yellow;
        if (val < g) return '#10b981';
        if (val < y) return '#eab308';
        return '#ef4444';
    }

    function colorForSpeed(val) {
        if (val == null) return '#94a3b8';
        const r = thresholds.speed.red, y = thresholds.speed.yellow;
        if (val < r) return '#ef4444';
        if (val < y) return '#eab308';
        return '#10b981';
    }

    function getValue(item, metric) {
        if (metric === 'latency') return item.latency_ms;
        if (metric === 'rx_speed') return item.rx_speed_mbps;
        if (metric === 'tx_speed') return item.tx_speed_mbps;
        return null;
    }

    // ---- Render markers ----
    function renderMarkers() {
        markers.forEach(m => map.removeLayer(m));
        markers = [];

        const metric = metricSelect.value;
        const isSpeed = metric !== 'latency';

        const vals = serverData.map(s => getValue(s, metric)).filter(v => v != null && v > 0);

        // Update legend
        if (isSpeed) {
            const r = thresholds.speed.red, y = thresholds.speed.yellow;
            legendLow.textContent = '<' + r;
            legendHigh.textContent = '>' + y;
            legendBar.style.background = 'linear-gradient(to right, #ef4444, #eab308, #10b981)';
        } else {
            const g = thresholds.latency.green, y = thresholds.latency.yellow;
            legendLow.textContent = '<' + g;
            legendHigh.textContent = '>' + y;
            legendBar.style.background = 'linear-gradient(to right, #10b981, #eab308, #ef4444)';
        }

        serverData.forEach(s => {
            const val = getValue(s, metric);
            const color = isSpeed ? colorForSpeed(val) : colorForLatency(val);

            const marker = L.circleMarker([s.lat, s.lon], {
                radius: 7,
                fillColor: color,
                color: 'rgba(255,255,255,0.3)',
                weight: 1,
                fillOpacity: 0.85
            }).addTo(map);

            const latStr = s.latency_ms != null ? s.latency_ms.toFixed(2) + ' ms' : 'N/A';
            const dlStr = s.rx_speed_mbps != null ? s.rx_speed_mbps.toFixed(1) + ' Mbps' : 'N/A';
            const ulStr = s.tx_speed_mbps != null ? s.tx_speed_mbps.toFixed(1) + ' Mbps' : 'N/A';

            marker.bindPopup(`
                <div class="popup-domain">${s.domain}</div>
                <div class="popup-row"><span class="popup-label">IP</span> <span class="popup-val">${s.ip}</span></div>
                <div class="popup-row"><span class="popup-label">Location</span> <span class="popup-val">${s.city}, ${s.country}</span></div>
                <div class="popup-row"><span class="popup-label">Latency</span> <span class="popup-val">${latStr}</span></div>
                <div class="popup-row"><span class="popup-label">Download</span> <span class="popup-val">${dlStr}</span></div>
                <div class="popup-row"><span class="popup-label">Upload</span> <span class="popup-val">${ulStr}</span></div>
            `);

            markers.push(marker);
        });

        mapStats.textContent = `${serverData.length} servers • ${vals.length} with ${isSpeed ? 'speed' : 'latency'} data`;
    }

    // ---- Load data ----
    async function loadData() {
        mapStats.textContent = 'Loading...';
        try {
            // Load thresholds from theme API
            const themeResp = await fetch('/api/theme');
            const themeData = await themeResp.json();
            if (themeData.map_thresholds) {
                thresholds = themeData.map_thresholds;
            }

            const resp = await fetch('/api/results/geo');
            serverData = await resp.json();
            if (!Array.isArray(serverData)) {
                mapStats.textContent = 'Error loading data';
                return;
            }
            renderMarkers();

            // Fit bounds to markers
            if (serverData.length > 0) {
                const bounds = L.latLngBounds(serverData.map(s => [s.lat, s.lon]));
                map.fitBounds(bounds, { padding: [30, 30], maxZoom: 6 });
            }
        } catch (e) {
            mapStats.textContent = 'Failed to load data';
        }
    }

    metricSelect.addEventListener('change', renderMarkers);
    loadData();
})();
