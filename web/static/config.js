document.addEventListener('DOMContentLoaded', () => {
    // ========================================
    // Tabs
    // ========================================
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        });
    });

    // ========================================
    // Day-picker buttons
    // ========================================
    document.querySelectorAll('.day-btn').forEach(btn => {
        btn.addEventListener('click', () => btn.classList.toggle('selected'));
    });

    // ========================================
    // Visibility helpers
    // ========================================
    function updateVisibility() {
        const sections = [
            { enabled: 'cfgVpnEnabled', opts: 'cfgVpnOptions', interval: 'cfgVpnInterval', dayWrap: 'cfgVpnDayWrap', dayPicker: 'cfgVpnDays', domWrap: 'cfgVpnDomWrap' },
            { enabled: 'cfgGeoEnabled', opts: 'cfgGeoOptions', interval: 'cfgGeoInterval', dayWrap: 'cfgGeoDayWrap', dayPicker: 'cfgGeoDays', domWrap: 'cfgGeoDomWrap' },
            { enabled: 'cfgOvpnSchedEnabled', opts: 'cfgOvpnSchedOptions', interval: 'cfgOvpnInterval', dayWrap: 'cfgOvpnDayWrap', dayPicker: 'cfgOvpnDays', domWrap: 'cfgOvpnDomWrap' },
            { enabled: 'cfgSrvEnabled', opts: 'cfgSrvOptions', interval: 'cfgSrvInterval', dayWrap: 'cfgSrvDayWrap', dayPicker: 'cfgSrvDays', domWrap: 'cfgSrvDomWrap' }
        ];
        sections.forEach(s => {
            const on = document.getElementById(s.enabled).checked;
            document.getElementById(s.opts).style.display = on ? '' : 'none';
            const intv = document.getElementById(s.interval).value;
            document.getElementById(s.dayWrap).style.display = intv === 'weekly' ? '' : 'none';
            document.getElementById(s.dayPicker).style.display = intv === 'custom' ? '' : 'none';
            document.getElementById(s.domWrap).style.display = intv === 'monthly' ? '' : 'none';
        });

        const ntfyOn = document.getElementById('cfgNtfyEnabled').checked;
        document.getElementById('cfgNtfyOptions').style.display = ntfyOn ? '' : 'none';
    }

    // Attach listeners
    ['cfgVpnEnabled', 'cfgGeoEnabled', 'cfgOvpnSchedEnabled', 'cfgSrvEnabled', 'cfgNtfyEnabled'].forEach(id =>
        document.getElementById(id).addEventListener('change', updateVisibility));
    ['cfgVpnInterval', 'cfgGeoInterval', 'cfgOvpnInterval', 'cfgSrvInterval'].forEach(id =>
        document.getElementById(id).addEventListener('change', updateVisibility));

    // ========================================
    // Load config
    // ========================================
    async function loadConfig() {
        try {
            const resp = await fetch('/api/config');
            const config = await resp.json();
            populateForm(config);
        } catch (e) {
            showToast('Failed to load config', true);
        }
    }

    function setDayButtons(containerId, days) {
        const btns = document.querySelectorAll(`#${containerId} .day-btn`);
        btns.forEach(btn => {
            btn.classList.toggle('selected', (days || []).includes(btn.dataset.day));
        });
    }

    function getDayButtons(containerId) {
        return Array.from(document.querySelectorAll(`#${containerId} .day-btn.selected`))
            .map(btn => btn.dataset.day);
    }

    function populateForm(config) {
        const vpn = config.schedule?.vpn_speedtest || {};
        document.getElementById('cfgVpnEnabled').checked = vpn.enabled || false;
        document.getElementById('cfgVpnInterval').value = vpn.interval || 'daily';
        document.getElementById('cfgVpnDay').value = vpn.day || 'monday';
        document.getElementById('cfgVpnDom').value = vpn.dom || 1;
        document.getElementById('cfgVpnTime').value = vpn.time || '03:00';
        setDayButtons('cfgVpnDays', vpn.days);

        const geo = config.schedule?.geolite_update || {};
        document.getElementById('cfgGeoEnabled').checked = geo.enabled || false;
        document.getElementById('cfgGeoInterval').value = geo.interval || 'weekly';
        document.getElementById('cfgGeoDay').value = geo.day || 'sunday';
        document.getElementById('cfgGeoDom').value = geo.dom || 1;
        document.getElementById('cfgGeoTime').value = geo.time || '04:00';
        setDayButtons('cfgGeoDays', geo.days);

        const ovpn = config.schedule?.ovpn_update || {};
        document.getElementById('cfgOvpnSchedEnabled').checked = ovpn.enabled || false;
        document.getElementById('cfgOvpnInterval').value = ovpn.interval || 'weekly';
        document.getElementById('cfgOvpnDay').value = ovpn.day || 'sunday';
        document.getElementById('cfgOvpnDom').value = ovpn.dom || 1;
        document.getElementById('cfgOvpnTime').value = ovpn.time || '05:00';
        setDayButtons('cfgOvpnDays', ovpn.days);

        const srv = config.schedule?.servers_update || {};
        document.getElementById('cfgSrvEnabled').checked = srv.enabled || false;
        document.getElementById('cfgSrvCommand').value = srv.command || '';
        document.getElementById('cfgSrvInterval').value = srv.interval || 'weekly';
        document.getElementById('cfgSrvDay').value = srv.day || 'sunday';
        document.getElementById('cfgSrvDom').value = srv.dom || 1;
        document.getElementById('cfgSrvTime').value = srv.time || '06:00';
        setDayButtons('cfgSrvDays', srv.days);

        document.getElementById('cfgOvpnUrl').value = config.ovpn?.download_url || '';

        const ntfy = config.notifications?.ntfy || {};
        document.getElementById('cfgNtfyEnabled').checked = ntfy.enabled || false;
        document.getElementById('cfgNtfyUrl').value = ntfy.url || '';
        document.getElementById('cfgEvtVpnComplete').checked = ntfy.events?.vpn_speedtest_complete || false;
        document.getElementById('cfgEvtVpnError').checked = ntfy.events?.vpn_speedtest_error !== false;
        document.getElementById('cfgEvtGeoUpdated').checked = ntfy.events?.geolite_updated || false;
        document.getElementById('cfgEvtGeoError').checked = ntfy.events?.geolite_update_error !== false;
        document.getElementById('cfgEvtOvpnUpdated').checked = ntfy.events?.ovpn_updated || false;
        document.getElementById('cfgEvtOvpnError').checked = ntfy.events?.ovpn_update_error !== false;
        document.getElementById('cfgEvtSrvUpdated').checked = ntfy.events?.servers_updated || false;
        document.getElementById('cfgEvtSrvError').checked = ntfy.events?.servers_update_error !== false;

        updateVisibility();
    }

    // ========================================
    // Collect & save
    // ========================================
    function collectConfig() {
        return {
            schedule: {
                vpn_speedtest: {
                    enabled: document.getElementById('cfgVpnEnabled').checked,
                    interval: document.getElementById('cfgVpnInterval').value,
                    day: document.getElementById('cfgVpnDay').value,
                    days: getDayButtons('cfgVpnDays'),
                    dom: parseInt(document.getElementById('cfgVpnDom').value) || 1,
                    time: document.getElementById('cfgVpnTime').value
                },
                geolite_update: {
                    enabled: document.getElementById('cfgGeoEnabled').checked,
                    interval: document.getElementById('cfgGeoInterval').value,
                    day: document.getElementById('cfgGeoDay').value,
                    days: getDayButtons('cfgGeoDays'),
                    dom: parseInt(document.getElementById('cfgGeoDom').value) || 1,
                    time: document.getElementById('cfgGeoTime').value
                },
                ovpn_update: {
                    enabled: document.getElementById('cfgOvpnSchedEnabled').checked,
                    interval: document.getElementById('cfgOvpnInterval').value,
                    day: document.getElementById('cfgOvpnDay').value,
                    days: getDayButtons('cfgOvpnDays'),
                    dom: parseInt(document.getElementById('cfgOvpnDom').value) || 1,
                    time: document.getElementById('cfgOvpnTime').value
                },
                servers_update: {
                    enabled: document.getElementById('cfgSrvEnabled').checked,
                    command: document.getElementById('cfgSrvCommand').value.trim(),
                    interval: document.getElementById('cfgSrvInterval').value,
                    day: document.getElementById('cfgSrvDay').value,
                    days: getDayButtons('cfgSrvDays'),
                    dom: parseInt(document.getElementById('cfgSrvDom').value) || 1,
                    time: document.getElementById('cfgSrvTime').value
                }
            },
            notifications: {
                ntfy: {
                    enabled: document.getElementById('cfgNtfyEnabled').checked,
                    url: document.getElementById('cfgNtfyUrl').value.trim(),
                    events: {
                        vpn_speedtest_complete: document.getElementById('cfgEvtVpnComplete').checked,
                        vpn_speedtest_error: document.getElementById('cfgEvtVpnError').checked,
                        geolite_updated: document.getElementById('cfgEvtGeoUpdated').checked,
                        geolite_update_error: document.getElementById('cfgEvtGeoError').checked,
                        ovpn_updated: document.getElementById('cfgEvtOvpnUpdated').checked,
                        ovpn_update_error: document.getElementById('cfgEvtOvpnError').checked,
                        servers_updated: document.getElementById('cfgEvtSrvUpdated').checked,
                        servers_update_error: document.getElementById('cfgEvtSrvError').checked
                    }
                }
            },
            ovpn: {
                download_url: document.getElementById('cfgOvpnUrl').value.trim()
            }
        };
    }

    const saveBtn = document.getElementById('saveConfigBtn');
    const statusEl = document.getElementById('configStatus');

    saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
            const config = collectConfig();
            const resp = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast('Configuration saved');
                statusEl.textContent = 'Saved ' + new Date().toLocaleTimeString();
            } else {
                showToast('Save failed: ' + data.message, true);
            }
        } catch (e) {
            showToast('Network error', true);
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Configuration';
        }
    });

    // ========================================
    // Run Now Buttons
    // ========================================
    document.querySelectorAll('.run-now-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const job = btn.dataset.job;
            btn.disabled = true;
            const origText = btn.innerHTML;
            btn.textContent = 'Running...';
            try {
                const resp = await fetch('/api/schedule/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ job })
                });
                const data = await resp.json();
                if (data.status === 'ok') {
                    showToast(`${job.replace(/_/g, ' ')} started`);
                } else {
                    showToast(data.message || 'Failed', true);
                }
            } catch (e) {
                showToast('Network error', true);
            } finally {
                btn.disabled = false;
                btn.innerHTML = origText;
            }
        });
    });

    // ========================================
    // Test Notification
    // ========================================
    const testNotifBtn = document.getElementById('testNotifBtn');
    testNotifBtn.addEventListener('click', async () => {
        testNotifBtn.disabled = true;
        testNotifBtn.textContent = 'Sending...';
        try {
            const resp = await fetch('/api/config/test-notification', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast('Test notification sent');
            } else {
                showToast(data.message || 'Failed to send', true);
            }
        } catch (e) {
            showToast('Network error', true);
        } finally {
            testNotifBtn.disabled = false;
            testNotifBtn.textContent = '\u{1F514} Send Test Notification';
        }
    });

    // ========================================
    // Toast
    // ========================================
    function showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.style.borderLeft = isError ? '4px solid #ef4444' : '4px solid #10b981';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 5000);
    }

    // Init
    loadConfig();
});
