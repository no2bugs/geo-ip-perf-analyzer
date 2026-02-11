document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const searchInput = document.getElementById('search');
    const resultsBody = document.getElementById('resultsBody');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressDetail = document.getElementById('progressDetail');
    const progressSection = document.getElementById('progressSection');
    const statusText = document.getElementById('statusText');
    const globalStatus = document.querySelector('.status-indicator .dot');

    let isScanning = false;
    let pollInterval = null;
    let allResults = [];
    let filteredResults = []; // Track filtered results separately for pagination
    let selectedDomains = new Set();
    let currentPage = 1;
    const rowsPerPage = 50;
    const paginationContainers = [
        document.getElementById('pagination'),
        document.getElementById('paginationTop')
    ].filter(Boolean);

    // Initial Load
    fetchStatus();
    fetchResults();

    startBtn.addEventListener('click', startScan);
    stopBtn.addEventListener('click', stopScan);
    refreshBtn.addEventListener('click', fetchResults);
    searchInput.addEventListener('input', filterResults);

    // VPN Speedtest controls
    const selectAllBtn = document.getElementById('selectAllBtn');
    const vpnSpeedtestBtn = document.getElementById('vpnSpeedtestBtn');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');

    selectAllBtn.addEventListener('click', (e) => toggleSelectAll(e));
    vpnSpeedtestBtn.addEventListener('click', runVpnSpeedtest);
    selectAllCheckbox.addEventListener('change', (e) => toggleSelectAll(e));

    // Sorting
    document.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            const order = th.dataset.order === 'asc' ? 'desc' : 'asc';
            th.dataset.order = order;
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

    function updateStatusUI(data) {
        isScanning = data.active;
        startBtn.disabled = isScanning;

        statusText.textContent = isScanning ? "Scanning..." : "Ready";
        globalStatus.className = 'dot ' + (isScanning ? 'running' : 'completed');

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
            progressText.textContent = percent + '%';
            progressDetail.textContent = `${done}/${total}`;
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
                        tx_speed: entry.tx_speed_mbps
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

            // Default sort by latency
            allResults.sort((a, b) => a.latency - b.latency);
            filteredResults = [...allResults];
            currentPage = 1;

            renderResults();
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

            row.insertAdjacentHTML('beforeend', `
                <td><strong>${item.domain}</strong></td>
                <td class="${latencyClass}">${item.latency.toFixed(2)}</td>
                <td class="mono">${item.ip}</td>
                <td>${item.country}</td>
                <td>${item.city}</td>
                <td>${dlSpeed}</td>
                <td>${ulSpeed}</td>
            `);
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
        filteredResults = allResults.filter(item =>
            item.domain.toLowerCase().includes(query) ||
            item.country.toLowerCase().includes(query) ||
            item.city.toLowerCase().includes(query)
        );
        currentPage = 1;
        renderResults();
    }

    function sortResults(field, order) {
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

    // Start log polling immediately
    setInterval(fetchLogs, 2000);
});
