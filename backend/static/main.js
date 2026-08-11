document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();

    // ==========================================================================
    // CURSOR SPOTLIGHT
    // ==========================================================================
    const cursorGlow = document.getElementById('cursorGlow');
    let mouseX = window.innerWidth / 2, mouseY = window.innerHeight / 2;
    let glowX = mouseX, glowY = mouseY;
    document.addEventListener('mousemove', e => { mouseX = e.clientX; mouseY = e.clientY; });
    (function animateCursor() {
        glowX += (mouseX - glowX) * 0.08;
        glowY += (mouseY - glowY) * 0.08;
        if (cursorGlow) { cursorGlow.style.left = glowX + 'px'; cursorGlow.style.top = glowY + 'px'; }
        requestAnimationFrame(animateCursor);
    })();

    // ==========================================================================
    // DOM REFS
    // ==========================================================================
    const urlInput            = document.getElementById('urlInput');
    const scrapeBtn           = document.getElementById('scrapeBtn');
    const loader              = document.getElementById('loader');
    const loaderMsg           = document.getElementById('loaderMsg');
    const resultsSection      = document.getElementById('resultsSection');
    const imageGrid           = document.getElementById('imageGrid');
    const imageCount          = document.getElementById('imageCount');
    const downloadBtn         = document.getElementById('downloadBtn');
    const downloadZipBtn      = document.getElementById('downloadZipBtn');
    const autoscrollToggle    = document.getElementById('autoscrollToggle');
    const filterSelect        = document.getElementById('filterSelect');
    const countBtn            = document.getElementById('countBtn');
    const countPanel          = document.getElementById('countPanel');
    const countTotal          = document.getElementById('countTotal');
    const countMethodBadge    = document.getElementById('countMethodBadge');
    const countBreakdown      = document.getElementById('countBreakdown');
    const countNote           = document.getElementById('countNote');
    const countDismissBtn     = document.getElementById('countDismissBtn');
    const themeToggleBtn      = document.getElementById('themeToggleBtn');
    const selectionBar        = document.getElementById('selectionBar');
    const selectionInfo       = document.getElementById('selectionInfo');
    const selectAllBtn        = document.getElementById('selectAllBtn');
    const clearSelectionBtn   = document.getElementById('clearSelectionBtn');
    const downloadModal       = document.getElementById('downloadModal');
    const downloadModalTitle  = document.getElementById('downloadModalTitle');
    const downloadModalStatus = document.getElementById('downloadModalStatus');
    const progressBarFill     = document.getElementById('progressBarFill');
    const statProgress        = document.getElementById('statProgress');
    const statSpeed           = document.getElementById('statSpeed');
    const statEta             = document.getElementById('statEta');
    const downloadLog         = document.getElementById('downloadLog');
    const cancelDownloadBtn   = document.getElementById('cancelDownloadBtn');
    const lightboxModal       = document.getElementById('lightboxModal');
    const lightboxTitle       = document.getElementById('lightboxTitle');
    const lightboxImg         = document.getElementById('lightboxImg');
    const lightboxSpinner     = document.getElementById('lightboxSpinner');
    const lightboxCloseBtn    = document.getElementById('lightboxCloseBtn');
    const lightboxPrevBtn     = document.getElementById('lightboxPrevBtn');
    const lightboxNextBtn     = document.getElementById('lightboxNextBtn');
    const lightboxDownloadBtn = document.getElementById('lightboxDownloadBtn');
    const lightboxMeta        = document.getElementById('lightboxMeta');
    const lightboxCounter     = document.getElementById('lightboxCounter');
    const settingsToggleBtn   = document.getElementById('settingsToggleBtn');
    const settingsDropdown    = document.getElementById('settingsDropdown');
    const toastContainer      = document.getElementById('toastContainer');

    // ==========================================================================
    // TOAST SYSTEM
    // ==========================================================================
    function showToast(message, type = 'info', duration = 3800) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="toast-dot"></span><span>${message}</span>`;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('toast-out');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, duration);
    }

    // ==========================================================================
    // BACKEND DETECTION — local Python server (http://localhost:5000)
    // Note: On HTTPS Vercel, mixed-content rules block http:// calls,
    //       so localAvailable will always be false there — that's correct.
    // ==========================================================================
    const LOCAL_API = 'http://localhost:5000';
    let localAvailable = false;
    let localCheckTs = 0;
    const LOCAL_CHECK_TTL = 30000; // 30s cache

    async function checkLocalBackend(force = false) {
        const now = Date.now();
        if (!force && (now - localCheckTs) < LOCAL_CHECK_TTL) return;
        localCheckTs = now;
        try {
            const r = await fetch(`${LOCAL_API}/api/health`, { signal: AbortSignal.timeout(1500) });
            localAvailable = r.ok;
        } catch { localAvailable = false; }
        updateStatusBadge();
    }
    checkLocalBackend(true);

    function updateStatusBadge() {
        if (!settingsDropdown) return;
        settingsDropdown.innerHTML = `<div style="font-size:12px;color:var(--text-dim);max-width:260px;">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
                <span style="width:8px;height:8px;border-radius:50%;background:${localAvailable ? '#5efb6e' : '#ff5c5c'};display:inline-block;flex-shrink:0;"></span>
                <strong style="color:var(--text-main);">Local Backend: ${localAvailable ? 'CONNECTED ✅' : 'NOT RUNNING ❌'}</strong>
            </div>
            ${localAvailable
                ? '<span style="color:#5efb6e;">Scraping from your real IP — 1000+ images, no captcha.</span>'
                : `<span style="color:#ff8844;">Start for 1000+ images:<br>
                   <code style="font-size:10px;background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px;display:inline-block;margin-top:4px;">cd backend &amp;&amp; python app.py</code></span>`}
        </div>`;
        lucide.createIcons();
    }

    settingsToggleBtn && settingsToggleBtn.addEventListener('click', e => {
        e.stopPropagation();
        checkLocalBackend(true);
        settingsDropdown.classList.toggle('settings-dropdown--hidden');
    });
    document.addEventListener('click', e => {
        if (settingsDropdown &&
            !settingsDropdown.contains(e.target) &&
            e.target !== settingsToggleBtn &&
            !settingsToggleBtn.contains(e.target)) {
            settingsDropdown.classList.add('settings-dropdown--hidden');
        }
    });

    // ==========================================================================
    // STATE
    // ==========================================================================
    let allImages = [], filteredImages = [], selectedUrls = new Set();
    let currentLightboxIdx = -1, downloadAborted = false;

    // ==========================================================================
    // THEME
    // ==========================================================================
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeUI(savedTheme);

    themeToggleBtn.addEventListener('click', () => {
        const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
        updateThemeUI(next);
    });

    function updateThemeUI(theme) {
        themeToggleBtn.innerHTML = theme === 'light' ? '<i data-lucide="moon"></i>' : '<i data-lucide="sun"></i>';
        lucide.createIcons();
    }

    urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') scrapeBtn.click(); });

    // ==========================================================================
    // EMPTY / ERROR STATE HELPER
    // ==========================================================================
    function renderEmptyState({ icon = 'image-off', title, body, note = '' }) {
        return `<div class="empty-state">
            <div class="empty-state-icon"><i data-lucide="${icon}"></i></div>
            <p class="empty-state-title">${title}</p>
            <p class="empty-state-body">${body}</p>
            ${note ? `<p class="empty-state-note">${note}</p>` : ''}
        </div>`;
    }

    // ==========================================================================
    // VERCEL PROXY SCRAPER — parses Yandex HTML when local backend unavailable
    // ==========================================================================
    async function scrapeViaProxy(url) {
        const images = [];
        const seen = new Set();

        async function proxyFetch(pageUrl) {
            try {
                const r = await fetch(`/api/proxy?url=${encodeURIComponent(pageUrl)}`, {
                    signal: AbortSignal.timeout(20000)
                });
                if (!r.ok) return null;
                const data = await r.json();
                return data.contents || null;
            } catch { return null; }
        }

        function parseImages(html) {
            const results = [];
            // Pattern 1: any image URL in JSON (data-bem, JSON blobs)
            const urlRe = /"url"\s*:\s*"(https?:\/\/[^"]+\.(?:jpg|jpeg|png|webp|gif|avif)[^"]*)"/gi;
            let m;
            while ((m = urlRe.exec(html)) !== null) {
                const u = m[1].replace(/\\/g, '');
                if (!seen.has(u) && !u.includes('yastatic') && !u.includes('favicon')) {
                    seen.add(u);
                    results.push({ url: u, thumb: u, alt: 'Image' });
                }
            }
            // Pattern 2: "orig":{"url":"..."
            const origRe = /"orig"\s*:\s*\{[^}]*"url"\s*:\s*"(https?:\/\/[^"]+)"/gi;
            while ((m = origRe.exec(html)) !== null) {
                const u = m[1].replace(/\\/g, '');
                if (!seen.has(u)) {
                    seen.add(u);
                    results.push({ url: u, thumb: u, alt: 'Image' });
                }
            }
            return results;
        }

        const html = await proxyFetch(url);
        if (html) images.push(...parseImages(html));
        return images;
    }

    // ==========================================================================
    // SCRAPE — dual mode: local backend (fast) OR Vercel proxy (cloud fallback)
    // ==========================================================================
    scrapeBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) {
            urlInput.focus();
            showToast('Please enter a Yandex Images URL', 'error');
            return;
        }

        await checkLocalBackend();

        resultsSection.classList.add('hidden');
        loader.classList.remove('hidden');
        imageGrid.innerHTML = '';
        allImages = []; filteredImages = [];
        selectedUrls.clear();
        updateSelectionUI();
        countPanel.classList.add('hidden');

        const deepMode = autoscrollToggle.checked;

        if (localAvailable) {
            // ── Mode A: Local Python backend (real IP, 1000+ images, fastest)
            loaderMsg.textContent = deepMode
                ? '⚡ Deep scraping via local backend (up to 1000+ images)…'
                : '⚡ Scraping via local backend…';
            try {
                const res = await fetch(`${LOCAL_API}/api/scrape`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, autoscroll: deepMode }),
                    signal: AbortSignal.timeout(300000)
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                allImages = data.images || [];
            } catch (err) {
                // Local backend failed — fall through to cloud proxy
                showToast('Local backend error — trying cloud proxy…', 'info');
                loaderMsg.textContent = '🌐 Scraping via cloud proxy (page 1 only)…';
                allImages = await scrapeViaProxy(url);
            }
        } else {
            // ── Mode B: Vercel serverless proxy (cloud mode, single page)
            loaderMsg.textContent = '🌐 Scraping via cloud proxy…';
            allImages = await scrapeViaProxy(url);
        }

        loader.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        if (!allImages.length) {
            imageGrid.innerHTML = renderEmptyState({
                icon: 'search-x',
                title: 'No Images Found',
                body: `Try a Yandex Images search URL:<br>
                       <code>https://yandex.com/images/search?text=cats</code><br><br>
                       For 1000+ images, run the local backend:<br>
                       <code>cd backend &amp;&amp; python app.py</code>`
            });
            imageCount.textContent = '0 images';
            showToast('No images found', 'info');
        } else {
            filterSelect.value = 'all';
            applyFilter();
            showToast(`Found ${allImages.length} images!`, 'success');
        }
        lucide.createIcons();
    });

    // ==========================================================================
    // COUNT — uses fast /api/count endpoint on local backend
    // ==========================================================================
    function animateCount(el, target) {
        const start = performance.now();
        (function step(now) {
            const t = Math.min((now - start) / 900, 1);
            el.textContent = Math.round(target * (1 - (1 - t) ** 3));
            if (t < 1) requestAnimationFrame(step);
        })(performance.now());
    }

    countBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) { urlInput.focus(); return; }
        countBtn.classList.add('loading');
        countBtn.innerHTML = '<i data-lucide="loader-2"></i><span class="btn-text btn-count-text">Counting…</span>';
        lucide.createIcons();
        countPanel.classList.add('hidden');
        await checkLocalBackend();
        try {
            if (!localAvailable) throw new Error('Local backend not running. Run: cd backend && python app.py');
            const res = await fetch(`${LOCAL_API}/api/count`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
                signal: AbortSignal.timeout(30000)
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            const total = data.count || 0;
            const bd    = data.breakdown || {};
            countPanel.classList.remove('hidden');
            animateCount(countTotal, total);
            countMethodBadge.textContent = '⚡ Local (page 1 only)';
            countBreakdown.innerHTML = Object.entries(bd).map(([k, v]) =>
                `<span class="count-chip"><strong>${v}</strong> ${k.toUpperCase()}</span>`
            ).join('') || '<span class="count-chip">No breakdown</span>';
            countNote.textContent = 'Page 1 only. Enable Deep Scrape to fetch 1000+ images.';
            showToast(`${total} images detected on page 1`, 'success');
        } catch (err) {
            countPanel.classList.remove('hidden');
            countTotal.textContent = '?';
            countMethodBadge.textContent = 'Error';
            countBreakdown.innerHTML = '';
            const msg = (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))
                ? 'Could not reach local backend. Make sure it is running.'
                : err.message;
            countNote.textContent = msg;
            showToast(msg, 'error');
        } finally {
            countBtn.classList.remove('loading');
            countBtn.innerHTML = '<i data-lucide="hash"></i><span class="btn-text btn-count-text">Count</span>';
            lucide.createIcons();
        }
    });
    countDismissBtn.addEventListener('click', () => countPanel.classList.add('hidden'));

    // ==========================================================================
    // FILTER
    // ==========================================================================
    filterSelect.addEventListener('change', applyFilter);
    function applyFilter() {
        const f = filterSelect.value;
        if (f === 'all') {
            filteredImages = [...allImages];
        } else if (f === 'hd') {
            filteredImages = allImages.filter(i => i.isHighRes || Number(i.width) > 1080);
        } else {
            filteredImages = allImages.filter(i => {
                const ext = i.url.split('.').pop().split('?')[0].toLowerCase();
                return f === 'jpg' ? (ext === 'jpg' || ext === 'jpeg') : ext === f;
            });
        }

        imageCount.textContent = `Found ${filteredImages.length} images`;

        // Remove selected URLs no longer in filtered set
        const fSet = new Set(filteredImages.map(i => i.url));
        let removedCount = 0;
        selectedUrls.forEach(u => { if (!fSet.has(u)) { selectedUrls.delete(u); removedCount++; } });
        if (removedCount) showToast(`${removedCount} selected image(s) removed by filter`, 'info');

        updateSelectionUI();
        displayImages(filteredImages);
    }

    // ==========================================================================
    // SELECTION
    // ==========================================================================
    function updateSelectionUI() {
        const n = selectedUrls.size;
        if (n > 0) {
            selectionBar.classList.remove('hidden');
            selectionInfo.textContent = `${n} image${n > 1 ? 's' : ''} selected`;
            downloadBtn.querySelector('span').textContent = `Download Selected (${n})`;
            downloadZipBtn.querySelector('span').textContent = `Download ZIP (${n})`;
        } else {
            selectionBar.classList.add('hidden');
            downloadBtn.querySelector('span').textContent = 'Download Files';
            downloadZipBtn.querySelector('span').textContent = 'Download ZIP';
        }
    }

    selectAllBtn.addEventListener('click', () => {
        filteredImages.forEach(i => selectedUrls.add(i.url));
        updateSelectionUI();
        document.querySelectorAll('.img-card').forEach(c => c.classList.add('selected'));
    });

    clearSelectionBtn.addEventListener('click', () => {
        selectedUrls.clear();
        updateSelectionUI();
        document.querySelectorAll('.img-card').forEach(c => c.classList.remove('selected'));
    });

    // ==========================================================================
    // DISPLAY IMAGE GRID
    // ==========================================================================
    function displayImages(images) {
        imageGrid.innerHTML = '';
        if (!images.length) {
            imageGrid.innerHTML = `<p style="color:var(--text-dim);grid-column:1/-1;text-align:center;padding:3rem;font-weight:600;">No images match this filter.</p>`;
            return;
        }
        const frag = document.createDocumentFragment();
        images.forEach((img, idx) => {
            const card = document.createElement('div');
            card.className = `img-card ${selectedUrls.has(img.url) ? 'selected' : ''}`;
            card.dataset.index = idx;
            const safeAlt = (img.alt || 'Image').replace(/"/g, '&quot;');
            card.innerHTML = `
                <div class="card-select-checkbox" title="Select"><i data-lucide="check"></i></div>
                <img src="${img.thumb || img.url}" referrerpolicy="no-referrer"
                     onerror="this.onerror=null;this.style.opacity='0.2';this.style.filter='grayscale(1)';"
                     alt="${safeAlt}" loading="lazy">
                <div class="card-overlay">
                    <span class="badge badge-orig">Original</span>
                    <div class="card-actions">
                        <button class="btn-mini btn-preview" title="Preview"><i data-lucide="maximize-2"></i></button>
                    </div>
                </div>`;
            card.addEventListener('click', e => {
                if (e.target.closest('.btn-preview')) { e.stopPropagation(); openLightbox(idx); return; }
                e.preventDefault();
                if (selectedUrls.has(img.url)) { selectedUrls.delete(img.url); card.classList.remove('selected'); }
                else { selectedUrls.add(img.url); card.classList.add('selected'); }
                updateSelectionUI();
            });
            frag.appendChild(card);
        });
        imageGrid.appendChild(frag);
        lucide.createIcons();
    }

    // ==========================================================================
    // DOWNLOAD MODAL HELPERS
    // ==========================================================================
    function showModal(title, status) {
        downloadAborted = false;
        downloadModalTitle.textContent = title;
        downloadModalStatus.textContent = status;
        progressBarFill.style.width = '0%';
        progressBarFill.classList.remove('indeterminate');
        statProgress.textContent = '0%';
        statSpeed.textContent = '0 KB/s';
        statEta.textContent = '--:--';
        cancelDownloadBtn.textContent = 'Cancel Download';
        cancelDownloadBtn.className = 'btn-danger';
        cancelDownloadBtn.disabled = false;
        downloadLog.innerHTML = '<div class="log-entry">Starting…</div>';
        downloadModal.classList.add('active');
    }

    function logEntry(text, type = '') {
        const el = document.createElement('div');
        el.className = `log-entry ${type}`;
        el.textContent = text;
        downloadLog.appendChild(el);
        downloadLog.scrollTop = downloadLog.scrollHeight;
    }

    function updateStats(pct, speed, eta) {
        progressBarFill.style.width = pct + '%';
        statProgress.textContent = Math.round(pct) + '%';
        statSpeed.textContent = speed;
        statEta.textContent = eta;
    }

    function doneModal(successMsg) {
        cancelDownloadBtn.textContent = 'Close Panel';
        cancelDownloadBtn.className = 'btn-primary';
        cancelDownloadBtn.disabled = false;
        if (successMsg) showToast(successMsg, 'success');
    }

    // Close modal on backdrop click (only when not actively downloading)
    downloadModal.addEventListener('click', e => {
        if (e.target === downloadModal && cancelDownloadBtn.textContent === 'Close Panel') {
            downloadModal.classList.remove('active');
        }
    });

    cancelDownloadBtn.addEventListener('click', () => {
        if (cancelDownloadBtn.textContent === 'Close Panel') {
            downloadModal.classList.remove('active');
            return;
        }
        downloadAborted = true;
        logEntry('Aborting…', 'fail');
        downloadModalStatus.textContent = 'Cancelling…';
        cancelDownloadBtn.disabled = true;
    });

    // ==========================================================================
    // FETCH IMAGE BLOB — 3-tier fallback: direct → Vercel proxy → local proxy
    // ==========================================================================
    async function fetchImageBlob(url) {
        // 1. Direct fetch (works if CDN has CORS open)
        try {
            const r = await fetch(url, { referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(5000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        // 2. Vercel serverless proxy (works on HTTPS Vercel, never blocked)
        try {
            const r = await fetch(`/api/proxy?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(10000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        // 3. Local backend proxy (works when running locally)
        try {
            const r = await fetch(`${LOCAL_API}/api/proxy_download?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(10000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        return null;
    }

    // Shared parallel worker factory to avoid function name conflicts
    function makeWorkers(targets, taskFn, concurrency = 6) {
        let pos = 0;
        async function runWorker() {
            while (pos < targets.length && !downloadAborted) {
                const i = pos++;
                await taskFn(i, targets[i]);
            }
        }
        return Promise.all(Array.from({ length: Math.min(concurrency, targets.length) }, runWorker));
    }

    // ==========================================================================
    // DOWNLOAD FILES — individual file download with progress
    // ==========================================================================
    downloadBtn.addEventListener('click', async () => {
        const targets = selectedUrls.size ? filteredImages.filter(i => selectedUrls.has(i.url)) : filteredImages;
        if (!targets.length) return;

        showModal(`Download ${targets.length} Images`, `Preparing to download ${targets.length} files…`);
        logEntry(`Queued ${targets.length} images for download.`, 'success');

        let done = 0, ok = 0, bytes = 0;
        const t0 = Date.now();

        await makeWorkers(targets, async (i, img) => {
            try {
                const blob = await fetchImageBlob(img.url);
                if (!blob) throw new Error('Empty response');
                bytes += blob.size;
                let ext = img.url.split('.').pop().split('?')[0].toLowerCase();
                if (!['jpg','jpeg','png','webp','gif','avif'].includes(ext)) ext = 'jpg';
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `img_${String(i + 1).padStart(4, '0')}.${ext}`;
                document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();
                ok++;
                logEntry(`✔ img_${i+1} (${(blob.size / 1024).toFixed(1)} KB)`, 'success');
            } catch(e) {
                logEntry(`✖ img_${i+1}: ${e.message}`, 'fail');
            }
            done++;
            const elapsed = (Date.now() - t0) / 1000;
            const sp = bytes / Math.max(elapsed, 0.1);
            const spTxt = sp < 1048576 ? `${(sp/1024).toFixed(1)} KB/s` : `${(sp/1048576).toFixed(1)} MB/s`;
            const rem = done > 0 ? (elapsed / done) * (targets.length - done) : 0;
            updateStats(
                (done / targets.length) * 100,
                spTxt,
                rem < 60 ? `${Math.ceil(rem)}s` : `${Math.floor(rem/60)}m ${Math.ceil(rem%60)}s`
            );
            downloadModalStatus.textContent = `${done} / ${targets.length} done…`;
        });

        logEntry(`✅ Done: ${ok}/${targets.length} saved.`, 'success');
        downloadModalStatus.textContent = 'Complete!';
        updateStats(100, '—', 'Done');
        doneModal(`Downloaded ${ok} image${ok !== 1 ? 's' : ''} successfully!`);
    });

    // ==========================================================================
    // ZIP DOWNLOAD — local backend (fast) OR in-browser JSZip (HTTPS fallback)
    // ==========================================================================
    downloadZipBtn.addEventListener('click', async () => {
        const targets = selectedUrls.size ? filteredImages.filter(i => selectedUrls.has(i.url)) : filteredImages;
        if (!targets.length) return;

        // ── Mode 1: Local backend fast parallel ZIP
        if (localAvailable) {
            showModal(`Building ZIP — ${targets.length} images`, 'Sending to local backend…');
            logEntry(`Downloading ${targets.length} images via local backend…`, 'success');
            progressBarFill.classList.add('indeterminate');
            updateStats(0, '—', 'Working…');

            try {
                downloadModalStatus.textContent = `Downloading ${targets.length} images…`;
                const res = await fetch(`${LOCAL_API}/api/download`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls: targets.map(i => i.url) }),
                    signal: AbortSignal.timeout(300000)
                });
                if (!res.ok) throw new Error(`Backend error ${res.status}`);

                progressBarFill.classList.remove('indeterminate');
                downloadModalStatus.textContent = 'Packaging ZIP…';
                updateStats(80, '—', 'Packaging…');

                const blob = await res.blob();
                updateStats(100, '—', 'Done');

                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `yandex_images_${Date.now().toString().slice(-6)}.zip`;
                document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();

                const sizeMB = (blob.size / 1048576).toFixed(2);
                logEntry(`✅ ZIP downloaded: ${sizeMB} MB`, 'success');
                downloadModalStatus.textContent = 'ZIP downloaded!';
                doneModal(`ZIP saved — ${sizeMB} MB (${targets.length} images)`);
                return;
            } catch(e) {
                progressBarFill.classList.remove('indeterminate');
                logEntry(`⚠️ Backend unreachable (${e.message}) — switching to in-browser ZIP…`, 'fail');
                // fall through to Mode 2
            }
        }

        // ── Mode 2: Client-side JSZip (works on HTTPS Vercel via /api/proxy)
        if (typeof JSZip === 'undefined') {
            showToast('JSZip is still loading — please wait a moment and try again.', 'error');
            return;
        }

        showModal(`Building ZIP — ${targets.length} images`, 'Fetching images in browser…');
        logEntry(`Starting client-side ZIP for ${targets.length} images…`, 'info');

        const zip = new JSZip();
        let zipDone = 0, zipOk = 0, zipBytes = 0;
        const t0 = Date.now();

        await makeWorkers(targets, async (i, img) => {
            try {
                const blob = await fetchImageBlob(img.url);
                if (!blob) throw new Error('Fetch failed');
                zipBytes += blob.size;
                let ext = img.url.split('.').pop().split('?')[0].toLowerCase();
                if (!['jpg','jpeg','png','webp','gif','avif'].includes(ext)) ext = 'jpg';
                zip.file(`image_${String(i + 1).padStart(4, '0')}.${ext}`, blob);
                zipOk++;
                logEntry(`✔ Packaged img_${i+1} (${(blob.size/1024).toFixed(1)} KB)`, 'success');
            } catch(e) {
                logEntry(`✖ img_${i+1}: ${e.message}`, 'fail');
            }
            zipDone++;
            const elapsed = (Date.now() - t0) / 1000;
            const sp = zipBytes / Math.max(elapsed, 0.1);
            const spTxt = sp < 1048576 ? `${(sp/1024).toFixed(1)} KB/s` : `${(sp/1048576).toFixed(1)} MB/s`;
            const rem = zipDone > 0 ? (elapsed / zipDone) * (targets.length - zipDone) : 0;
            updateStats(
                (zipDone / targets.length) * 80,
                spTxt,
                rem < 60 ? `${Math.ceil(rem)}s` : `${Math.floor(rem/60)}m ${Math.ceil(rem%60)}s`
            );
            downloadModalStatus.textContent = `${zipDone} / ${targets.length} fetched…`;
        });

        if (downloadAborted || zipOk === 0) {
            logEntry('No images fetched — ZIP cancelled.', 'fail');
            doneModal(null);
            return;
        }

        downloadModalStatus.textContent = 'Compressing archive…';
        logEntry('Compressing ZIP archive…', 'info');
        progressBarFill.classList.add('indeterminate');

        try {
            const content = await zip.generateAsync({ type: 'blob' });
            progressBarFill.classList.remove('indeterminate');
            updateStats(100, '—', 'Done');

            const a = document.createElement('a');
            a.href = URL.createObjectURL(content);
            a.download = `yandex_images_${Date.now().toString().slice(-6)}.zip`;
            document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();

            const sizeMB = (content.size / 1048576).toFixed(2);
            logEntry(`✅ ZIP generated: ${sizeMB} MB`, 'success');
            downloadModalStatus.textContent = 'ZIP downloaded!';
            doneModal(`ZIP saved — ${sizeMB} MB (${zipOk} images)`);
        } catch(err) {
            progressBarFill.classList.remove('indeterminate');
            logEntry('Compression failed: ' + err.message, 'fail');
            showToast('ZIP compression failed', 'error');
            doneModal(null);
        }
    });

    // ==========================================================================
    // LIGHTBOX
    // ==========================================================================
    function openLightbox(i) {
        currentLightboxIdx = i;
        updateLightbox();
        lightboxModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeLightbox() {
        lightboxModal.classList.remove('active');
        document.body.style.overflow = '';
        lightboxImg.src = '';
        lightboxImg.classList.remove('loaded');
        if (lightboxSpinner) lightboxSpinner.classList.remove('hidden');
    }

    function updateLightbox() {
        if (currentLightboxIdx < 0 || currentLightboxIdx >= filteredImages.length) return;
        const img = filteredImages[currentLightboxIdx];

        lightboxImg.classList.remove('loaded');
        if (lightboxSpinner) lightboxSpinner.classList.remove('hidden');

        lightboxImg.onload = () => {
            lightboxImg.classList.add('loaded');
            if (lightboxSpinner) lightboxSpinner.classList.add('hidden');
        };
        lightboxImg.onerror = function() {
            this.onerror = null;
            this.src = img.thumb || img.url;
            if (lightboxSpinner) lightboxSpinner.classList.add('hidden');
            lightboxImg.classList.add('loaded');
        };

        lightboxImg.setAttribute('referrerpolicy', 'no-referrer');
        lightboxImg.src = img.url;
        lightboxTitle.textContent = img.alt || 'Yandex Image';
        lightboxCounter.textContent = `${currentLightboxIdx + 1} of ${filteredImages.length}`;

        let ext = img.url.split('.').pop().split('?')[0].toUpperCase();
        if (ext.length > 4) ext = 'IMG';
        lightboxMeta.textContent = `Original | ${ext}`;
    }

    lightboxCloseBtn.addEventListener('click', closeLightbox);

    lightboxPrevBtn.addEventListener('click', () => {
        currentLightboxIdx = (currentLightboxIdx - 1 + filteredImages.length) % filteredImages.length;
        updateLightbox();
    });

    lightboxNextBtn.addEventListener('click', () => {
        currentLightboxIdx = (currentLightboxIdx + 1) % filteredImages.length;
        updateLightbox();
    });

    lightboxDownloadBtn.addEventListener('click', async () => {
        const img = filteredImages[currentLightboxIdx];
        if (!img) return;
        showToast('Fetching image…', 'info', 2000);
        const blob = await fetchImageBlob(img.url);
        if (blob) {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `yandex_${Date.now()}.jpg`;
            document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();
            showToast('Image saved!', 'success');
        } else {
            window.open(img.url, '_blank');
        }
    });

    lightboxModal.addEventListener('click', e => {
        if (e.target === lightboxModal) closeLightbox();
    });

    document.addEventListener('keydown', e => {
        if (!lightboxModal.classList.contains('active')) return;
        if (e.key === 'Escape') closeLightbox();
        else if (e.key === 'ArrowLeft') lightboxPrevBtn.click();
        else if (e.key === 'ArrowRight') lightboxNextBtn.click();
    });

    // Touch swipe support for lightbox
    let touchStartX = 0, touchStartY = 0;
    lightboxModal.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].clientX;
        touchStartY = e.changedTouches[0].clientY;
    }, { passive: true });

    lightboxModal.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx < 0) lightboxNextBtn.click();
            else        lightboxPrevBtn.click();
        }
    }, { passive: true });
});
