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
        vpnSelectedCountries = vpn.countries || [];
        loadVpnCountries();
        document.getElementById('cfgVpnLastRun').textContent = vpn.last_run ? `Last run: ${vpn.last_run}` : '';

        const geo = config.schedule?.geolite_update || {};
        document.getElementById('cfgGeoEnabled').checked = geo.enabled || false;
        document.getElementById('cfgGeoInterval').value = geo.interval || 'weekly';
        document.getElementById('cfgGeoDay').value = geo.day || 'sunday';
        document.getElementById('cfgGeoDom').value = geo.dom || 1;
        document.getElementById('cfgGeoTime').value = geo.time || '04:00';
        setDayButtons('cfgGeoDays', geo.days);
        document.getElementById('cfgGeoLastRun').textContent = geo.last_run ? `Last run: ${geo.last_run}` : '';

        const ovpn = config.schedule?.ovpn_update || {};
        document.getElementById('cfgOvpnSchedEnabled').checked = ovpn.enabled || false;
        document.getElementById('cfgOvpnInterval').value = ovpn.interval || 'weekly';
        document.getElementById('cfgOvpnDay').value = ovpn.day || 'sunday';
        document.getElementById('cfgOvpnDom').value = ovpn.dom || 1;
        document.getElementById('cfgOvpnTime').value = ovpn.time || '05:00';
        setDayButtons('cfgOvpnDays', ovpn.days);
        document.getElementById('cfgOvpnUrl').value = ovpn.download_url || config.ovpn?.download_url || '';
        document.getElementById('cfgOvpnLastRun').textContent = ovpn.last_run ? `Last run: ${ovpn.last_run}` : '';

        const srv = config.schedule?.servers_update || {};
        document.getElementById('cfgSrvEnabled').checked = srv.enabled || false;
        renderSrvCommands(srv.commands || (srv.command ? [{command: srv.command, label: '', enabled: true}] : []));
        document.getElementById('cfgSrvInterval').value = srv.interval || 'weekly';
        document.getElementById('cfgSrvDay').value = srv.day || 'sunday';
        document.getElementById('cfgSrvDom').value = srv.dom || 1;
        document.getElementById('cfgSrvTime').value = srv.time || '06:00';
        setDayButtons('cfgSrvDays', srv.days);
        document.getElementById('cfgSrvPruneStale').checked = srv.prune_stale || false;
        document.getElementById('cfgSrvLastRun').textContent = srv.last_run ? `Last run: ${srv.last_run}` : '';

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
                    time: document.getElementById('cfgVpnTime').value,
                    countries: vpnSelectedCountries
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
                    time: document.getElementById('cfgOvpnTime').value,
                    download_url: document.getElementById('cfgOvpnUrl').value.trim()
                },
                servers_update: {
                    enabled: document.getElementById('cfgSrvEnabled').checked,
                    commands: collectSrvCommands(),
                    interval: document.getElementById('cfgSrvInterval').value,
                    day: document.getElementById('cfgSrvDay').value,
                    days: getDayButtons('cfgSrvDays'),
                    dom: parseInt(document.getElementById('cfgSrvDom').value) || 1,
                    time: document.getElementById('cfgSrvTime').value,
                    prune_stale: document.getElementById('cfgSrvPruneStale').checked
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
    // Prune Stale Servers
    // ========================================
    const pruneNowBtn = document.getElementById('pruneNowBtn');
    pruneNowBtn.addEventListener('click', async () => {
        pruneNowBtn.disabled = true;
        const origText = pruneNowBtn.textContent;
        pruneNowBtn.textContent = 'Cleaning up...';
        try {
            const resp = await fetch('/api/prune-stale', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast(data.message);
            } else {
                showToast(data.message || 'Prune failed', true);
            }
        } catch (e) {
            showToast('Network error', true);
        } finally {
            pruneNowBtn.disabled = false;
            pruneNowBtn.textContent = origText;
        }
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

    // ========================================
    // Multi-command list (Servers List Update)
    // ========================================
    const srvCommandsContainer = document.getElementById('cfgSrvCommands');
    const addSrvCommandBtn = document.getElementById('addSrvCommandBtn');

    function renderSrvCommands(commands) {
        srvCommandsContainer.innerHTML = '';
        if (!commands || commands.length === 0) return;
        commands.forEach((cmd, idx) => addCommandItem(cmd, idx));
    }

    function addCommandItem(cmd = {command: '', label: '', enabled: true}) {
        const item = document.createElement('div');
        item.className = 'command-item' + (cmd.enabled === false ? ' disabled' : '');
        item.innerHTML = `
            <div class="command-item-header">
                <label class="switch" style="transform: scale(0.8);">
                    <input type="checkbox" class="cmd-enabled" ${cmd.enabled !== false ? 'checked' : ''}>
                    <span class="slider"></span>
                </label>
                <input type="text" class="cmd-label" placeholder="Comment (e.g. Switzerland servers)" value="${(cmd.label || '').replace(/"/g, '&quot;')}">
                <div class="command-order-btns">
                    <button type="button" class="command-move-btn" data-dir="up" title="Move up">&uarr;</button>
                    <button type="button" class="command-move-btn" data-dir="down" title="Move down">&darr;</button>
                </div>
                <button type="button" class="command-remove-btn" title="Remove">&times;</button>
            </div>
            <div class="command-item-body">
                <textarea class="cmd-command" rows="2" placeholder="Shell script — use multiple lines for complex commands">${(cmd.command || '').replace(/</g, '&lt;')}</textarea>
            </div>
        `;
        item.querySelector('.command-remove-btn').addEventListener('click', () => item.remove());
        item.querySelector('.cmd-enabled').addEventListener('change', (e) => {
            item.classList.toggle('disabled', !e.target.checked);
        });
        const ta = item.querySelector('.cmd-command');
        autoResizeTextarea(ta);
        ta.addEventListener('input', () => autoResizeTextarea(ta));
        item.querySelectorAll('.command-move-btn').forEach(btn => {
            btn.addEventListener('click', () => moveCommandItem(item, btn.dataset.dir));
        });
        srvCommandsContainer.appendChild(item);
    }

    function autoResizeTextarea(ta) {
        ta.style.height = 'auto';
        ta.style.height = ta.scrollHeight + 'px';
    }

    function moveCommandItem(item, dir) {
        if (dir === 'up' && item.previousElementSibling) {
            srvCommandsContainer.insertBefore(item, item.previousElementSibling);
        } else if (dir === 'down' && item.nextElementSibling) {
            srvCommandsContainer.insertBefore(item.nextElementSibling, item);
        }
    }

    addSrvCommandBtn.addEventListener('click', () => addCommandItem());

    function collectSrvCommands() {
        return Array.from(srvCommandsContainer.querySelectorAll('.command-item')).map(item => ({
            command: item.querySelector('.cmd-command').value.trimEnd(),
            label: item.querySelector('.cmd-label').value.trim(),
            enabled: item.querySelector('.cmd-enabled').checked
        })).filter(c => c.command);
    }

    // ========================================
    // VPN Speedtest Country Picker
    // ========================================
    let vpnSelectedCountries = [];
    let vpnCountriesData = [];
    const vpnCountryBtn = document.getElementById('cfgVpnCountryBtn');
    const vpnCountryDropdown = document.getElementById('cfgVpnCountryDropdown');
    const vpnCountryList = document.getElementById('cfgVpnCountryList');
    const vpnCountrySearch = document.getElementById('cfgVpnCountrySearch');
    const vpnCountryClear = document.getElementById('cfgVpnCountryClear');

    function updateVpnCountryBtn() {
        if (vpnSelectedCountries.length === 0) {
            vpnCountryBtn.textContent = 'All Countries';
        } else {
            const total = vpnSelectedCountries.reduce((sum, c) => {
                const found = vpnCountriesData.find(d => d.country === c);
                return sum + (found ? found.count : 0);
            }, 0);
            vpnCountryBtn.textContent = `${vpnSelectedCountries.length} countries (${total} servers)`;
        }
    }

    function renderVpnCountryList(filter = '') {
        vpnCountryList.innerHTML = '';
        const lf = filter.toLowerCase();
        const filtered = vpnCountriesData.filter(d => !lf || d.country.toLowerCase().includes(lf));
        // Sort: checked countries first, then alphabetical
        filtered.sort((a, b) => {
            const aChecked = vpnSelectedCountries.includes(a.country);
            const bChecked = vpnSelectedCountries.includes(b.country);
            if (aChecked !== bChecked) return aChecked ? -1 : 1;
            return a.country.localeCompare(b.country);
        });
        filtered.forEach(d => {
                const label = document.createElement('label');
                label.className = 'country-option';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = vpnSelectedCountries.includes(d.country);
                cb.addEventListener('change', () => {
                    if (cb.checked) {
                        if (!vpnSelectedCountries.includes(d.country)) vpnSelectedCountries.push(d.country);
                    } else {
                        vpnSelectedCountries = vpnSelectedCountries.filter(c => c !== d.country);
                    }
                    updateVpnCountryBtn();
                });
                label.appendChild(cb);
                label.appendChild(document.createTextNode(d.country));
                const span = document.createElement('span');
                span.className = 'country-count';
                span.textContent = d.count;
                label.appendChild(span);
                vpnCountryList.appendChild(label);
            });
    }

    async function loadVpnCountries() {
        try {
            const resp = await fetch('/api/countries');
            vpnCountriesData = await resp.json();
        } catch (e) {
            vpnCountriesData = [];
        }
        renderVpnCountryList();
        updateVpnCountryBtn();
    }

    vpnCountryBtn.addEventListener('click', () => {
        const visible = vpnCountryDropdown.style.display !== 'none';
        vpnCountryDropdown.style.display = visible ? 'none' : 'flex';
        vpnCountryBtn.closest('.config-card').classList.toggle('dropdown-open', !visible);
        if (!visible) vpnCountrySearch.focus();
    });

    vpnCountrySearch.addEventListener('input', () => renderVpnCountryList(vpnCountrySearch.value));

    vpnCountryClear.addEventListener('click', () => {
        vpnSelectedCountries = [];
        renderVpnCountryList(vpnCountrySearch.value);
        updateVpnCountryBtn();
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!document.getElementById('cfgVpnCountryPicker').contains(e.target)) {
            vpnCountryDropdown.style.display = 'none';
            vpnCountryBtn.closest('.config-card').classList.remove('dropdown-open');
        }
    });

    // ========================================
    // Credentials Tab
    // ========================================
    const credsStatus = document.getElementById('credsStatus');
    const saveCredsBtn = document.getElementById('saveCredsBtn');
    const togglePwdBtn = document.getElementById('togglePwdBtn');
    const pwdInput = document.getElementById('cfgVpnPassword');

    togglePwdBtn.addEventListener('click', () => {
        pwdInput.type = pwdInput.type === 'password' ? 'text' : 'password';
    });

    async function loadCredentials() {
        try {
            const resp = await fetch('/api/credentials');
            const data = await resp.json();
            document.getElementById('cfgVpnUsername').value = data.vpn_username || '';
            // Don't populate password — show placeholder if one is set
            pwdInput.value = '';
            pwdInput.placeholder = data.vpn_password_set ? '••••••••  (unchanged)' : 'VPN service password';
        } catch (e) { /* ignore */ }
    }

    saveCredsBtn.addEventListener('click', async () => {
        saveCredsBtn.disabled = true;
        saveCredsBtn.textContent = 'Saving...';
        try {
            const payload = { vpn_username: document.getElementById('cfgVpnUsername').value.trim() };
            const pwd = pwdInput.value;
            if (pwd) payload.vpn_password = pwd;
            const resp = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast('Credentials saved');
                credsStatus.textContent = 'Saved ' + new Date().toLocaleTimeString();
                pwdInput.value = '';
                pwdInput.placeholder = '••••••••  (unchanged)';
            } else {
                showToast('Save failed: ' + data.message, true);
            }
        } catch (e) {
            showToast('Network error', true);
        } finally {
            saveCredsBtn.disabled = false;
            saveCredsBtn.textContent = 'Save Credentials';
        }
    });

    // ========================================
    // Theme Picker
    // ========================================
    const engine = window.__THEME_ENGINE || {};
    const paletteGrid = document.getElementById('paletteGrid');
    const wallpaperGrid = document.getElementById('wallpaperGrid');
    let currentTheme = { palette: 'default', wallpaper: 'none', wallpaper_mode: 'tile' };

    function renderPalettes() {
        paletteGrid.innerHTML = '';
        for (const [key, vars] of Object.entries(engine.PALETTES || {})) {
            const swatch = document.createElement('div');
            swatch.className = 'palette-swatch' + (currentTheme.palette === key ? ' active' : '');
            const colors = document.createElement('div');
            colors.className = 'palette-colors';
            [vars['--bg-color'], vars['--accent-color'], vars['--success-color'], vars['--text-primary']].forEach(c => {
                const dot = document.createElement('span');
                dot.style.background = c;
                colors.appendChild(dot);
            });
            swatch.appendChild(colors);
            const label = document.createElement('div');
            label.className = 'palette-name';
            label.textContent = (engine.PALETTE_LABELS || {})[key] || key;
            swatch.appendChild(label);
            swatch.addEventListener('click', () => {
                currentTheme.palette = key;
                saveTheme();
                renderPalettes();
            });
            paletteGrid.appendChild(swatch);
        }
    }

    function renderWallpapers() {
        wallpaperGrid.innerHTML = '';
        for (const [key, bgVal] of Object.entries(engine.WALLPAPERS || {})) {
            const tile = document.createElement('div');
            tile.className = 'wallpaper-tile' + (currentTheme.wallpaper === key ? ' active' : '');
            const preview = document.createElement('div');
            preview.className = 'wallpaper-preview';
            if (bgVal !== 'none') {
                preview.style.backgroundImage = bgVal;
            }
            tile.appendChild(preview);
            const label = document.createElement('div');
            label.className = 'wallpaper-label';
            label.textContent = (engine.WALLPAPER_LABELS || {})[key] || key;
            tile.appendChild(label);
            tile.addEventListener('click', () => {
                currentTheme.wallpaper = key;
                saveTheme();
                renderWallpapers();
                refreshCustomWallpaperUI();
            });
            wallpaperGrid.appendChild(tile);
        }
    }

    async function saveTheme() {
        engine.applyTheme(currentTheme);
        localStorage.setItem('geo_ip_theme', JSON.stringify(currentTheme));
        try {
            await fetch('/api/theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    palette: currentTheme.palette,
                    wallpaper: currentTheme.wallpaper,
                    wallpaper_mode: currentTheme.wallpaper_mode || 'tile',
                    map_thresholds: getMapThresholds()
                })
            });
        } catch (e) { /* silent */ }
    }

    async function loadTheme() {
        try {
            const resp = await fetch('/api/theme');
            const data = await resp.json();
            currentTheme = data;
            loadMapThresholds(data.map_thresholds);
        } catch (e) { /* use defaults */ }
        renderPalettes();
        renderWallpapers();
        refreshCustomWallpaperUI();
    }

    // ========================================
    // Custom Wallpaper Upload
    // ========================================
    const wallpaperFileInput = document.getElementById('wallpaperFileInput');
    const uploadStatus = document.getElementById('uploadStatus');
    const removeWallpaperBtn = document.getElementById('removeWallpaperBtn');
    const customPreview = document.getElementById('customWallpaperPreview');
    const wallpaperModeSelect = document.getElementById('wallpaperModeSelect');

    function refreshCustomWallpaperUI() {
        fetch('/api/wallpaper/custom', { method: 'HEAD' }).then(r => {
            const hasFile = r.ok;
            removeWallpaperBtn.style.display = hasFile ? '' : 'none';
            wallpaperModeSelect.style.display = hasFile ? '' : 'none';
            if (hasFile) {
                customPreview.style.display = 'block';
                customPreview.style.backgroundImage = 'url(/api/wallpaper/custom?' + Date.now() + ')';
                wallpaperModeSelect.value = currentTheme.wallpaper_mode || 'tile';
            } else {
                customPreview.style.display = 'none';
            }
        }).catch(() => {
            removeWallpaperBtn.style.display = 'none';
            wallpaperModeSelect.style.display = 'none';
            customPreview.style.display = 'none';
        });
    }

    wallpaperModeSelect.addEventListener('change', () => {
        currentTheme.wallpaper_mode = wallpaperModeSelect.value;
        if (currentTheme.wallpaper === 'custom') {
            engine.applyTheme(currentTheme);
        }
        saveTheme();
    });

    wallpaperFileInput.addEventListener('change', async () => {
        const file = wallpaperFileInput.files[0];
        if (!file) return;
        uploadStatus.textContent = 'Uploading...';
        const form = new FormData();
        form.append('file', file);
        try {
            const resp = await fetch('/api/wallpaper/upload', { method: 'POST', body: form });
            const data = await resp.json();
            if (data.status === 'ok') {
                uploadStatus.textContent = 'Uploaded!';
                currentTheme.wallpaper = 'custom';
                engine.applyTheme(currentTheme);
                localStorage.setItem('geo_ip_theme', JSON.stringify(currentTheme));
                renderWallpapers();
                refreshCustomWallpaperUI();
            } else {
                uploadStatus.textContent = data.message || 'Upload failed';
            }
        } catch (e) {
            uploadStatus.textContent = 'Upload failed';
        }
        wallpaperFileInput.value = '';
        setTimeout(() => { uploadStatus.textContent = ''; }, 3000);
    });

    removeWallpaperBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/wallpaper/custom', { method: 'DELETE' });
            currentTheme.wallpaper = 'none';
            saveTheme();
            renderWallpapers();
            refreshCustomWallpaperUI();
        } catch (e) { /* silent */ }
    });

    // ========================================
    // Map Thresholds
    // ========================================
    const cfgMapLatGreen = document.getElementById('cfgMapLatGreen');
    const cfgMapLatYellow = document.getElementById('cfgMapLatYellow');
    const cfgMapSpeedRed = document.getElementById('cfgMapSpeedRed');
    const cfgMapSpeedYellow = document.getElementById('cfgMapSpeedYellow');

    function updateThresholdPreviews() {
        const lg = cfgMapLatGreen.value, ly = cfgMapLatYellow.value;
        const sr = cfgMapSpeedRed.value, sy = cfgMapSpeedYellow.value;
        document.getElementById('tpLatGreen').textContent = lg;
        document.getElementById('tpLatGreen2').textContent = lg;
        document.getElementById('tpLatYellow').textContent = ly;
        document.getElementById('tpLatYellow2').textContent = ly;
        document.getElementById('tpSpeedRed').textContent = sr;
        document.getElementById('tpSpeedRed2').textContent = sr;
        document.getElementById('tpSpeedYellow').textContent = sy;
        document.getElementById('tpSpeedYellow2').textContent = sy;
    }

    [cfgMapLatGreen, cfgMapLatYellow, cfgMapSpeedRed, cfgMapSpeedYellow].forEach(el => {
        el.addEventListener('input', updateThresholdPreviews);
    });

    function loadMapThresholds(thresholds) {
        if (!thresholds) return;
        if (thresholds.latency) {
            cfgMapLatGreen.value = thresholds.latency.green || 50;
            cfgMapLatYellow.value = thresholds.latency.yellow || 150;
        }
        if (thresholds.speed) {
            cfgMapSpeedRed.value = thresholds.speed.red || 50;
            cfgMapSpeedYellow.value = thresholds.speed.yellow || 200;
        }
        updateThresholdPreviews();
    }

    function getMapThresholds() {
        return {
            latency: {
                green: parseInt(cfgMapLatGreen.value) || 50,
                yellow: parseInt(cfgMapLatYellow.value) || 150
            },
            speed: {
                red: parseInt(cfgMapSpeedRed.value) || 50,
                yellow: parseInt(cfgMapSpeedYellow.value) || 200
            }
        };
    }

    // Init
    loadConfig();
    loadCredentials();
    loadTheme();
});
