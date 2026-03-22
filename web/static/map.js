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

    // ---- Color helpers ----
    function lerp(a, b, t) { return a + (b - a) * t; }

    function colorForValue(val, min, max, invert) {
        if (val == null || max === min) return '#94a3b8';
        let t = (val - min) / (max - min);
        t = Math.max(0, Math.min(1, t));
        if (invert) t = 1 - t;
        // green (0) → yellow (0.5) → red (1)
        let r, g, b;
        if (t < 0.5) {
            const s = t * 2;
            r = lerp(16, 234, s);
            g = lerp(185, 179, s);
            b = lerp(129, 8, s);
        } else {
            const s = (t - 0.5) * 2;
            r = lerp(234, 239, s);
            g = lerp(179, 68, s);
            b = lerp(8, 68, s);
        }
        return `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;
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

        // Collect valid values for range
        const vals = serverData.map(s => getValue(s, metric)).filter(v => v != null && v > 0);
        if (vals.length === 0) {
            mapStats.textContent = 'No data for selected metric';
            return;
        }
        const min = Math.min(...vals);
        const max = Math.max(...vals);

        // Update legend
        if (isSpeed) {
            legendLow.textContent = 'Slow';
            legendHigh.textContent = 'Fast';
            legendBar.style.background = 'linear-gradient(to right, #ef4444, #eab308, #10b981)';
        } else {
            legendLow.textContent = 'Fast';
            legendHigh.textContent = 'Slow';
            legendBar.style.background = 'linear-gradient(to right, #10b981, #eab308, #ef4444)';
        }

        serverData.forEach(s => {
            const val = getValue(s, metric);
            const color = colorForValue(val, min, max, isSpeed);
            const radius = 7;

            const marker = L.circleMarker([s.lat, s.lon], {
                radius: radius,
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
