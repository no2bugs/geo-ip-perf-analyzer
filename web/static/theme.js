/**
 * Theme engine — applies palette + wallpaper from /api/theme on every page.
 * Loaded before page-specific scripts so the theme is painted immediately.
 */
(function () {
    const PALETTES = {
        default:   { '--bg-color': '#0f172a', '--panel-bg': 'rgba(30,41,59,0.7)',  '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--accent-color': '#3b82f6', '--accent-hover': '#2563eb', '--success-color': '#10b981', '--error-color': '#ef4444', '--border-color': 'rgba(148,163,184,0.1)' },
        midnight:  { '--bg-color': '#0a0e1a', '--panel-bg': 'rgba(16,20,40,0.75)', '--text-primary': '#e2e8f0', '--text-secondary': '#7c8db5', '--accent-color': '#6366f1', '--accent-hover': '#4f46e5', '--success-color': '#22d3ee', '--error-color': '#f43f5e', '--border-color': 'rgba(99,102,241,0.12)' },
        emerald:   { '--bg-color': '#0c1a14', '--panel-bg': 'rgba(16,40,30,0.7)',  '--text-primary': '#ecfdf5', '--text-secondary': '#6ee7b7', '--accent-color': '#10b981', '--accent-hover': '#059669', '--success-color': '#34d399', '--error-color': '#fb7185', '--border-color': 'rgba(16,185,129,0.12)' },
        sunset:    { '--bg-color': '#1a0e0e', '--panel-bg': 'rgba(40,20,20,0.7)',  '--text-primary': '#fef2f2', '--text-secondary': '#fca5a5', '--accent-color': '#f97316', '--accent-hover': '#ea580c', '--success-color': '#fbbf24', '--error-color': '#ef4444', '--border-color': 'rgba(249,115,22,0.12)' },
        arctic:    { '--bg-color': '#0e1628', '--panel-bg': 'rgba(15,30,55,0.7)',  '--text-primary': '#f0f9ff', '--text-secondary': '#7dd3fc', '--accent-color': '#0ea5e9', '--accent-hover': '#0284c7', '--success-color': '#2dd4bf', '--error-color': '#f87171', '--border-color': 'rgba(14,165,233,0.12)' },
        rose:      { '--bg-color': '#1a0a1a', '--panel-bg': 'rgba(40,15,40,0.7)',  '--text-primary': '#fdf2f8', '--text-secondary': '#f9a8d4', '--accent-color': '#ec4899', '--accent-hover': '#db2777', '--success-color': '#a78bfa', '--error-color': '#fb7185', '--border-color': 'rgba(236,72,153,0.12)' },
        sandstorm: { '--bg-color': '#1a1510', '--panel-bg': 'rgba(40,32,20,0.7)',  '--text-primary': '#fefce8', '--text-secondary': '#fcd34d', '--accent-color': '#eab308', '--accent-hover': '#ca8a04', '--success-color': '#a3e635', '--error-color': '#f87171', '--border-color': 'rgba(234,179,8,0.12)' },
        monochrome:{ '--bg-color': '#111111', '--panel-bg': 'rgba(30,30,30,0.75)', '--text-primary': '#e5e5e5', '--text-secondary': '#a3a3a3', '--accent-color': '#d4d4d4', '--accent-hover': '#a3a3a3', '--success-color': '#86efac', '--error-color': '#fca5a5', '--border-color': 'rgba(163,163,163,0.12)' }
    };

    // SVG wallpapers encoded as CSS background values
    const WALLPAPERS = {
        none: 'none',
        grid: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Cpath d='M60 0H0v60' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3C/svg%3E\")",
        dots: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Ccircle cx='20' cy='20' r='1' fill='%23ffffff' fill-opacity='0.05'/%3E%3C/svg%3E\")",
        hexagons: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50V16L28 0l28 16v34L28 66zm0 34L0 84V50l28-16 28 16v34L28 100z' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.5'/%3E%3C/svg%3E\")",
        circuit: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Cpath d='M0 40h20m20 0h20M40 0v20m0 20v20' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Ccircle cx='40' cy='40' r='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='0' cy='40' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='40' cy='0' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3C/svg%3E\")",
        topography: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='600'%3E%3Cpath d='M120 300c60-80 180-80 240 0s180 80 240 0' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='1'/%3E%3Cpath d='M0 200c80-60 160-60 240 0s160 60 240 0 160-60 240 0' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='1'/%3E%3Cpath d='M60 450c60-50 120-50 180 0s120 50 180 0 120-50 180 0' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='1'/%3E%3Cpath d='M0 100c100-40 200 40 300 0s200 40 300 0' fill='none' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='1'/%3E%3Cpath d='M0 520c80-30 160 30 240 0s160-30 240 0 80 30 160 0' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='1'/%3E%3C/svg%3E\")",
        diamonds: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Cpath d='M24 4L44 24 24 44 4 24z' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3C/svg%3E\")",
        crosses: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Cpath d='M20 16v8M16 20h8' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6' stroke-linecap='round'/%3E%3C/svg%3E\")",
        waves: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='40' viewBox='0 0 120 40'%3E%3Cpath d='M0 20c20-15 40-15 60 0s40 15 60 0' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.6'/%3E%3C/svg%3E\")",
        constellation: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Ccircle cx='30' cy='30' r='1' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='170' cy='50' r='1.2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Ccircle cx='100' cy='100' r='1' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='50' cy='160' r='1.3' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='150' cy='170' r='0.8' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='80' cy='40' r='0.6' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='180' cy='120' r='0.7' fill='%23ffffff' fill-opacity='0.05'/%3E%3Cline x1='30' y1='30' x2='100' y2='100' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='100' y1='100' x2='170' y2='50' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='100' y1='100' x2='50' y2='160' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='150' y1='170' x2='180' y2='120' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3C/svg%3E\")",
        triangles: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='56'%3E%3Cpath d='M32 0L64 56H0z' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3C/svg%3E\")"
    };

    const WALLPAPER_LABELS = {
        none: 'None',
        grid: 'Grid',
        dots: 'Dots',
        hexagons: 'Hexagons',
        circuit: 'Circuit',
        topography: 'Topography',
        diamonds: 'Diamonds',
        crosses: 'Crosses',
        waves: 'Waves',
        constellation: 'Constellation',
        triangles: 'Triangles'
    };

    const PALETTE_LABELS = {
        default: 'Default',
        midnight: 'Midnight',
        emerald: 'Emerald',
        sunset: 'Sunset',
        arctic: 'Arctic',
        rose: 'Rosé',
        sandstorm: 'Sandstorm',
        monochrome: 'Mono'
    };

    function applyPalette(name) {
        const vars = PALETTES[name] || PALETTES.default;
        const root = document.documentElement;
        for (const [prop, val] of Object.entries(vars)) {
            root.style.setProperty(prop, val);
        }
    }

    function applyWallpaper(name) {
        const bg = WALLPAPERS[name] || WALLPAPERS.none;
        document.body.style.backgroundImage = bg === 'none' ? 'none' : bg;
        document.body.style.backgroundRepeat = 'repeat';
        document.body.style.backgroundSize = name === 'topography' ? '600px 600px' : 'auto';
    }

    function applyTheme(theme) {
        applyPalette(theme.palette || 'default');
        applyWallpaper(theme.wallpaper || 'none');
    }

    // Try to apply cached theme instantly (avoid flash)
    try {
        const cached = JSON.parse(localStorage.getItem('geo_ip_theme') || '{}');
        if (cached.palette || cached.wallpaper) applyTheme(cached);
    } catch (e) { /* ignore */ }

    // Fetch live theme from server and apply
    fetch('/api/theme').then(r => r.json()).then(theme => {
        applyTheme(theme);
        localStorage.setItem('geo_ip_theme', JSON.stringify(theme));
    }).catch(() => {});

    // Expose for config.js
    window.__THEME_ENGINE = { PALETTES, WALLPAPERS, WALLPAPER_LABELS, PALETTE_LABELS, applyTheme };
})();
