document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');

    const searchInput = document.getElementById('search');
    const resultsBody = document.getElementById('resultsBody');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressDetail = document.getElementById('progressDetail');
    const progressSection = document.getElementById('progressSection');
    const statusText = document.getElementById('statusText');
    const globalStatus = document.getElementById('globalStatus');
    const waveBars = document.getElementById('waveBars');
    const statusIndicator = document.getElementById('statusIndicator');
    const controlsPanel = document.querySelector('.controls-section');

    // ── Matrix rain setup ──
    const matrixCanvases = [
        document.getElementById('matrixLog'),
        document.getElementById('matrixControls')
    ].filter(Boolean);
    const matrixCtxs = matrixCanvases.map(c => c.getContext('2d'));
    const matrixDrops = [];          // per-canvas drops array
    const matrixChars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF<>{}|/\\=+-*&^%$#@!';
    let matrixRAF = null;
    const MATRIX_FONT_SIZE = 13;
    const MATRIX_INTERVAL = 70;   // ms between frames (~14fps)
    let matrixLastFrame = 0;

    function initMatrixDrops() {
        matrixDrops.length = 0;
        matrixCanvases.forEach((c, i) => {
            c.width  = c.parentElement.offsetWidth;
            c.height = c.parentElement.offsetHeight;
            const cols = Math.floor(c.width / MATRIX_FONT_SIZE);
            const arr  = new Array(cols);
            for (let j = 0; j < cols; j++) arr[j] = Math.random() * -40 | 0;
            matrixDrops[i] = arr;
        });
    }

    function drawMatrix(now) {
        matrixRAF = requestAnimationFrame(drawMatrix);
        if (now - matrixLastFrame < MATRIX_INTERVAL) return;
        matrixLastFrame = now;
        matrixCanvases.forEach((c, i) => {
            const ctx = matrixCtxs[i];
            const drops = matrixDrops[i];
            if (!ctx || !drops) return;
            ctx.fillStyle = 'rgba(15, 23, 42, 0.12)';
            ctx.fillRect(0, 0, c.width, c.height);
            ctx.font = MATRIX_FONT_SIZE + 'px monospace';
            for (let x = 0; x < drops.length; x++) {
                const ch = matrixChars[Math.random() * matrixChars.length | 0];
                const bright = Math.random();
                ctx.fillStyle = bright > 0.9
                    ? 'rgba(180,255,180,0.9)'
                    : 'rgba(0,' + (140 + (bright * 115) | 0) + ',65,' + (0.35 + bright * 0.45).toFixed(2) + ')';
                ctx.fillText(ch, x * MATRIX_FONT_SIZE, drops[x] * MATRIX_FONT_SIZE);
                if (drops[x] * MATRIX_FONT_SIZE > c.height && Math.random() > 0.975) drops[x] = 0;
                drops[x]++;
            }
        });
    }

    function startMatrix() {
        if (matrixRAF) return;
        initMatrixDrops();
        matrixLastFrame = 0;
        matrixCanvases.forEach(c => c.classList.add('active'));
        matrixRAF = requestAnimationFrame(drawMatrix);
    }
    function stopMatrix() {
        if (matrixRAF) { cancelAnimationFrame(matrixRAF); matrixRAF = null; }
        matrixCanvases.forEach(c => {
            c.classList.remove('active');
            const ctx = c.getContext('2d');
            ctx.clearRect(0, 0, c.width, c.height);
        });
    }
    // Resize canvases when window changes
    window.addEventListener('resize', () => { if (matrixRAF) initMatrixDrops(); });

    let isScanning = false;
    let pollInterval = null;
    let scanStartTime = null; // epoch seconds from server
    let allResults = [];
    let filteredResults = []; // Track filtered results separately for pagination
    let selectedDomains = new Set();
    let currentPage = 1;
    const rowsPerPage = 50;
    const paginationContainers = [
        document.getElementById('pagination'),
        document.getElementById('paginationTop')
    ].filter(Boolean);

    // Country filter state
    let selectedCountries = new Set();
    const countryFilterBtn = document.getElementById('countryFilterBtn');
    const countryFilterDropdown = document.getElementById('countryFilterDropdown');
    const countryFilterList = document.getElementById('countryFilterList');
    const countryFilterSearch = document.getElementById('countryFilterSearch');
    const countryFilterClear = document.getElementById('countryFilterClear');

    // Initial Load
    fetchStatus();
    fetchResults();

    startBtn.addEventListener('click', startScan);
    stopBtn.addEventListener('click', stopScan);

    // Debounce search input
    let searchTimeout = null;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(filterResults, 200);
    });

    // VPN Speedtest controls
    const selectAllBtn = document.getElementById('selectAllBtn');
    const vpnSpeedtestBtn = document.getElementById('vpnSpeedtestBtn');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');

    selectAllBtn.addEventListener('click', (e) => toggleSelectAll(e));
    vpnSpeedtestBtn.addEventListener('click', runVpnSpeedtest);
    selectAllCheckbox.addEventListener('change', (e) => toggleSelectAll(e));

    // Sorting
    let currentSortField = null;
    let currentSortOrder = null;

    function updateSortIndicators() {
        document.querySelectorAll('th[data-sort]').forEach(th => {
            const icon = th.querySelector('.sort-icon');
            if (th.dataset.sort === currentSortField) {
                th.classList.add('sort-active');
                if (icon) icon.textContent = currentSortOrder === 'asc' ? ' ▲' : ' ▼';
            } else {
                th.classList.remove('sort-active');
                if (icon) icon.textContent = '';
            }
        });
    }

    document.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            const order = (currentSortField === field && currentSortOrder === 'asc') ? 'desc' : 'asc';
            sortResults(field, order);
        });
    });

    async function startScan() {
        const pings = document.getElementById('pings').value;
        const timeout = document.getElementById('timeout').value;
        const workers = document.getElementById('workers').value;
        const vpnSpeedtestEl = document.getElementById('vpnSpeedtest');
        const vpnSpeedtest = vpnSpeedtestEl ? vpnSpeedtestEl.checked : false;

        try {
            startBtn.disabled = true;
            const response = await fetch('/api/scan/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pings, timeout, workers, vpn_speedtest: vpnSpeedtest })
            });

            if (response.ok) {
                showToast('Scan started successfully');
                startPolling();
            } else {
                const err = await response.json();
                showToast('Error: ' + err.message, true);
                startBtn.disabled = false;
            }
        } catch (e) {
            showToast('Network error', true);
            startBtn.disabled = false;
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/api/scan/status');
            const data = await response.json();

            updateStatusUI(data);

            if (data.active) {
                if (!pollInterval) startPolling();
            } else if (pollInterval) {
                stopPolling();
                fetchResults(); // Refresh results when done
            }
        } catch (e) {
            console.error("Status check failed", e);
        }
    }

    function _fmtDuration(sec) {
        sec = Math.round(sec);
        if (sec < 60) return sec + 's';
        const m = Math.floor(sec / 60), s = sec % 60;
        if (m < 60) return m + 'm ' + s + 's';
        const h = Math.floor(m / 60);
        return h + 'h ' + (m % 60) + 'm';
    }

    function updateStatusUI(data) {
        isScanning = data.active;
        startBtn.disabled = isScanning;

        globalStatus.className = 'dot ' + (isScanning ? 'running' : 'completed');

        // Wave bars + indicator glow
        if (waveBars) waveBars.classList.toggle('visible', isScanning);
        if (statusIndicator) statusIndicator.classList.toggle('active', isScanning);

        // Animated border on controls panel
        if (controlsPanel) controlsPanel.classList.toggle('scanning', isScanning);

        // Matrix rain background
        if (isScanning) startMatrix(); else stopMatrix();

        // Track scan start time from server
        if (isScanning && data.start_time) {
            scanStartTime = data.start_time;
        } else if (!isScanning) {
            scanStartTime = null;
        }

        // Dynamic status text with live percentage
        if (isScanning && data.progress && data.progress.total > 0) {
            const pct = Math.round((data.progress.done / data.progress.total) * 100);
            statusText.textContent = 'Scanning ' + pct + '%';
        } else if (isScanning) {
            statusText.textContent = 'Scanning\u2026';
        } else {
            statusText.textContent = 'Ready';
        }

        // Show elapsed / ETA inline below progress bar
        const progressEta = document.getElementById('progressEta');
        if (isScanning && scanStartTime && data.progress) {
            const { done, total } = data.progress;
            const elapsed = Date.now() / 1000 - scanStartTime;
            let etaText = 'Elapsed: ' + _fmtDuration(elapsed);
            if (done > 0 && total > 0) {
                const remaining = (elapsed / done) * (total - done);
                etaText += '  \u00b7  ETA: ~' + _fmtDuration(remaining);
            }
            if (progressEta) progressEta.textContent = etaText;
        } else {
            if (progressEta) progressEta.textContent = '';
        }

        // Show/hide stop button
        if (isScanning) {
            startBtn.style.display = 'none';
            stopBtn.style.display = 'block';

            // Sync stopping state with backend
            if (data.stopping) {
                stopBtn.disabled = true;
                stopBtn.textContent = 'Stopping...';
            } else {
                stopBtn.disabled = false;
                stopBtn.textContent = 'Stop Scan';
            }
        } else {
            startBtn.style.display = 'block';
            stopBtn.style.display = 'none';
            // Reset stop button state when scan finishes
            stopBtn.disabled = false;
            stopBtn.textContent = 'Stop Scan';
            startBtn.disabled = false;
        }

        if (isScanning || (data.progress && data.progress.total > 0)) {
            progressSection.style.display = 'block';
            const { done, total } = data.progress;
            const percent = total > 0 ? Math.round((done / total) * 100) : 0;

            progressBar.style.width = percent + '%';
            progressBar.classList.toggle('animating', isScanning);
            progressText.textContent = percent + '%';
            progressDetail.textContent = `${done}/${total}`;
        } else {
            progressBar.classList.remove('animating');
        }

        if (data.error) {
            statusText.textContent = "Error";
            globalStatus.className = 'dot error';
            showToast(data.error, true);
        }
    }

    async function stopScan() {
        try {
            stopBtn.disabled = true;
            stopBtn.textContent = 'Stopping...';
            const response = await fetch('/api/scan/stop', { method: 'POST' });
            if (response.ok) {
                showToast('Stop signal sent');
            } else {
                const err = await response.json();
                showToast('Error: ' + err.message, true);
                stopBtn.disabled = false;
                stopBtn.textContent = 'Stop Scan';
            }
        } catch (e) {
            showToast('Network error', true);
            stopBtn.disabled = false;
            stopBtn.textContent = 'Stop Scan';
        }
    }

    function startPolling() {
        if (pollInterval) return;
        pollInterval = setInterval(fetchStatus, 1000);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    async function fetchResults() {
        try {
            const response = await fetch('/api/results');
            const data = await response.json();

            // Convert to array and handle both old and new formats
            allResults = Object.keys(data).map(domain => {
                const entry = data[domain];
                // New format (dict)
                if (typeof entry === 'object' && !Array.isArray(entry)) {
                    return {
                        domain,
                        latency: entry.latency_ms || 0,
                        ip: entry.ip || 'N/A',
                        country: entry.country || 'Unknown',
                        city: entry.city || 'Unknown',
                        rx_speed: entry.rx_speed_mbps,
                        tx_speed: entry.tx_speed_mbps,
                        scan_timestamp: entry.scan_timestamp || null,
                        speedtest_timestamp: entry.speedtest_timestamp || null
                    };
                }
                // Old format (array)
                return {
                    domain,
                    latency: entry[0] || 0,
                    ip: entry[1] || 'N/A',
                    country: entry[2] || 'Unknown',
                    city: entry[3] || 'Unknown',
                    rx_speed: null,
                    tx_speed: null
                };
            });

            // Default sort: by download speed (descending), fallback to latency (ascending)
            const hasSpeedData = allResults.some(r => r.rx_speed !== null && r.rx_speed !== undefined);
            if (hasSpeedData) {
                allResults.sort((a, b) => (b.rx_speed || 0) - (a.rx_speed || 0));
                currentSortField = 'rx_speed';
                currentSortOrder = 'desc';
            } else {
                allResults.sort((a, b) => a.latency - b.latency);
                currentSortField = 'latency';
                currentSortOrder = 'asc';
            }
            currentPage = 1;
            updateSortIndicators();
            filterResults();
        } catch (e) {
            console.error("Fetch results failed", e);
        }
    }

    function setPaginationHtml(html) {
        paginationContainers.forEach(container => {
            container.innerHTML = html;
        });
    }

    function renderResults() {
        resultsBody.innerHTML = '';
        const countSpan = document.getElementById('resultsCount');
        countSpan.textContent = filteredResults.length;

        if (filteredResults.length === 0) {
            document.getElementById('noResults').style.display = 'block';
            setPaginationHtml('');
            selectAllBtn.disabled = true;
            vpnSpeedtestBtn.disabled = true;
            return;
        }
        document.getElementById('noResults').style.display = 'none';
        selectAllBtn.disabled = false;

        // Calculate pagination
        const startIndex = (currentPage - 1) * rowsPerPage;
        const endIndex = startIndex + rowsPerPage;
        const pageResults = filteredResults.slice(startIndex, endIndex);

        pageResults.forEach((item, index) => {
            const actualIndex = startIndex + index;
            const row = document.createElement('tr');
            const latencyClass = item.latency < 50 ? 'latency-good' : (item.latency < 150 ? 'latency-med' : 'latency-bad');

            const dlSpeed = item.rx_speed !== null && item.rx_speed !== undefined ? item.rx_speed.toFixed(2) : 'N/A';
            const ulSpeed = item.tx_speed !== null && item.tx_speed !== undefined ? item.tx_speed.toFixed(2) : 'N/A';

            // # Counter column
            const indexTd = document.createElement('td');
            indexTd.textContent = actualIndex + 1;
            indexTd.className = 'text-secondary mono';
            row.appendChild(indexTd);

            const checkboxTd = document.createElement('td');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'row-checkbox';
            checkbox.dataset.domain = item.domain;
            checkbox.checked = selectedDomains.has(item.domain);
            checkbox.addEventListener('change', handleCheckboxChange);
            checkboxTd.appendChild(checkbox);
            row.appendChild(checkboxTd);

            const scanTitle = item.scan_timestamp ? formatTimestamp(item.scan_timestamp) : '';
            const speedTitle = item.speedtest_timestamp ? formatTimestamp(item.speedtest_timestamp) : '';

            // Build cells safely using textContent to prevent XSS
            const domainTd = document.createElement('td');
            const domainStrong = document.createElement('strong');
            domainStrong.className = 'domain-link';
            domainStrong.dataset.domain = item.domain;
            domainStrong.textContent = item.domain;
            domainTd.appendChild(domainStrong);
            row.appendChild(domainTd);

            const latencyTd = document.createElement('td');
            latencyTd.className = latencyClass + ' ts-cell';
            if (scanTitle) latencyTd.title = 'Scanned: ' + scanTitle;
            latencyTd.textContent = item.latency.toFixed(2);
            row.appendChild(latencyTd);

            const ipTd = document.createElement('td');
            ipTd.className = 'mono';
            ipTd.textContent = item.ip;
            row.appendChild(ipTd);

            const countryTd = document.createElement('td');
            countryTd.textContent = item.country;
            row.appendChild(countryTd);

            const cityTd = document.createElement('td');
            cityTd.textContent = item.city;
            row.appendChild(cityTd);

            const dlTd = document.createElement('td');
            dlTd.className = 'ts-cell';
            if (speedTitle) dlTd.title = 'Tested: ' + speedTitle;
            dlTd.textContent = dlSpeed;
            row.appendChild(dlTd);

            const ulTd = document.createElement('td');
            ulTd.className = 'ts-cell';
            if (speedTitle) ulTd.title = 'Tested: ' + speedTitle;
            ulTd.textContent = ulSpeed;
            row.appendChild(ulTd);
            resultsBody.appendChild(row);
        });

        renderPagination();
        updateVpnButtonState();
    }

    function renderPagination() {
        const totalPages = Math.ceil(filteredResults.length / rowsPerPage);

        if (totalPages <= 1) {
            setPaginationHtml('');
            return;
        }

        let html = `
            <button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">&laquo;</button>
        `;

        // Logic for page numbers (show few around current)
        const range = 2;
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= currentPage - range && i <= currentPage + range)) {
                html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="changePage(${i})">${i}</button>`;
            } else if (i === currentPage - range - 1 || i === currentPage + range + 1) {
                html += `<span class="page-info">...</span>`;
            }
        }

        html += `
            <button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">&raquo;</button>
        `;

        setPaginationHtml(html);

        // Expose changePage to global scope for onclick or attach listeners
        window.changePage = (page) => {
            currentPage = page;
            renderResults();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        };
    }

    function filterResults() {
        const query = searchInput.value.toLowerCase();
        filteredResults = allResults.filter(item => {
            if (selectedCountries.size > 0 && !selectedCountries.has(item.country)) return false;
            if (!query) return true;
            return item.domain.toLowerCase().includes(query) ||
                (item.ip && item.ip.toLowerCase().includes(query)) ||
                item.country.toLowerCase().includes(query) ||
                item.city.toLowerCase().includes(query);
        });
        currentPage = 1;
        renderResults();
    }

    // ========================================
    // Country Filter (Dashboard)
    // ========================================
    function buildCountryFilter() {
        const counts = {};
        allResults.forEach(r => { counts[r.country] = (counts[r.country] || 0) + 1; });
        const sorted = Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]));
        return sorted;
    }

    function renderCountryFilter(filter = '') {
        const countries = buildCountryFilter();
        const lf = filter.toLowerCase();
        countryFilterList.innerHTML = '';
        const filtered = countries.filter(([c]) => !lf || c.toLowerCase().includes(lf));
        // Sort: checked countries first, then alphabetical
        filtered.sort((a, b) => {
            const aChecked = selectedCountries.has(a[0]);
            const bChecked = selectedCountries.has(b[0]);
            if (aChecked !== bChecked) return aChecked ? -1 : 1;
            return a[0].localeCompare(b[0]);
        });
        filtered.forEach(([country, count]) => {
                const label = document.createElement('label');
                label.className = 'country-option';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = selectedCountries.has(country);
                cb.addEventListener('change', () => {
                    if (cb.checked) selectedCountries.add(country);
                    else selectedCountries.delete(country);
                    updateCountryFilterBtn();
                    filterResults();
                });
                label.appendChild(cb);
                label.appendChild(document.createTextNode(country));
                const span = document.createElement('span');
                span.className = 'country-count';
                span.textContent = count;
                label.appendChild(span);
                countryFilterList.appendChild(label);
            });
    }

    function updateCountryFilterBtn() {
        if (selectedCountries.size === 0) {
            countryFilterBtn.textContent = '\u{1F310} All Countries';
        } else {
            const total = allResults.filter(r => selectedCountries.has(r.country)).length;
            countryFilterBtn.textContent = `\u{1F310} ${selectedCountries.size} countries (${total})`;
        }
    }

    countryFilterBtn.addEventListener('click', () => {
        const visible = countryFilterDropdown.style.display !== 'none';
        countryFilterDropdown.style.display = visible ? 'none' : 'flex';
        if (!visible) {
            renderCountryFilter();
            countryFilterSearch.focus();
        }
    });

    countryFilterSearch.addEventListener('input', () => renderCountryFilter(countryFilterSearch.value));

    countryFilterClear.addEventListener('click', () => {
        selectedCountries.clear();
        renderCountryFilter(countryFilterSearch.value);
        updateCountryFilterBtn();
        filterResults();
    });

    document.addEventListener('click', (e) => {
        if (!document.querySelector('.country-filter-wrapper').contains(e.target)) {
            countryFilterDropdown.style.display = 'none';
        }
        const exportWrapper = document.querySelector('.export-wrapper');
        if (exportWrapper && !exportWrapper.contains(e.target)) {
            document.getElementById('exportDropdown').style.display = 'none';
        }
    });

    /* ── Export dropdown ── */
    const exportBtn = document.getElementById('exportBtn');
    const exportDropdown = document.getElementById('exportDropdown');
    if (exportBtn && exportDropdown) {
        exportBtn.addEventListener('click', () => {
            exportDropdown.style.display = exportDropdown.style.display === 'none' ? 'flex' : 'none';
        });
        exportDropdown.querySelectorAll('.export-option').forEach(btn => {
            btn.addEventListener('click', () => {
                const fmt = btn.dataset.format;
                const data = filteredResults.length ? filteredResults : allResults;
                let blob, filename;
                if (fmt === 'json') {
                    const obj = {};
                    data.forEach(r => { obj[r.domain] = { ip: r.ip, latency_ms: r.latency_ms, country: r.country, city: r.city, rx_speed_mbps: r.rx_speed_mbps, tx_speed_mbps: r.tx_speed_mbps }; });
                    blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
                    filename = 'results.json';
                } else {
                    const rows = [['Domain', 'IP', 'Latency (ms)', 'Country', 'City', 'Download (Mbps)', 'Upload (Mbps)']];
                    data.forEach(r => rows.push([r.domain, r.ip || '', r.latency_ms ?? '', r.country, r.city, r.rx_speed_mbps ?? '', r.tx_speed_mbps ?? '']));
                    const csv = rows.map(row => row.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\n');
                    blob = new Blob([csv], { type: 'text/csv' });
                    filename = 'results.csv';
                }
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                a.click();
                URL.revokeObjectURL(a.href);
                exportDropdown.style.display = 'none';
            });
        });
    }

    function sortResults(field, order) {
        currentSortField = field;
        currentSortOrder = order;
        filteredResults.sort((a, b) => {
            let valA = a[field];
            let valB = b[field];

            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();

            if (valA < valB) return order === 'asc' ? -1 : 1;
            if (valA > valB) return order === 'asc' ? 1 : -1;
            return 0;
        });
        currentPage = 1;
        updateSortIndicators();
        renderResults();
    }

    function showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.style.borderLeft = isError ? '4px solid #ef4444' : '4px solid #10b981';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 10000);
    }

    function handleCheckboxChange(e) {
        const domain = e.target.dataset.domain;
        if (e.target.checked) selectedDomains.add(domain); else selectedDomains.delete(domain);
        updateVpnButtonState();
        updateSelectAllCheckbox();
    }

    function toggleSelectAll(e) {
        if (e && e.target === selectAllBtn) {
            // GLOBAL TOGGLE (Button)
            const allSelected = selectedDomains.size === filteredResults.length && filteredResults.length > 0;
            if (allSelected) {
                selectedDomains.clear();
            } else {
                filteredResults.forEach(item => selectedDomains.add(item.domain));
            }
            renderResults(); // Re-render to update checkboxes on current page
        } else {
            // LOCAL TOGGLE (Header Checkbox)
            const shouldCheck = selectAllCheckbox.checked;
            const checkboxes = document.querySelectorAll('.row-checkbox');

            checkboxes.forEach(cb => {
                cb.checked = shouldCheck;
                const domain = cb.dataset.domain;
                if (shouldCheck) {
                    selectedDomains.add(domain);
                } else {
                    selectedDomains.delete(domain);
                }
            });
        }

        updateVpnButtonState();
    }

    function updateSelectAllCheckbox() {
        const checkboxes = document.querySelectorAll('.row-checkbox');
        selectAllCheckbox.checked = Array.from(checkboxes).every(cb => cb.checked);
    }

    function updateVpnButtonState() {
        const totalSelected = selectedDomains.size;
        vpnSpeedtestBtn.disabled = totalSelected === 0;

        const allSelectedGlobally = totalSelected === filteredResults.length && filteredResults.length > 0;
        selectAllBtn.textContent = allSelectedGlobally ? `Deselect All (${totalSelected})` : `Select All (${filteredResults.length})`;

        if (totalSelected > 0) {
            vpnSpeedtestBtn.textContent = `Run VPN Speedtest on Selected (${totalSelected})`;
        } else {
            vpnSpeedtestBtn.textContent = `Run VPN Speedtest on Selected`;
        }
    }

    async function runVpnSpeedtest() {
        if (selectedDomains.size === 0) return showToast('No endpoints selected', true);
        try {
            vpnSpeedtestBtn.disabled = true;
            const res = await fetch('/api/vpn-speedtest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ domains: Array.from(selectedDomains) })
            });
            if (res.ok) {
                showToast('VPN speedtest started');
                startPolling();
                // Clear console for new run
                logConsole.innerHTML = '<div class="log-message system"><span class="level">SYS</span> VPN Speedtest batch started...</div>';
            }
            else { const err = await res.json(); showToast('Error: ' + err.message, true); vpnSpeedtestBtn.disabled = false; }
        } catch (e) { showToast('Network error', true); vpnSpeedtestBtn.disabled = false; }
    }

    // Log Console Logic
    const logConsole = document.getElementById('logConsole');
    const clearLogsBtn = document.getElementById('clearLogsBtn');
    let logInterval = null;

    clearLogsBtn.addEventListener('click', async () => {
        await fetch('/api/logs/clear', { method: 'POST' });
        logConsole.innerHTML = '<div class="log-message system"><span class="level">SYS</span> Console cleared.</div>';
    });

    async function fetchLogs() {
        try {
            const response = await fetch('/api/logs');
            const logs = await response.json();
            renderLogs(logs);
        } catch (e) {
            console.error("Failed to fetch logs", e);
        }
    }

    function renderLogs(logs) {
        // Only update if we have new logs or something changed
        const currentCount = logConsole.querySelectorAll('.log-message').length;
        if (logs.length === 0 && currentCount > 1) {
            // Logs might have been cleared on server
            return;
        }

        // We redraw to simplify, but for performance with many logs we could append
        // For now, simple redraw is fine for 200 logs
        const html = logs.map(log => {
            const levelClass = log.level.toLowerCase();
            const levelShort = log.level.substring(0, 3).toUpperCase();
            return `
                <div class="log-message ${levelClass}">
                    <span class="timestamp">[${log.timestamp}]</span>
                    <span class="level">${levelShort}</span>
                    <span class="text">${escapeHtml(log.message)}</span>
                </div>
            `;
        }).join('');

        if (html) {
            const isScrolledToBottom = logConsole.scrollHeight - logConsole.clientHeight <= logConsole.scrollTop + 1;
            logConsole.innerHTML = html;
            if (isScrolledToBottom) {
                logConsole.scrollTop = logConsole.scrollHeight;
            }
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatTimestamp(iso) {
        const d = new Date(iso);
        return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    // Start log polling immediately with AbortController
    let logAbortController = null;
    async function fetchLogsWithAbort() {
        if (logAbortController) logAbortController.abort();
        logAbortController = new AbortController();
        try {
            const response = await fetch('/api/logs', { signal: logAbortController.signal });
            const logs = await response.json();
            renderLogs(logs);
        } catch (e) {
            if (e.name !== 'AbortError') console.error("Failed to fetch logs", e);
        }
    }
    const logPollInterval = setInterval(fetchLogsWithAbort, 2000);

    // Cleanup intervals on page unload
    window.addEventListener('beforeunload', () => {
        if (pollInterval) clearInterval(pollInterval);
        clearInterval(logPollInterval);
        if (logAbortController) logAbortController.abort();
    });

    // ========================================
    // OVPN Configs Upload
    // ========================================
    const updateOvpnBtn = document.getElementById('updateOvpnBtn');
    const ovpnFileInput = document.getElementById('ovpnFileInput');
    const ovpnTooltip = document.getElementById('ovpnTooltip');

    let ovpnStatusLoaded = false;
    const ovpnWrapper = document.querySelector('.ovpn-wrapper');
    ovpnWrapper.addEventListener('mouseenter', () => {
        if (!ovpnStatusLoaded) {
            fetchOvpnStatus();
        }
    });

    async function fetchOvpnStatus() {
        ovpnTooltip.innerHTML = 'Checking...';
        try {
            const resp = await fetch('/api/ovpn/status');
            const data = await resp.json();
            let html = '';
            if (data.last_updated) {
                const localDate = new Date(data.last_updated).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                html += `<div class="tooltip-row"><span class="tooltip-label">Last updated: </span><span class="tooltip-value">${localDate}</span></div>`;
            } else {
                html += `<div class="tooltip-row"><span class="tooltip-label">Last updated: </span><span class="tooltip-value" style="color:var(--error-color)">No configs</span></div>`;
            }
            html += `<div class="tooltip-row"><span class="tooltip-label">UDP configs: </span><span class="tooltip-value">${data.count.toLocaleString()}</span></div>`;
            ovpnTooltip.innerHTML = html;
            ovpnStatusLoaded = true;
        } catch (e) {
            ovpnTooltip.innerHTML = 'Failed to check status';
        }
    }

    let cachedConfig = null;

    // Load config on startup (for OVPN URL behavior)
    fetch('/api/config').then(r => r.json()).then(c => { cachedConfig = c; }).catch(() => {});

    updateOvpnBtn.addEventListener('click', async () => {
        // Check if download URL is configured
        if (!cachedConfig) {
            try { const r = await fetch('/api/config'); cachedConfig = await r.json(); } catch(e) {}
        }
        const downloadUrl = cachedConfig?.schedule?.ovpn_update?.download_url || cachedConfig?.ovpn?.download_url;
        if (downloadUrl) {
            updateOvpnBtn.disabled = true;
            updateOvpnBtn.textContent = 'Downloading...';
            try {
                const resp = await fetch('/api/ovpn/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: downloadUrl})
                });
                const data = await resp.json();
                if (data.status === 'ok') {
                    showToast(`OVPN configs updated: ${data.count} UDP files extracted`);
                    ovpnStatusLoaded = false;
                } else {
                    showToast('Download failed: ' + data.message, true);
                }
            } catch(e) {
                showToast('Network error during download', true);
            } finally {
                updateOvpnBtn.disabled = false;
                updateOvpnBtn.innerHTML = '&#x21BB; OVPN Configs';
            }
        } else {
            ovpnFileInput.click();
        }
    });

    ovpnFileInput.addEventListener('change', async () => {
        const file = ovpnFileInput.files[0];
        if (!file) return;
        ovpnFileInput.value = '';

        updateOvpnBtn.disabled = true;
        updateOvpnBtn.textContent = 'Uploading...';
        try {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch('/api/ovpn/upload', { method: 'POST', body: formData });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast(`OVPN configs updated: ${data.count} UDP files extracted`);
                ovpnStatusLoaded = false;
            } else {
                showToast('Upload failed: ' + data.message, true);
            }
        } catch (e) {
            showToast('Network error during upload', true);
        } finally {
            updateOvpnBtn.disabled = false;
            updateOvpnBtn.innerHTML = '&#x21BB; OVPN Configs';
        }
    });

    // ========================================
    // GeoLite2 Update
    // ========================================
    const updateGeoBtn = document.getElementById('updateGeoBtn');
    const geoliteTooltip = document.getElementById('geoliteTooltip');

    // Fetch GeoLite2 status on hover (once per hover session)
    let geoliteStatusLoaded = false;
    const geoliteWrapper = document.querySelector('.geolite-wrapper');
    geoliteWrapper.addEventListener('mouseenter', () => {
        if (!geoliteStatusLoaded) {
            fetchGeoliteStatus();
        }
    });

    async function fetchGeoliteStatus() {
        geoliteTooltip.innerHTML = 'Checking...';
        try {
            const resp = await fetch('/api/geolite/status');
            const data = await resp.json();
            let html = '';
            if (data.city_last_modified) {
                const localDate = new Date(data.city_last_modified).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                html += `<div class="tooltip-row"><span class="tooltip-label">Local DBs: </span><span class="tooltip-value">${localDate}</span></div>`;
            } else {
                html += `<div class="tooltip-row"><span class="tooltip-label">Local DBs: </span><span class="tooltip-value" style="color:var(--error-color)">Not found</span></div>`;
            }
            if (data.latest_release_date) {
                const releaseDate = new Date(data.latest_release_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                html += `<div class="tooltip-row"><span class="tooltip-label">Latest release: </span><span class="tooltip-value">${releaseDate}</span></div>`;
            }
            if (data.update_available) {
                html += `<div class="tooltip-row"><span class="tooltip-update">&#x2B06; Update available</span></div>`;
            } else if (data.city_last_modified) {
                html += `<div class="tooltip-row"><span class="tooltip-current">&#x2714; Up to date</span></div>`;
            }
            geoliteTooltip.innerHTML = html;
            geoliteStatusLoaded = true;
        } catch (e) {
            geoliteTooltip.innerHTML = 'Failed to check status';
        }
    }

    updateGeoBtn.addEventListener('click', async () => {
        updateGeoBtn.disabled = true;
        updateGeoBtn.textContent = 'Updating...';
        try {
            const resp = await fetch('/api/geolite/update', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast(`GeoLite2 updated: ${data.updated.join(', ')}`);
                geoliteStatusLoaded = false; // Force re-fetch on next hover
            } else {
                showToast('Update failed: ' + data.message, true);
            }
        } catch (e) {
            showToast('Network error during update', true);
        } finally {
            updateGeoBtn.disabled = false;
            updateGeoBtn.innerHTML = '&#x21BB; GeoLite2 DBs';
        }
    });

    // ========================================
    // Servers List Editor
    // ========================================
    const editServersBtn = document.getElementById('editServersBtn');
    const serversModal = document.getElementById('serversModal');
    const closeServersModal = document.getElementById('closeServersModal');
    const cancelServersBtn = document.getElementById('cancelServersBtn');
    const saveServersBtn = document.getElementById('saveServersBtn');
    const serversTextarea = document.getElementById('serversTextarea');
    const serversCount = document.getElementById('serversCount');

    function updateServersCount() {
        const lines = serversTextarea.value.split('\n').filter(l => l.trim().length > 0);
        serversCount.textContent = `${lines.length} server${lines.length !== 1 ? 's' : ''}`;
    }

    editServersBtn.addEventListener('click', async () => {
        serversModal.style.display = 'flex';
        serversTextarea.value = 'Loading...';
        serversTextarea.disabled = true;
        try {
            const resp = await fetch('/api/servers');
            const data = await resp.json();
            serversTextarea.value = data.servers || '';
            serversTextarea.disabled = false;
            updateServersCount();
            serversTextarea.focus();
        } catch (e) {
            serversTextarea.value = '';
            serversTextarea.disabled = false;
            showToast('Failed to load servers list', true);
        }
    });

    serversTextarea.addEventListener('input', updateServersCount);

    function closeServersEditor() {
        serversModal.style.display = 'none';
    }

    closeServersModal.addEventListener('click', closeServersEditor);
    cancelServersBtn.addEventListener('click', closeServersEditor);
    serversModal.addEventListener('mousedown', (e) => {
        if (e.target === serversModal) closeServersEditor();
    });

    saveServersBtn.addEventListener('click', async () => {
        saveServersBtn.disabled = true;
        saveServersBtn.textContent = 'Saving...';
        try {
            const resp = await fetch('/api/servers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ servers: serversTextarea.value })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast(`Servers list saved: ${data.count} entries`);
                closeServersEditor();
            } else {
                showToast('Save failed: ' + data.message, true);
            }
        } catch (e) {
            showToast('Network error', true);
        } finally {
            saveServersBtn.disabled = false;
            saveServersBtn.textContent = 'Save';
        }
    });

    // ========================================
    // OVPN Config Viewer (domain click)
    // ========================================
    const ovpnModal = document.getElementById('ovpnConfigModal');
    const ovpnTitle = document.getElementById('ovpnConfigTitle');
    const ovpnContent = document.getElementById('ovpnConfigContent');
    const closeOvpnBtn = document.getElementById('closeOvpnModal');
    const copyOvpnBtn = document.getElementById('copyOvpnBtn');

    if (ovpnModal) {
        resultsBody.addEventListener('click', async (e) => {
            const link = e.target.closest('.domain-link');
            if (!link) return;
            const domain = link.dataset.domain;
            ovpnTitle.textContent = domain;
            ovpnContent.textContent = 'Loading...';
            ovpnModal.style.display = 'flex';
            try {
                const resp = await fetch(`/api/ovpn/config/${encodeURIComponent(domain)}`);
                const data = await resp.json();
                if (data.status === 'ok') {
                    ovpnContent.textContent = data.content;
                } else {
                    ovpnContent.textContent = data.message || 'Not found';
                }
            } catch (e) {
                ovpnContent.textContent = 'Failed to load config';
            }
        });

        closeOvpnBtn.addEventListener('click', () => { ovpnModal.style.display = 'none'; });
        ovpnModal.addEventListener('click', (e) => { if (e.target === ovpnModal) ovpnModal.style.display = 'none'; });

        copyOvpnBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(ovpnContent.textContent).then(() => {
                copyOvpnBtn.textContent = 'Copied!';
                setTimeout(() => { copyOvpnBtn.textContent = 'Copy'; }, 1500);
            });
        });
    }
});
