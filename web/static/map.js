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

    const showAllCheckbox = document.getElementById('showAllServers');

    let serverData = [];
    let markers = [];
    let thresholds = { latency: { green: 50, yellow: 150 }, speed: { red: 50, yellow: 200 }, auto_color_latency: false, auto_color_speed: false, show_all_servers: false };

    let originMarker = null;
    let originData = null; // {lat, lon, city, country}
    const distanceOverlay = document.getElementById('distanceOverlay');

    // ---- Haversine distance (km) ----
    function haversineKm(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // ---- Percentile helper ----
    function percentile(sortedArr, p) {
        if (!sortedArr.length) return 0;
        const idx = (p / 100) * (sortedArr.length - 1);
        const lo = Math.floor(idx), hi = Math.ceil(idx);
        if (lo === hi) return sortedArr[lo];
        return sortedArr[lo] + (sortedArr[hi] - sortedArr[lo]) * (idx - lo);
    }

    // ---- Color helpers (threshold-based) ----
    function colorForLatency(val, bounds) {
        if (val == null) return '#94a3b8';
        if (val < bounds.green) return '#10b981';
        if (val < bounds.yellow) return '#eab308';
        return '#ef4444';
    }

    function colorForSpeed(val, bounds) {
        if (val == null) return '#94a3b8';
        if (val < bounds.red) return '#ef4444';
        if (val < bounds.yellow) return '#eab308';
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

        // Filter to servers that have a valid value for the selected metric
        const showAll = showAllCheckbox && showAllCheckbox.checked;
        const filtered = showAll ? serverData.filter(s => s.lat != null && s.lon != null) : serverData.filter(s => {
            const v = getValue(s, metric);
            return v != null && v > 0;
        });

        const vals = filtered.map(s => getValue(s, metric)).filter(v => v != null && v > 0).sort((a, b) => a - b);

        // Determine color boundaries
        const useAuto = isSpeed ? thresholds.auto_color_speed : thresholds.auto_color_latency;
        let bounds;
        if (useAuto && vals.length > 0) {
            if (isSpeed) {
                bounds = { red: percentile(vals, 33), yellow: percentile(vals, 66) };
            } else {
                bounds = { green: percentile(vals, 33), yellow: percentile(vals, 66) };
            }
        } else {
            bounds = isSpeed ? thresholds.speed : thresholds.latency;
        }

        // Update legend
        if (isSpeed) {
            const r = Math.round(bounds.red), y = Math.round(bounds.yellow);
            legendLow.textContent = '<' + r;
            legendHigh.textContent = '>' + y;
            legendBar.style.background = 'linear-gradient(to right, #ef4444, #eab308, #10b981)';
        } else {
            const g = Math.round(bounds.green), y = Math.round(bounds.yellow);
            legendLow.textContent = '<' + g;
            legendHigh.textContent = '>' + y;
            legendBar.style.background = 'linear-gradient(to right, #10b981, #eab308, #ef4444)';
        }

        // Determine best server per country for the current metric
        const bestByCountry = {};
        filtered.forEach(s => {
            const val = getValue(s, metric);
            if (val == null || val <= 0) return;
            const c = s.country;
            if (!bestByCountry[c] || (isSpeed ? val > bestByCountry[c] : val < bestByCountry[c])) {
                bestByCountry[c] = val;
            }
        });
        const bestSet = new Set();
        filtered.forEach(s => {
            const val = getValue(s, metric);
            if (val != null && val > 0 && val === bestByCountry[s.country] && !bestSet.has(s.country)) {
                bestSet.add(s.country);
                s._isBest = true;
            } else {
                s._isBest = false;
            }
        });

        // Build jitter offsets for overlapping coordinates
        const locCounts = {};
        const locIndex = {};
        filtered.forEach(s => {
            const key = s.lat.toFixed(4) + ',' + s.lon.toFixed(4);
            locCounts[key] = (locCounts[key] || 0) + 1;
            locIndex[key] = 0;
        });

        filtered.forEach(s => {
            const val = getValue(s, metric);
            const hasVal = val != null && val > 0;
            const color = hasVal ? (isSpeed ? colorForSpeed(val, bounds) : colorForLatency(val, bounds)) : '#94a3b8';

            // Spiral jitter for co-located markers
            const key = s.lat.toFixed(4) + ',' + s.lon.toFixed(4);
            let lat = s.lat, lon = s.lon;
            if (locCounts[key] > 1) {
                const i = locIndex[key]++;
                const angle = i * 2.4; // golden angle in radians
                const r = 0.012 * Math.sqrt(i + 1); // grow outward
                lat += r * Math.cos(angle);
                lon += r * Math.sin(angle);
            }

            const marker = L.circleMarker([lat, lon], {
                radius: s._isBest ? 9 : 7,
                fillColor: color,
                color: s._isBest ? '#ffffff' : 'rgba(255,255,255,0.3)',
                weight: s._isBest ? 2 : 1,
                fillOpacity: 0.85
            }).addTo(map);

            // Add pulse animation and tooltip to best-per-country markers
            if (s._isBest) {
                const el = marker.getElement();
                if (el) el.classList.add('best-marker');
                const bestLabel = isSpeed ? 'Fastest' : 'Lowest latency';
                marker.bindTooltip(`⭐ ${bestLabel} server in ${s.country}`, {
                    permanent: false, direction: 'top', className: 'best-tooltip'
                });
            }

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

        const withData = filtered.filter(s => { const v = getValue(s, metric); return v != null && v > 0; }).length;
        mapStats.textContent = showAll
            ? `${filtered.length} servers (${withData} with ${isSpeed ? 'speed' : 'latency'} data)`
            : `${withData} servers with ${isSpeed ? 'speed' : 'latency'} data`;

        updateDistanceOverlay();
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
                if (showAllCheckbox) showAllCheckbox.checked = !!thresholds.show_all_servers;
            }

            const resp = await fetch('/api/results/geo');
            serverData = await resp.json();
            if (!Array.isArray(serverData)) {
                mapStats.textContent = 'Error loading data';
                return;
            }
            renderMarkers();

            // Load and display measurement origin
            try {
                const originResp = await fetch('/api/origin');
                const origin = await originResp.json();
                if (origin.lat != null && origin.lon != null) {
                    if (originMarker) map.removeLayer(originMarker);
                    const icon = L.divIcon({
                        className: '',
                        html: '<div style="position:relative;width:22px;height:22px;"><div class="origin-ring"></div><div class="origin-icon">🏠</div></div>',
                        iconSize: [22, 22],
                        iconAnchor: [11, 11]
                    });
                    originMarker = L.marker([origin.lat, origin.lon], { icon, zIndexOffset: 1000 }).addTo(map);
                    originMarker.bindTooltip('Measurement origin (vantage point)', {
                        permanent: false, direction: 'top', className: 'best-tooltip'
                    });
                    originMarker.bindPopup(`
                        <div class="popup-domain">📡 Vantage Point</div>
                        <div class="popup-row"><span class="popup-label">IP</span> <span class="popup-val">${origin.ip || '—'}</span></div>
                        <div class="popup-row"><span class="popup-label">Location</span> <span class="popup-val">${origin.city}, ${origin.country}</span></div>
                        <div class="popup-row"><span class="popup-label">Detection</span> <span class="popup-val">${origin.source === 'manual' ? 'Manual' : 'Auto (IP)'}</span></div>
                        <div style="margin-top:6px;color:#94a3b8;font-size:0.75rem;">All measurements are relative to this location.</div>
                    `);
                    originData = { lat: origin.lat, lon: origin.lon, city: origin.city, country: origin.country };
                }
            } catch (e) { /* origin not available */ }

            // Fit bounds to markers with valid geo data
            const geoValid = serverData.filter(s => s.lat != null && s.lon != null);
            if (geoValid.length > 0) {
                const bounds = L.latLngBounds(geoValid.map(s => [s.lat, s.lon]));
                map.fitBounds(bounds, { padding: [30, 30], maxZoom: 6 });
            }
        } catch (e) {
            mapStats.textContent = 'Failed to load data';
        }
    }

    metricSelect.addEventListener('change', renderMarkers);
    if (showAllCheckbox) showAllCheckbox.addEventListener('change', renderMarkers);

    // ---- Distance overlay: show distance to single best visible server ----
    function updateDistanceOverlay() {
        if (!originData || !distanceOverlay) { if (distanceOverlay) distanceOverlay.classList.add('hidden'); return; }
        const mapBounds = map.getBounds();
        const metric = metricSelect.value;
        const isSpeed = metric !== 'latency';

        // Find best servers that are visible in the current viewport
        const visibleBest = serverData.filter(s =>
            s._isBest && s.lat != null && s.lon != null &&
            mapBounds.contains([s.lat, s.lon])
        );

        if (visibleBest.length === 1) {
            const s = visibleBest[0];
            const dist = haversineKm(originData.lat, originData.lon, s.lat, s.lon);
            const distStr = dist < 100 ? dist.toFixed(0) + ' km' : Math.round(dist) + ' km';
            distanceOverlay.textContent = `📏 ${distStr} (${originData.city} \u2192 ${s.city})`;
            distanceOverlay.classList.remove('hidden');
        } else {
            distanceOverlay.classList.add('hidden');
        }
    }
    map.on('moveend', updateDistanceOverlay);

    // Reset view button — fly to vantage point at country zoom
    document.getElementById('resetViewBtn').addEventListener('click', () => {
        if (originMarker) {
            map.flyTo(originMarker.getLatLng(), 6, { duration: 1.2 });
        }
    });

    loadData();
})();
