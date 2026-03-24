/**
 * Animated (video) wallpapers — canvas-based backgrounds.
 * Loaded after theme.js. Exposes window.__VIDEO_WALLPAPERS.
 * Each renderer is a FACTORY returning { init(), draw() } with isolated state.
 */
(function () {
    let activeCanvas = null;
    let activeRAF = null;
    let activeType = null;
    let activeRenderer = null;
    let lastFrame = 0;

    const FPS = 24;
    const FRAME_MS = 1000 / FPS;

    /* ── helpers ── */
    function ensureCanvas() {
        if (activeCanvas) return activeCanvas;
        const c = document.createElement('canvas');
        c.id = 'videoBgCanvas';
        c.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none;opacity:0;transition:opacity 0.8s;';
        document.body.prepend(c);
        activeCanvas = c;
        resize();
        return c;
    }

    function resize() {
        if (!activeCanvas) return;
        activeCanvas.width = window.innerWidth;
        activeCanvas.height = window.innerHeight;
    }
    window.addEventListener('resize', () => {
        resize();
        if (activeRenderer) activeRenderer.init(activeCanvas, activeCanvas.getContext('2d'));
    });

    /* ══════════════════════════════════════
       RENDERER FACTORIES — each returns { init, draw }
       ══════════════════════════════════════ */
    const FACTORIES = {};

    /* ── 1. Matrix Rain ── */
    FACTORIES.video_matrix = () => {
        let drops = [];
        const chars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF';
        const SZ = 14;
        return {
            init(c) {
                const cols = Math.floor(c.width / SZ);
                drops = new Array(cols);
                for (let i = 0; i < cols; i++) drops[i] = Math.random() * -50 | 0;
            },
            draw(c, ctx) {
                ctx.fillStyle = 'rgba(0,0,0,0.06)';
                ctx.fillRect(0, 0, c.width, c.height);
                ctx.font = SZ + 'px monospace';
                for (let x = 0; x < drops.length; x++) {
                    const ch = chars[Math.random() * chars.length | 0];
                    const b = Math.random();
                    ctx.fillStyle = b > 0.92 ? 'rgba(180,255,180,0.85)' : 'rgba(0,' + (130 + b * 125 | 0) + ',60,' + (0.3 + b * 0.4).toFixed(2) + ')';
                    ctx.fillText(ch, x * SZ, drops[x] * SZ);
                    if (drops[x] * SZ > c.height && Math.random() > 0.975) drops[x] = 0;
                    drops[x]++;
                }
            }
        };
    };

    /* ── 2. Starfield ── */
    FACTORIES.video_starfield = () => {
        let stars = [];
        const COUNT = 400;
        function resetStar(s, w, h) {
            s.x = (Math.random() - 0.5) * w * 2;
            s.y = (Math.random() - 0.5) * h * 2;
            s.z = Math.random() * w;
        }
        return {
            init(c) {
                stars = [];
                for (let i = 0; i < COUNT; i++) {
                    const s = {};
                    resetStar(s, c.width, c.height);
                    stars.push(s);
                }
            },
            draw(c, ctx) {
                ctx.fillStyle = 'rgba(0,0,0,0.15)';
                ctx.fillRect(0, 0, c.width, c.height);
                const cx = c.width / 2, cy = c.height / 2;
                for (const s of stars) {
                    s.z -= 3;
                    if (s.z <= 0) { resetStar(s, c.width, c.height); s.z = c.width; }
                    const sx = (s.x / s.z) * 200 + cx;
                    const sy = (s.y / s.z) * 200 + cy;
                    const r = Math.max(0.3, (1 - s.z / c.width) * 2.5);
                    const a = (1 - s.z / c.width).toFixed(2);
                    ctx.beginPath();
                    ctx.arc(sx, sy, r, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(200,220,255,' + a + ')';
                    ctx.fill();
                }
            }
        };
    };

    /* ── 3. Particles Network ── */
    FACTORIES.video_particles = () => {
        let pts = [];
        const COUNT = 80;
        const LINK = 150;
        return {
            init(c) {
                pts = [];
                for (let i = 0; i < COUNT; i++) {
                    pts.push({
                        x: Math.random() * c.width,
                        y: Math.random() * c.height,
                        vx: (Math.random() - 0.5) * 0.5,
                        vy: (Math.random() - 0.5) * 0.5,
                        r: Math.random() * 1.5 + 0.5
                    });
                }
            },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                for (const p of pts) {
                    p.x += p.vx; p.y += p.vy;
                    if (p.x < 0 || p.x > c.width) p.vx *= -1;
                    if (p.y < 0 || p.y > c.height) p.vy *= -1;
                }
                ctx.strokeStyle = 'rgba(59,130,246,0.12)';
                ctx.lineWidth = 0.5;
                for (let i = 0; i < pts.length; i++) {
                    for (let j = i + 1; j < pts.length; j++) {
                        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
                        const d = dx * dx + dy * dy;
                        if (d < LINK * LINK) {
                            ctx.globalAlpha = 1 - Math.sqrt(d) / LINK;
                            ctx.beginPath();
                            ctx.moveTo(pts[i].x, pts[i].y);
                            ctx.lineTo(pts[j].x, pts[j].y);
                            ctx.stroke();
                        }
                    }
                }
                ctx.globalAlpha = 1;
                for (const p of pts) {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(59,130,246,0.5)';
                    ctx.fill();
                }
            }
        };
    };

    /* ── 4. Aurora ── */
    FACTORIES.video_aurora = () => {
        let t = 0;
        return {
            init() { t = 0; },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                t += 0.003;
                for (let band = 0; band < 3; band++) {
                    const off = band * 1.2;
                    ctx.beginPath();
                    ctx.moveTo(0, c.height);
                    for (let x = 0; x <= c.width; x += 4) {
                        const y = c.height * 0.45
                            + Math.sin(x * 0.003 + t * 2 + off) * 60
                            + Math.sin(x * 0.007 + t * 1.3 + off) * 40
                            + Math.sin(x * 0.001 + t * 3 + off * 2) * 30;
                        ctx.lineTo(x, y);
                    }
                    ctx.lineTo(c.width, c.height);
                    ctx.closePath();
                    const g = ctx.createLinearGradient(0, c.height * 0.2, 0, c.height);
                    const hue = (band * 60 + t * 20) % 360;
                    g.addColorStop(0, 'hsla(' + hue + ',80%,60%,0.08)');
                    g.addColorStop(0.5, 'hsla(' + ((hue + 40) % 360) + ',70%,50%,0.05)');
                    g.addColorStop(1, 'transparent');
                    ctx.fillStyle = g;
                    ctx.fill();
                }
            }
        };
    };

    /* ── 5. Fireflies ── */
    FACTORIES.video_fireflies = () => {
        let flies = [];
        const COUNT = 50;
        return {
            init(c) {
                flies = [];
                for (let i = 0; i < COUNT; i++) {
                    flies.push({
                        x: Math.random() * c.width,
                        y: Math.random() * c.height,
                        vx: (Math.random() - 0.5) * 0.4,
                        vy: (Math.random() - 0.5) * 0.4,
                        phase: Math.random() * Math.PI * 2,
                        r: Math.random() * 3 + 2,
                        hue: Math.random() * 60 + 90
                    });
                }
            },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                for (const f of flies) {
                    f.x += f.vx; f.y += f.vy;
                    f.phase += 0.015;
                    if (f.x < -20) f.x = c.width + 20;
                    if (f.x > c.width + 20) f.x = -20;
                    if (f.y < -20) f.y = c.height + 20;
                    if (f.y > c.height + 20) f.y = -20;
                    const glow = (Math.sin(f.phase) + 1) * 0.5;
                    const a = 0.15 + glow * 0.5;
                    const g = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r * 4);
                    g.addColorStop(0, 'hsla(' + f.hue + ',100%,70%,' + a.toFixed(2) + ')');
                    g.addColorStop(1, 'transparent');
                    ctx.beginPath();
                    ctx.arc(f.x, f.y, f.r * 4, 0, Math.PI * 2);
                    ctx.fillStyle = g;
                    ctx.fill();
                }
            }
        };
    };

    /* ── 6. Cyber Grid ── */
    FACTORIES.video_cyber_grid = () => {
        let offset = 0;
        return {
            init() { offset = 0; },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                offset = (offset + 0.3) % 40;
                const horizon = c.height * 0.55;
                ctx.strokeStyle = 'rgba(59,130,246,0.15)';
                ctx.lineWidth = 0.5;
                for (let i = 0; i < 20; i++) {
                    const rawY = i * 40 + offset;
                    const t = rawY / (20 * 40);
                    const y = horizon + Math.pow(t, 1.5) * (c.height - horizon) * 1.2;
                    if (y > c.height) continue;
                    const a = (0.05 + t * 0.2).toFixed(2);
                    ctx.strokeStyle = 'rgba(59,130,246,' + a + ')';
                    ctx.beginPath();
                    ctx.moveTo(0, y);
                    ctx.lineTo(c.width, y);
                    ctx.stroke();
                }
                const vanishX = c.width / 2;
                const count = 24;
                for (let i = -count / 2; i <= count / 2; i++) {
                    const x = vanishX + i * (c.width / count);
                    ctx.strokeStyle = 'rgba(59,130,246,0.08)';
                    ctx.beginPath();
                    ctx.moveTo(vanishX, horizon);
                    ctx.lineTo(x + (x - vanishX) * 0.5, c.height);
                    ctx.stroke();
                }
                const g = ctx.createLinearGradient(0, horizon - 2, 0, horizon + 8);
                g.addColorStop(0, 'transparent');
                g.addColorStop(0.5, 'rgba(59,130,246,0.15)');
                g.addColorStop(1, 'transparent');
                ctx.fillStyle = g;
                ctx.fillRect(0, horizon - 2, c.width, 10);
            }
        };
    };

    /* ── 7. Plexus Vortex (funnel) ── */
    FACTORIES.video_plexus_vortex = () => {
        let nodes = [], t = 0;
        const N = 120;
        return {
            init(c) {
                nodes = [];
                for (let i = 0; i < N; i++) {
                    const angle = Math.random() * Math.PI * 2;
                    const radius = Math.random() * 0.45 + 0.05;
                    nodes.push({ angle, radius, speed: 0.003 + Math.random() * 0.008, drift: (Math.random() - 0.5) * 0.0003, z: Math.random() });
                }
                t = 0;
            },
            draw(c, ctx) {
                ctx.fillStyle = 'rgba(0,0,0,0.08)';
                ctx.fillRect(0, 0, c.width, c.height);
                t += 0.01;
                const cx = c.width / 2, cy = c.height / 2;
                const maxR = Math.min(c.width, c.height) * 0.48;
                // update nodes
                for (const n of nodes) {
                    n.angle += n.speed;
                    n.radius -= 0.0004;
                    n.z += 0.003;
                    if (n.radius < 0.02 || n.z > 1) { n.radius = 0.4 + Math.random() * 0.1; n.z = 0; n.angle = Math.random() * Math.PI * 2; }
                }
                // positions
                const pos = nodes.map(n => {
                    const r = n.radius * maxR * (0.5 + n.z * 0.5);
                    return { x: cx + Math.cos(n.angle) * r, y: cy + Math.sin(n.angle) * r * 0.6, z: n.z };
                });
                // connections
                ctx.lineWidth = 0.4;
                for (let i = 0; i < pos.length; i++) {
                    for (let j = i + 1; j < pos.length; j++) {
                        const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
                        const d = Math.sqrt(dx * dx + dy * dy);
                        if (d < 100) {
                            const a = ((1 - d / 100) * 0.25 * (pos[i].z + pos[j].z) / 2).toFixed(3);
                            ctx.strokeStyle = 'rgba(100,180,255,' + a + ')';
                            ctx.beginPath(); ctx.moveTo(pos[i].x, pos[i].y); ctx.lineTo(pos[j].x, pos[j].y); ctx.stroke();
                        }
                    }
                }
                // nodes
                for (const p of pos) {
                    const sz = 1 + p.z * 2;
                    const a = (0.3 + p.z * 0.6).toFixed(2);
                    ctx.beginPath(); ctx.arc(p.x, p.y, sz, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(120,200,255,' + a + ')';
                    ctx.fill();
                }
            }
        };
    };

    /* ── 8. Data Stream (high-tech flowing nodes) ── */
    FACTORIES.video_data_stream = () => {
        let particles = [];
        const N = 100, LINK = 120;
        return {
            init(c) {
                particles = [];
                for (let i = 0; i < N; i++) {
                    particles.push({
                        x: Math.random() * c.width, y: Math.random() * c.height,
                        vx: (Math.random() * 0.8 + 0.2) * (Math.random() < 0.5 ? -1 : 1),
                        vy: (Math.random() - 0.5) * 0.3,
                        r: Math.random() * 1.5 + 0.5,
                        pulse: Math.random() * Math.PI * 2
                    });
                }
            },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                for (const p of particles) {
                    p.x += p.vx; p.y += p.vy; p.pulse += 0.02;
                    if (p.x < -20) p.x = c.width + 20;
                    if (p.x > c.width + 20) p.x = -20;
                    if (p.y < 0 || p.y > c.height) p.vy *= -1;
                }
                // connections with gradient
                ctx.lineWidth = 0.5;
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x, dy = particles[i].y - particles[j].y;
                        const d = dx * dx + dy * dy;
                        if (d < LINK * LINK) {
                            const dist = Math.sqrt(d);
                            const a = (1 - dist / LINK) * 0.3;
                            const g = ctx.createLinearGradient(particles[i].x, particles[i].y, particles[j].x, particles[j].y);
                            g.addColorStop(0, 'rgba(0,200,255,' + a.toFixed(3) + ')');
                            g.addColorStop(1, 'rgba(120,80,255,' + a.toFixed(3) + ')');
                            ctx.strokeStyle = g;
                            ctx.beginPath(); ctx.moveTo(particles[i].x, particles[i].y); ctx.lineTo(particles[j].x, particles[j].y); ctx.stroke();
                        }
                    }
                }
                // glowing nodes
                for (const p of particles) {
                    const glow = (Math.sin(p.pulse) + 1) * 0.5;
                    const sz = p.r + glow * 1.5;
                    const gr = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, sz * 3);
                    gr.addColorStop(0, 'rgba(0,200,255,' + (0.4 + glow * 0.4).toFixed(2) + ')');
                    gr.addColorStop(1, 'transparent');
                    ctx.beginPath(); ctx.arc(p.x, p.y, sz * 3, 0, Math.PI * 2);
                    ctx.fillStyle = gr; ctx.fill();
                    ctx.beginPath(); ctx.arc(p.x, p.y, sz * 0.5, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(200,240,255,' + (0.6 + glow * 0.4).toFixed(2) + ')';
                    ctx.fill();
                }
            }
        };
    };

    /* ── 9. Plexus Web (3D rotating sphere) ── */
    FACTORIES.video_plexus_web = () => {
        let nodes3d = [], t = 0;
        const N = 90, LINK = 0.6;
        return {
            init() {
                nodes3d = [];
                for (let i = 0; i < N; i++) {
                    const theta = Math.acos(2 * Math.random() - 1);
                    const phi = Math.random() * Math.PI * 2;
                    nodes3d.push({ theta, phi, r: 0.8 + Math.random() * 0.2 });
                }
                t = 0;
            },
            draw(c, ctx) {
                ctx.clearRect(0, 0, c.width, c.height);
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, c.width, c.height);
                t += 0.004;
                const cx = c.width / 2, cy = c.height / 2;
                const scale = Math.min(c.width, c.height) * 0.35;
                // project 3D -> 2D with rotation
                const proj = nodes3d.map(n => {
                    const th = n.theta, ph = n.phi + t;
                    const x3 = n.r * Math.sin(th) * Math.cos(ph);
                    const y3 = n.r * Math.sin(th) * Math.sin(ph);
                    const z3 = n.r * Math.cos(th);
                    // rotate around Y
                    const rx = x3 * Math.cos(t * 0.7) - z3 * Math.sin(t * 0.7);
                    const rz = x3 * Math.sin(t * 0.7) + z3 * Math.cos(t * 0.7);
                    const depth = 1 / (2 - rz);
                    return { x: cx + rx * scale * depth, y: cy + y3 * scale * depth, z: rz, depth };
                });
                // connections
                ctx.lineWidth = 0.4;
                for (let i = 0; i < proj.length; i++) {
                    for (let j = i + 1; j < proj.length; j++) {
                        const dth = nodes3d[i].theta - nodes3d[j].theta;
                        const dph = nodes3d[i].phi - nodes3d[j].phi;
                        if (Math.abs(dth) + Math.abs(dph) < LINK) {
                            const a = ((proj[i].depth + proj[j].depth) * 0.12).toFixed(3);
                            ctx.strokeStyle = 'rgba(160,120,255,' + a + ')';
                            ctx.beginPath(); ctx.moveTo(proj[i].x, proj[i].y); ctx.lineTo(proj[j].x, proj[j].y); ctx.stroke();
                        }
                    }
                }
                // nodes
                for (const p of proj) {
                    const sz = p.depth * 2.5;
                    const a = (p.depth * 0.5).toFixed(2);
                    ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(0.5, sz), 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(180,140,255,' + a + ')';
                    ctx.fill();
                }
            }
        };
    };

    /* ══════════════════════════════════════
       PUBLIC API
       ══════════════════════════════════════ */
    const LABELS = {
        video_matrix:        'Matrix Rain',
        video_starfield:     'Starfield',
        video_particles:     'Particle Network',
        video_aurora:        'Aurora Waves',
        video_fireflies:     'Fireflies',
        video_cyber_grid:    'Cyber Grid',
        video_plexus_vortex: 'Plexus Vortex',
        video_data_stream:   'Data Stream',
        video_plexus_web:    'Plexus Web'
    };

    /* ── Custom video (MP4) playback ── */
    let customVideo = null;

    function startCustomVideo() {
        stopCustomVideo();
        stop(); // stop any canvas renderer
        const v = document.createElement('video');
        v.id = 'videoBgVideo';
        v.src = '/api/wallpaper/video?' + Date.now();
        v.autoplay = true;
        v.loop = true;
        v.muted = true;
        v.playsInline = true;
        v.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1;pointer-events:none;opacity:0;transition:opacity 0.8s;';
        document.body.prepend(v);
        v.play().catch(() => {});
        requestAnimationFrame(() => { v.style.opacity = '1'; });
        customVideo = v;
    }

    function stopCustomVideo() {
        if (customVideo) {
            customVideo.style.opacity = '0';
            const el = customVideo;
            customVideo = null;
            setTimeout(() => { el.pause(); el.remove(); }, 900);
        }
    }

    function start(type) {
        if (activeType === type) return;
        stop();
        stopCustomVideo();
        if (type === 'video_custom') {
            activeType = type;
            startCustomVideo();
            return;
        }
        if (!FACTORIES[type]) return;
        activeType = type;
        activeRenderer = FACTORIES[type]();
        const c = ensureCanvas();
        const ctx = c.getContext('2d');
        activeRenderer.init(c, ctx);
        requestAnimationFrame(() => { c.style.opacity = '1'; });
        function loop(now) {
            activeRAF = requestAnimationFrame(loop);
            if (now - lastFrame < FRAME_MS) return;
            lastFrame = now;
            activeRenderer.draw(c, ctx);
        }
        activeRAF = requestAnimationFrame(loop);
    }

    function stop() {
        if (activeRAF) { cancelAnimationFrame(activeRAF); activeRAF = null; }
        if (activeCanvas) { activeCanvas.style.opacity = '0'; }
        stopCustomVideo();
        activeType = null;
        activeRenderer = null;
    }

    /** Render a looping mini preview into a given canvas element */
    function renderPreview(type, canvas) {
        if (!FACTORIES[type]) return;
        const r = FACTORIES[type]();  // isolated instance
        const ctx = canvas.getContext('2d');
        r.init(canvas, ctx);
        let frames = 0;
        const MAX = 200;
        // Run faster for previews so movement is visible at small size
        function tick() {
            if (frames >= MAX) return;
            // Draw multiple steps per rAF tick for visible motion
            for (let i = 0; i < 3; i++) {
                r.draw(canvas, ctx);
                frames++;
                if (frames >= MAX) break;
            }
            requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    window.__VIDEO_WALLPAPERS = {
        FACTORIES,
        LABELS,
        start,
        stop,
        startCustomVideo,
        stopCustomVideo,
        renderPreview,
        isVideo(name) { return name && name.startsWith('video_'); }
    };

    // Pick up deferred wallpaper if theme.js applied before we loaded
    if (window.__PENDING_VIDEO_WALLPAPER) {
        start(window.__PENDING_VIDEO_WALLPAPER);
        delete window.__PENDING_VIDEO_WALLPAPER;
    }
})();
