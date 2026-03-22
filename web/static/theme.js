/**
 * Theme engine — applies palette + wallpaper from /api/theme on every page.
 * Loaded before page-specific scripts so the theme is painted immediately.
 */
(function () {
    const PALETTES = {
        default:    { '--bg-color': '#0f172a', '--panel-bg': 'rgba(30,41,59,0.7)',  '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--accent-color': '#3b82f6', '--accent-hover': '#2563eb', '--success-color': '#10b981', '--error-color': '#ef4444', '--border-color': 'rgba(148,163,184,0.1)' },
        midnight:   { '--bg-color': '#0a0e1a', '--panel-bg': 'rgba(16,20,40,0.75)', '--text-primary': '#e2e8f0', '--text-secondary': '#7c8db5', '--accent-color': '#6366f1', '--accent-hover': '#4f46e5', '--success-color': '#22d3ee', '--error-color': '#f43f5e', '--border-color': 'rgba(99,102,241,0.12)' },
        emerald:    { '--bg-color': '#0c1a14', '--panel-bg': 'rgba(16,40,30,0.7)',  '--text-primary': '#ecfdf5', '--text-secondary': '#6ee7b7', '--accent-color': '#10b981', '--accent-hover': '#059669', '--success-color': '#34d399', '--error-color': '#fb7185', '--border-color': 'rgba(16,185,129,0.12)' },
        sunset:     { '--bg-color': '#1a0e0e', '--panel-bg': 'rgba(40,20,20,0.7)',  '--text-primary': '#fef2f2', '--text-secondary': '#fca5a5', '--accent-color': '#f97316', '--accent-hover': '#ea580c', '--success-color': '#fbbf24', '--error-color': '#ef4444', '--border-color': 'rgba(249,115,22,0.12)' },
        arctic:     { '--bg-color': '#0e1628', '--panel-bg': 'rgba(15,30,55,0.7)',  '--text-primary': '#f0f9ff', '--text-secondary': '#7dd3fc', '--accent-color': '#0ea5e9', '--accent-hover': '#0284c7', '--success-color': '#2dd4bf', '--error-color': '#f87171', '--border-color': 'rgba(14,165,233,0.12)' },
        rose:       { '--bg-color': '#1a0a1a', '--panel-bg': 'rgba(40,15,40,0.7)',  '--text-primary': '#fdf2f8', '--text-secondary': '#f9a8d4', '--accent-color': '#ec4899', '--accent-hover': '#db2777', '--success-color': '#a78bfa', '--error-color': '#fb7185', '--border-color': 'rgba(236,72,153,0.12)' },
        sandstorm:  { '--bg-color': '#1a1510', '--panel-bg': 'rgba(40,32,20,0.7)',  '--text-primary': '#fefce8', '--text-secondary': '#fcd34d', '--accent-color': '#eab308', '--accent-hover': '#ca8a04', '--success-color': '#a3e635', '--error-color': '#f87171', '--border-color': 'rgba(234,179,8,0.12)' },
        carbon:     { '--bg-color': '#141414', '--panel-bg': 'rgba(28,28,28,0.8)',  '--text-primary': '#e0e0e0', '--text-secondary': '#888888', '--accent-color': '#0891b2', '--accent-hover': '#0e7490', '--success-color': '#22d3ee', '--error-color': '#f87171', '--border-color': 'rgba(136,136,136,0.12)' },
        pihole:     { '--bg-color': '#1e1e2e', '--panel-bg': 'rgba(30,30,46,0.85)', '--text-primary': '#cdd6f4', '--text-secondary': '#7f849c', '--accent-color': '#89b4fa', '--accent-hover': '#74c7ec', '--success-color': '#a6e3a1', '--error-color': '#f38ba8', '--border-color': 'rgba(137,180,250,0.1)' },
        backstage:  { '--bg-color': '#1b2028', '--panel-bg': 'rgba(32,38,48,0.85)', '--text-primary': '#d5d6db', '--text-secondary': '#8b9ab5', '--accent-color': '#9bf0e1', '--accent-hover': '#6ce6d2', '--success-color': '#9bf0e1', '--error-color': '#f77c7c', '--border-color': 'rgba(155,240,225,0.1)' },
        dracula:    { '--bg-color': '#282a36', '--panel-bg': 'rgba(40,42,54,0.85)', '--text-primary': '#f8f8f2', '--text-secondary': '#6272a4', '--accent-color': '#bd93f9', '--accent-hover': '#a578e6', '--success-color': '#50fa7b', '--error-color': '#ff5555', '--border-color': 'rgba(189,147,249,0.1)' },
        nord:       { '--bg-color': '#2e3440', '--panel-bg': 'rgba(46,52,64,0.85)', '--text-primary': '#eceff4', '--text-secondary': '#81a1c1', '--accent-color': '#88c0d0', '--accent-hover': '#5e81ac', '--success-color': '#a3be8c', '--error-color': '#bf616a', '--border-color': 'rgba(136,192,208,0.1)' }
    };

    // SVG wallpapers encoded as CSS background values
    const WALLPAPERS = {
        none: 'none',
        grid: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Cpath d='M60 0H0v60' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3C/svg%3E\")",
        dots: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Ccircle cx='20' cy='20' r='1' fill='%23ffffff' fill-opacity='0.05'/%3E%3C/svg%3E\")",
        hexagons: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50V16L28 0l28 16v34L28 66zm0 34L0 84V50l28-16 28 16v34L28 100z' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.5'/%3E%3C/svg%3E\")",
        circuit_board: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cpath d='M0 80h30m10 0h30m10 0h30M80 0v30m0 10v30m0 10v30M40 40h20v20H40zM100 40h20v20h-20zM40 100h20v20H40zM100 100h20v20h-20z' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Ccircle cx='40' cy='40' r='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='120' cy='40' r='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='40' cy='120' r='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='120' cy='120' r='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='80' cy='80' r='3' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.5'/%3E%3Cpath d='M30 80h10m50 0h10M80 30v10m0 50v10' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3C/svg%3E\")",
        network: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Ccircle cx='40' cy='40' r='4' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6'/%3E%3Ccircle cx='200' cy='40' r='4' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6'/%3E%3Ccircle cx='120' cy='120' r='6' fill='none' stroke='%23ffffff' stroke-opacity='0.05' stroke-width='0.6'/%3E%3Ccircle cx='40' cy='200' r='4' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6'/%3E%3Ccircle cx='200' cy='200' r='4' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6'/%3E%3Cline x1='40' y1='40' x2='120' y2='120' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='200' y1='40' x2='120' y2='120' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='40' y1='200' x2='120' y2='120' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='200' y1='200' x2='120' y2='120' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='40' y1='40' x2='200' y2='40' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3' stroke-dasharray='4 6'/%3E%3Cline x1='40' y1='200' x2='200' y2='200' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3' stroke-dasharray='4 6'/%3E%3Ccircle cx='120' cy='120' r='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3C/svg%3E\")",
        globe: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cellipse cx='150' cy='150' rx='120' ry='120' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.6'/%3E%3Cellipse cx='150' cy='150' rx='60' ry='120' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Cellipse cx='150' cy='150' rx='120' ry='60' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Cpath d='M30 150h240' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cpath d='M150 30v240' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cellipse cx='150' cy='150' rx='95' ry='120' fill='none' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.4'/%3E%3Cpath d='M30 100h240M30 200h240' fill='none' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3C/svg%3E\")",
        radar: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Ccircle cx='100' cy='100' r='30' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.5'/%3E%3Ccircle cx='100' cy='100' r='60' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Ccircle cx='100' cy='100' r='90' fill='none' stroke='%23ffffff' stroke-opacity='0.018' stroke-width='0.5'/%3E%3Cline x1='100' y1='10' x2='100' y2='190' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.3'/%3E%3Cline x1='10' y1='100' x2='190' y2='100' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.3'/%3E%3Cline x1='37' y1='37' x2='163' y2='163' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3Cline x1='163' y1='37' x2='37' y2='163' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3Ccircle cx='100' cy='100' r='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3C/svg%3E\")",
        city_lights: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='200'%3E%3Crect x='20' y='80' width='8' height='120' fill='%23ffffff' fill-opacity='0.012'/%3E%3Crect x='22' y='85' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='25' y='92' width='2' height='2' fill='%23ffffff' fill-opacity='0.03'/%3E%3Crect x='22' y='100' width='2' height='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Crect x='60' y='50' width='12' height='150' fill='%23ffffff' fill-opacity='0.015'/%3E%3Crect x='63' y='55' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='67' y='65' width='2' height='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Crect x='63' y='80' width='2' height='2' fill='%23ffffff' fill-opacity='0.03'/%3E%3Crect x='67' y='95' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='110' y='60' width='10' height='140' fill='%23ffffff' fill-opacity='0.012'/%3E%3Crect x='113' y='68' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='116' y='82' width='2' height='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Crect x='160' y='90' width='8' height='110' fill='%23ffffff' fill-opacity='0.012'/%3E%3Crect x='163' y='96' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='200' y='40' width='14' height='160' fill='%23ffffff' fill-opacity='0.015'/%3E%3Crect x='203' y='48' width='2' height='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Crect x='207' y='60' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3Crect x='203' y='78' width='2' height='2' fill='%23ffffff' fill-opacity='0.03'/%3E%3Crect x='210' y='90' width='2' height='2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Crect x='255' y='70' width='10' height='130' fill='%23ffffff' fill-opacity='0.012'/%3E%3Crect x='258' y='78' width='2' height='2' fill='%23ffffff' fill-opacity='0.04'/%3E%3C/svg%3E\")",
        data_flow: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='200'%3E%3Cpath d='M20 0v50l30 20v50l-30 20v60' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.5'/%3E%3Cpath d='M50 0v30l30 20v80l-30 20v50' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Cpath d='M80 0v70l-30 20v40l30 20v50' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.5'/%3E%3Ccircle cx='20' cy='50' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='50' cy='70' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='80' cy='90' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='50' cy='150' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='20' cy='120' r='1.5' fill='%23ffffff' fill-opacity='0.04'/%3E%3C/svg%3E\")",
        topology: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Crect x='85' y='10' width='30' height='20' rx='3' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Crect x='10' y='85' width='30' height='20' rx='3' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Crect x='160' y='85' width='30' height='20' rx='3' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Crect x='45' y='160' width='30' height='20' rx='3' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Crect x='125' y='160' width='30' height='20' rx='3' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3Cline x1='100' y1='30' x2='25' y2='85' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='100' y1='30' x2='175' y2='85' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='25' y1='105' x2='60' y2='160' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='175' y1='105' x2='140' y2='160' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.4'/%3E%3Cline x1='60' y1='170' x2='125' y2='170' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.3' stroke-dasharray='3 4'/%3E%3C/svg%3E\")",
        server_rack: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='160'%3E%3Crect x='20' y='10' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Crect x='20' y='32' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Crect x='20' y='54' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Crect x='20' y='76' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Crect x='20' y='98' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Crect x='20' y='120' width='80' height='18' rx='2' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3Ccircle cx='28' cy='19' r='1.5' fill='%2300ff88' fill-opacity='0.05'/%3E%3Ccircle cx='28' cy='41' r='1.5' fill='%2300ff88' fill-opacity='0.04'/%3E%3Ccircle cx='28' cy='63' r='1.5' fill='%2300ff88' fill-opacity='0.05'/%3E%3Ccircle cx='28' cy='85' r='1.5' fill='%23ff6644' fill-opacity='0.04'/%3E%3Ccircle cx='28' cy='107' r='1.5' fill='%2300ff88' fill-opacity='0.05'/%3E%3Ccircle cx='28' cy='129' r='1.5' fill='%2300ff88' fill-opacity='0.04'/%3E%3Cline x1='40' y1='19' x2='90' y2='19' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3Cline x1='40' y1='41' x2='90' y2='41' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3Cline x1='40' y1='63' x2='90' y2='63' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.3'/%3E%3C/svg%3E\")",
        signal_waves: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Ccircle cx='50' cy='180' r='15' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.5'/%3E%3Ccircle cx='50' cy='180' r='35' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Ccircle cx='50' cy='180' r='55' fill='none' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.5'/%3E%3Ccircle cx='50' cy='180' r='75' fill='none' stroke='%23ffffff' stroke-opacity='0.012' stroke-width='0.5'/%3E%3Ccircle cx='180' cy='30' r='12' fill='none' stroke='%23ffffff' stroke-opacity='0.025' stroke-width='0.5'/%3E%3Ccircle cx='180' cy='30' r='28' fill='none' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.5'/%3E%3Ccircle cx='180' cy='30' r='44' fill='none' stroke='%23ffffff' stroke-opacity='0.015' stroke-width='0.5'/%3E%3Ccircle cx='50' cy='180' r='3' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='180' cy='30' r='3' fill='%23ffffff' fill-opacity='0.04'/%3E%3C/svg%3E\")",
        matrix: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='120'%3E%3Ctext x='10' y='15' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.03'%3E01%3C/text%3E%3Ctext x='40' y='35' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.025'%3E10%3C/text%3E%3Ctext x='15' y='55' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.035'%3E11%3C/text%3E%3Ctext x='55' y='70' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.02'%3E00%3C/text%3E%3Ctext x='25' y='90' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.03'%3E10%3C/text%3E%3Ctext x='60' y='110' font-family='monospace' font-size='10' fill='%2300ff88' fill-opacity='0.025'%3E01%3C/text%3E%3C/svg%3E\")",
        constellation: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Ccircle cx='30' cy='30' r='1' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='170' cy='50' r='1.2' fill='%23ffffff' fill-opacity='0.05'/%3E%3Ccircle cx='100' cy='100' r='1' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='50' cy='160' r='1.3' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='150' cy='170' r='0.8' fill='%23ffffff' fill-opacity='0.06'/%3E%3Ccircle cx='80' cy='40' r='0.6' fill='%23ffffff' fill-opacity='0.04'/%3E%3Ccircle cx='180' cy='120' r='0.7' fill='%23ffffff' fill-opacity='0.05'/%3E%3Cline x1='30' y1='30' x2='100' y2='100' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='100' y1='100' x2='170' y2='50' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='100' y1='100' x2='50' y2='160' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3Cline x1='150' y1='170' x2='180' y2='120' stroke='%23ffffff' stroke-opacity='0.02' stroke-width='0.4'/%3E%3C/svg%3E\")",
        diamonds: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Cpath d='M24 4L44 24 24 44 4 24z' fill='none' stroke='%23ffffff' stroke-opacity='0.035' stroke-width='0.5'/%3E%3C/svg%3E\")",
        crosses: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Cpath d='M20 16v8M16 20h8' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='0.6' stroke-linecap='round'/%3E%3C/svg%3E\")",
        waves: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='40' viewBox='0 0 120 40'%3E%3Cpath d='M0 20c20-15 40-15 60 0s40 15 60 0' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.6'/%3E%3C/svg%3E\")",
        triangles: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='56'%3E%3Cpath d='M32 0L64 56H0z' fill='none' stroke='%23ffffff' stroke-opacity='0.03' stroke-width='0.5'/%3E%3C/svg%3E\")"
    };

    const WALLPAPER_LABELS = {
        none: 'None',
        grid: 'Grid',
        dots: 'Dots',
        hexagons: 'Hexagons',
        circuit_board: 'Circuit Board',
        network: 'Network',
        globe: 'Globe',
        radar: 'Radar',
        city_lights: 'City Lights',
        data_flow: 'Data Flow',
        topology: 'Topology',
        server_rack: 'Server Rack',
        signal_waves: 'Signal Waves',
        matrix: 'Matrix',
        constellation: 'Constellation',
        diamonds: 'Diamonds',
        crosses: 'Crosses',
        waves: 'Waves',
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
        carbon: 'Carbon',
        pihole: 'Pi-hole',
        backstage: 'Backstage',
        dracula: 'Dracula',
        nord: 'Nord'
    };

    const LARGE_WALLPAPERS = new Set(['globe', 'city_lights', 'network', 'signal_waves']);

    function applyPalette(name) {
        const vars = PALETTES[name] || PALETTES.default;
        const root = document.documentElement;
        for (const [prop, val] of Object.entries(vars)) {
            root.style.setProperty(prop, val);
        }
    }

    function applyWallpaper(name) {
        if (name === 'custom') {
            document.body.style.backgroundImage = 'url(/api/wallpaper/custom)';
            document.body.style.backgroundRepeat = 'repeat';
            document.body.style.backgroundSize = 'auto';
            return;
        }
        const bg = WALLPAPERS[name] || WALLPAPERS.none;
        document.body.style.backgroundImage = bg === 'none' ? 'none' : bg;
        document.body.style.backgroundRepeat = 'repeat';
        document.body.style.backgroundSize = LARGE_WALLPAPERS.has(name) ? '300px 300px' : 'auto';
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
