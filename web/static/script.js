document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('startBtn');
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

    // Initial Load
    fetchStatus();
    fetchResults();

    startBtn.addEventListener('click', startScan);
    refreshBtn.addEventListener('click', fetchResults);
    searchInput.addEventListener('input', filterResults);

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

        try {
            startBtn.disabled = true;
            const response = await fetch('/api/scan/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pings, timeout, workers })
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

            // Convert to array
            allResults = Object.keys(data).map(domain => ({
                domain,
                latency: data[domain][0],
                ip: data[domain][1],
                country: data[domain][2],
                city: data[domain][3]
            }));

            // Default sort by latency
            allResults.sort((a, b) => a.latency - b.latency);

            renderResults(allResults);
        } catch (e) {
            console.error("Fetch results failed", e);
        }
    }

    function renderResults(results) {
        resultsBody.innerHTML = '';
        if (results.length === 0) {
            document.getElementById('noResults').style.display = 'block';
            return;
        }
        document.getElementById('noResults').style.display = 'none';

        results.forEach(item => {
            const row = document.createElement('tr');
            const latencyClass = item.latency < 50 ? 'latency-good' : (item.latency < 150 ? 'latency-med' : 'latency-bad');

            row.innerHTML = `
                <td><strong>${item.domain}</strong></td>
                <td class="${latencyClass}">${item.latency.toFixed(2)}</td>
                <td class="mono">${item.ip}</td>
                <td>${item.country}</td>
                <td>${item.city}</td>
            `;
            resultsBody.appendChild(row);
        });
    }

    function filterResults() {
        const query = searchInput.value.toLowerCase();
        const filtered = allResults.filter(item =>
            item.domain.toLowerCase().includes(query) ||
            item.country.toLowerCase().includes(query) ||
            item.city.toLowerCase().includes(query)
        );
        renderResults(filtered);
    }

    function sortResults(field, order) {
        const sorted = [...allResults].sort((a, b) => {
            let valA = a[field];
            let valB = b[field];

            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();

            if (valA < valB) return order === 'asc' ? -1 : 1;
            if (valA > valB) return order === 'asc' ? 1 : -1;
            return 0;
        });
        renderResults(sorted);
    }

    function showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.style.borderLeft = isError ? '4px solid #ef4444' : '4px solid #10b981';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }
});
