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
    const sourceSelect            = document.getElementById('sourceSelect');
    const deepScrapeToggleGroup   = document.getElementById('deepScrapeToggleGroup');
    const urlInput                = document.getElementById('urlInput');
    const scrapeBtn               = document.getElementById('scrapeBtn');
    const loader                  = document.getElementById('loader');
    const loaderMsg               = document.getElementById('loaderMsg');
    const resultsSection          = document.getElementById('resultsSection');
    const imageGrid               = document.getElementById('imageGrid');
    const imageCount              = document.getElementById('imageCount');
    const downloadBtn             = document.getElementById('downloadBtn');
    const downloadZipBtn          = document.getElementById('downloadZipBtn');
    const autoscrollToggle        = document.getElementById('autoscrollToggle');
    const filterSelect            = document.getElementById('filterSelect');
    const countBtn                = document.getElementById('countBtn');
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
    // BACKEND DETECTION — tries Render.com cloud first, then localhost
    // This means the app works fully online with zero local setup.
    // ==========================================================================
    const RENDER_API   = 'https://image-scraper-pro.onrender.com';
    const LOCAL_API    = 'http://localhost:5000';
    let BACKEND_URL    = RENDER_API;  // default: cloud backend
    let localAvailable = false;
    let localCheckTs   = 0;
    const LOCAL_CHECK_TTL = 60000; // 60s cache

    async function checkLocalBackend(force = false) {
        const now = Date.now();
        if (!force && (now - localCheckTs) < LOCAL_CHECK_TTL) return;
        localCheckTs = now;

        // 1. Try local backend first (when running locally)
        try {
            const r = await fetch(`${LOCAL_API}/api/health`, { signal: AbortSignal.timeout(1500) });
            if (r.ok) {
                BACKEND_URL   = LOCAL_API;
                localAvailable = true;
                updateStatusBadge();
                return;
            }
        } catch {}

        // 2. Try Render.com cloud backend
        try {
            const r = await fetch(`${RENDER_API}/api/health`, { signal: AbortSignal.timeout(8000) });
            if (r.ok) {
                BACKEND_URL   = RENDER_API;
                localAvailable = true;
                updateStatusBadge();
                return;
            }
        } catch {}

        localAvailable = false;
        updateStatusBadge();
    }
    checkLocalBackend(true);

    function updateStatusBadge() {
        if (!settingsDropdown) return;
        const isCloud = BACKEND_URL === RENDER_API;
        const label   = localAvailable
            ? (isCloud ? 'Cloud Backend ✅' : 'Local Backend ✅')
            : 'Backend Offline ❌';
        settingsDropdown.innerHTML = `<div style="font-size:12px;color:var(--text-dim);max-width:260px;">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
                <span style="width:8px;height:8px;border-radius:50%;background:${localAvailable ? '#5efb6e' : '#ff5c5c'};display:inline-block;flex-shrink:0;"></span>
                <strong style="color:var(--text-main);">${label}</strong>
            </div>
            ${localAvailable
                ? `<span style="color:#5efb6e;">${isCloud ? 'Using Render.com cloud — 1000+ images, no setup needed.' : 'Using local backend — 1000+ images.'}</span>`
                : '<span style="color:#ff8844;">Backend is starting up… please wait 30s and try again.</span>'}
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

    if (sourceSelect) {
        sourceSelect.addEventListener('change', () => {
            const isPinterest = sourceSelect.value === 'pinterest';
            if (isPinterest) {
                urlInput.placeholder = 'https://in.pinterest.com/pin/1136033074757270594/ or /visual-search/';
                urlInput.setAttribute('aria-label', 'Pinterest Pin or Visual Search URL');
                countBtn.style.display = 'none';
                if (deepScrapeToggleGroup) deepScrapeToggleGroup.style.display = 'none';
                const textSpan = scrapeBtn.querySelector('.btn-text');
                if (textSpan) textSpan.textContent = 'Extract Images';
                countPanel.classList.add('hidden');
            } else {
                urlInput.placeholder = 'https://yandex.com/images/search?text=cats';
                urlInput.setAttribute('aria-label', 'Yandex Images URL');
                countBtn.style.display = '';
                if (deepScrapeToggleGroup) deepScrapeToggleGroup.style.display = '';
                const textSpan = scrapeBtn.querySelector('.btn-text');
                if (textSpan) textSpan.textContent = 'Extract Images';
            }
        });
    }

    async function extractPinterest(pinUrl) {
        const pinPattern = /https?:\/\/(?:[a-z0-9\-]+\.)?pinterest\.(?:com|[a-z]{2,3}(?:\.[a-z]{2})?)\/pin\//i;
        const pinItPattern = /https?:\/\/pin\.it\//i;
        if (!pinPattern.test(pinUrl) && !pinItPattern.test(pinUrl)) {
            showToast('Invalid Pinterest Pin or Visual Search URL. Please verify the link and try again.', 'error');
            return;
        }

        resultsSection.classList.add('hidden');
        loader.classList.remove('hidden');
        imageGrid.innerHTML = '';
        allImages = []; filteredImages = [];
        selectedUrls.clear();
        updateSelectionUI();
        countPanel.classList.add('hidden');

        loaderMsg.textContent = '⚡ Dynamically extracting Pinterest images (target 300+)… hold on!';

        const endpoints = [];
        if (window.PINTEREST_SCRAPER_URL) {
            endpoints.push(`${window.PINTEREST_SCRAPER_URL.replace(/\/$/, '')}/api/pinterest/extract`);
        }
        endpoints.push(
            `${BACKEND_URL}/api/pinterest/extract`,
            `${RENDER_API}/api/pinterest/extract`,
            `${LOCAL_API}/api/pinterest/extract`
        );
        const uniqueEndpoints = [...new Set(endpoints)];

        let extractedData = null;
        let errMsg = 'Unable to extract images from this Pinterest link. Please verify the URL and try again.';

        for (const endpoint of uniqueEndpoints) {
            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: pinUrl, min_target: 300, max_images: 1000 }),
                    signal: AbortSignal.timeout(45000)
                });
                const data = await res.json();
                if (res.ok && data.success && data.images && data.images.length > 0) {
                    extractedData = data;
                    break;
                } else if (data.error) {
                    errMsg = data.error;
                }
            } catch (e) {
                console.warn('[pinterest] Endpoint failed:', endpoint, e);
            }
        }

        loader.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        if (!extractedData || !extractedData.images || extractedData.images.length === 0) {
            imageGrid.innerHTML = renderEmptyState({
                icon: 'search-x',
                title: 'Extraction Failed',
                body: `${errMsg}<br><br>Please verify the Pinterest URL and try again.`
            });
            imageCount.textContent = '0 images';
            showToast(errMsg, 'error');
        } else {
            allImages = extractedData.images;
            filterSelect.value = 'all';
            applyFilter();
            showToast(`Extracted ${allImages.length} Main + Related image(s) from Pinterest!`, 'success');
        }
        lucide.createIcons();
    }

    // ==========================================================================
    // HELPERS
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
    // SCRAPE — requires local Python backend (Yandex blocks all cloud scrapers)
    // ==========================================================================
    scrapeBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) {
            urlInput.focus();
            const isPinterest = sourceSelect && sourceSelect.value === 'pinterest';
            showToast(isPinterest ? 'Please enter a Pinterest Pin URL' : 'Please enter a Yandex Images URL', 'error');
            return;
        }

        if (sourceSelect && sourceSelect.value === 'pinterest') {
            return extractPinterest(url);
        }

        resultsSection.classList.add('hidden');
        loader.classList.remove('hidden');
        imageGrid.innerHTML = '';
        allImages = []; filteredImages = [];
        selectedUrls.clear();
        updateSelectionUI();
        countPanel.classList.add('hidden');

        const deepMode = autoscrollToggle.checked;
        loaderMsg.textContent = '⚡ Connecting to cloud server (extracting images)…';

        let extracted = [];
        const endpoints = [
            `${BACKEND_URL}/api/scrape`,
            `${LOCAL_API}/api/scrape`,
            `/api/scrape`,
            `${RENDER_API}/api/scrape`
        ];
        const uniqueEndpoints = [...new Set(endpoints)];

        // Retry loop: try up to 3 times to handle Render cold-start wakeups gracefully
        for (let attempt = 1; attempt <= 3; attempt++) {
            if (attempt > 1) {
                loaderMsg.textContent = `⚡ Cloud server waking up, retrying extraction (attempt ${attempt}/3)…`;
                await new Promise(r => setTimeout(r, 3000));
            }

            for (const endpoint of uniqueEndpoints) {
                try {
                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url, autoscroll: deepMode }),
                        signal: AbortSignal.timeout(45000)
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.images && data.images.length > 0) {
                            extracted = data.images;
                            if (endpoint.startsWith('http')) {
                                BACKEND_URL = endpoint.replace('/api/scrape', '');
                                localAvailable = true;
                                updateStatusBadge();
                            }
                            break;
                        }
                    }
                } catch (e) {}
            }

            if (extracted.length > 0) break;
        }

        allImages = extracted;

        loader.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        if (!allImages.length) {
            imageGrid.innerHTML = renderEmptyState({
                icon: 'search-x',
                title: 'No Images Found',
                body: `The cloud server took too long to respond.<br><br>Please wait 5 seconds and click <strong>Extract Images</strong> again.`
            });
            imageCount.textContent = '0 images';
            showToast('Cloud server waking up — please click Extract Images again', 'info');
        } else {
            filterSelect.value = 'all';
            applyFilter();
            showToast(`Found ${allImages.length} images!`, 'success');
        }
        lucide.createIcons();
    });

    // ==========================================================================
    // COUNT
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
            if (!localAvailable) throw new Error('Backend is offline. Please wait 30s and try again (cold start).');
            const res = await fetch(`${BACKEND_URL}/api/count`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
                signal: AbortSignal.timeout(30000)
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            const total = data.count || 0;
            const bd = data.breakdown || {};
            countPanel.classList.remove('hidden');
            animateCount(countTotal, total);
            countMethodBadge.textContent = '⚡ Local (page 1 only)';
            countBreakdown.innerHTML = Object.entries(bd).map(([k, v]) =>
                `<span class="count-chip"><strong>${v}</strong> ${k.toUpperCase()}</span>`
            ).join('') || '<span class="count-chip">No breakdown</span>';
            countNote.textContent = 'Page 1 only. Enable Deep Scrape for 1000+ images.';
            showToast(`${total} images on page 1`, 'success');
        } catch (err) {
            countPanel.classList.remove('hidden');
            countTotal.textContent = '?';
            countMethodBadge.textContent = 'Error';
            countBreakdown.innerHTML = '';
            const msg = (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))
                ? 'Could not reach local backend.'
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
        const fSet = new Set(filteredImages.map(i => i.url));
        let removed = 0;
        selectedUrls.forEach(u => { if (!fSet.has(u)) { selectedUrls.delete(u); removed++; } });
        if (removed) showToast(`${removed} selected image(s) removed by filter`, 'info');
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
    // DISPLAY
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
    // MODAL HELPERS
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
        cancelDownloadBtn.textContent = 'Cancel';
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

    function doneModal(msg) {
        cancelDownloadBtn.textContent = 'Close';
        cancelDownloadBtn.className = 'btn-primary';
        cancelDownloadBtn.disabled = false;
        if (msg) showToast(msg, 'success');
    }

    downloadModal.addEventListener('click', e => {
        if (e.target === downloadModal && cancelDownloadBtn.textContent === 'Close') {
            downloadModal.classList.remove('active');
        }
    });

    cancelDownloadBtn.addEventListener('click', () => {
        if (cancelDownloadBtn.textContent === 'Close') {
            downloadModal.classList.remove('active');
            return;
        }
        downloadAborted = true;
        logEntry('Aborting…', 'fail');
        downloadModalStatus.textContent = 'Cancelling…';
        cancelDownloadBtn.disabled = true;
    });

    // ==========================================================================
    // FETCH IMAGE BLOB — 3-tier: direct → Vercel proxy → local proxy
    // ==========================================================================
    async function fetchImageBlob(url) {
        try {
            const r = await fetch(url, { referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(8000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        try {
            const r = await fetch(`/api/proxy?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(15000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        try {
            const r = await fetch(`${BACKEND_URL}/api/proxy_download?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(15000) });
            if (r.ok) { const b = await r.blob(); if (b.size > 500) return b; }
        } catch {}
        return null;
    }

    // Shared parallel worker runner (avoids function name collision)
    function runParallel(targets, taskFn, concurrency = 6) {
        let pos = 0;
        const worker = async () => {
            while (pos < targets.length && !downloadAborted) {
                const i = pos++;
                await taskFn(i, targets[i]);
            }
        };
        return Promise.all(Array.from({ length: Math.min(concurrency, targets.length) }, worker));
    }

    // ==========================================================================
    // DOWNLOAD FILES (individual)
    // ==========================================================================
    downloadBtn.addEventListener('click', async () => {
        const targets = selectedUrls.size ? filteredImages.filter(i => selectedUrls.has(i.url)) : filteredImages;
        if (!targets.length) return;

        showModal(`Download ${targets.length} Images`, `Preparing…`);
        logEntry(`Queued ${targets.length} images.`, 'success');

        let done = 0, ok = 0, bytes = 0;
        const t0 = Date.now();

        await runParallel(targets, async (i, img) => {
            try {
                const blob = await fetchImageBlob(img.url);
                if (!blob) throw new Error('No data');
                bytes += blob.size;
                let ext = img.url.split('.').pop().split('?')[0].toLowerCase();
                if (!['jpg','jpeg','png','webp','gif','avif'].includes(ext)) ext = 'jpg';
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `img_${String(i + 1).padStart(4, '0')}.${ext}`;
                document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();
                ok++;
                logEntry(`✔ img_${i+1} (${(blob.size/1024).toFixed(1)} KB)`, 'success');
            } catch(e) {
                logEntry(`✖ img_${i+1}: ${e.message}`, 'fail');
            }
            done++;
            const el = (Date.now() - t0) / 1000;
            const sp = bytes / Math.max(el, 0.1);
            const spTxt = sp < 1048576 ? `${(sp/1024).toFixed(1)} KB/s` : `${(sp/1048576).toFixed(1)} MB/s`;
            const rem = done > 0 ? (el/done) * (targets.length - done) : 0;
            updateStats((done/targets.length)*100, spTxt, rem < 60 ? `${Math.ceil(rem)}s` : `${Math.floor(rem/60)}m ${Math.ceil(rem%60)}s`);
            downloadModalStatus.textContent = `${done}/${targets.length} done…`;
        });

        logEntry(`✅ ${ok}/${targets.length} saved.`, 'success');
        updateStats(100, '—', 'Done');
        doneModal(`Downloaded ${ok} image${ok !== 1 ? 's' : ''}!`);
    });

    // ==========================================================================
    // DOWNLOAD ZIP — local backend (fast) → JSZip in-browser (HTTPS fallback)
    // ==========================================================================
    downloadZipBtn.addEventListener('click', async () => {
        const targets = selectedUrls.size ? filteredImages.filter(i => selectedUrls.has(i.url)) : filteredImages;
        if (!targets.length) return;

        // ── Mode 1: Backend bulk ZIP — only for ≤150 images (free tier 512MB RAM limit)
        // For larger batches we go straight to in-browser JSZip which handles any size.
        if (localAvailable && targets.length <= 150) {
            showModal(`Building ZIP — ${targets.length} images`, 'Sending to local backend…');
            logEntry(`Requesting ZIP from local backend…`, 'success');
            progressBarFill.classList.add('indeterminate');

            try {
                const res = await fetch(`${BACKEND_URL}/api/download`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls: targets.map(i => i.url) }),
                    signal: AbortSignal.timeout(300000)
                });
                if (!res.ok) throw new Error(`Backend error ${res.status}`);
                progressBarFill.classList.remove('indeterminate');
                updateStats(90, '—', 'Packaging…');
                const blob = await res.blob();
                updateStats(100, '—', 'Done');
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `yandex_images_${Date.now().toString().slice(-6)}.zip`;
                document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();
                const sizeMB = (blob.size / 1048576).toFixed(2);
                logEntry(`✅ ZIP downloaded: ${sizeMB} MB`, 'success');
                doneModal(`ZIP saved — ${sizeMB} MB (${targets.length} images)`);
                return;
            } catch(e) {
                progressBarFill.classList.remove('indeterminate');
                logEntry(`Backend ZIP failed: ${e.message} — switching to browser ZIP…`, 'fail');
                // fall through to JSZip
            }
        }

        // ── Mode 2: In-browser JSZip (works on HTTPS via /api/proxy)
        if (typeof JSZip === 'undefined') {
            try {
                await new Promise((resolve, reject) => {
                    const s = document.createElement('script');
                    s.src = 'jszip.min.js';
                    s.onload = resolve;
                    s.onerror = () => {
                        const cdn = document.createElement('script');
                        cdn.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
                        cdn.onload = resolve;
                        cdn.onerror = reject;
                        document.head.appendChild(cdn);
                    };
                    document.head.appendChild(s);
                });
            } catch {
                showToast('Failed to load ZIP library. Please check your internet connection.', 'error');
                return;
            }
        }

        showModal(`Building ZIP — ${targets.length} images`, 'Fetching images…');
        logEntry(`Building ZIP in browser (${targets.length} images)…`, 'info');

        const zip = new JSZip();
        let done = 0, ok = 0, bytes = 0;
        const t0 = Date.now();

        await runParallel(targets, async (i, img) => {
            try {
                const blob = await fetchImageBlob(img.url);
                if (!blob) throw new Error('Fetch failed');
                bytes += blob.size;
                let ext = img.url.split('.').pop().split('?')[0].toLowerCase();
                if (!['jpg','jpeg','png','webp','gif','avif'].includes(ext)) ext = 'jpg';
                zip.file(`image_${String(i + 1).padStart(4, '0')}.${ext}`, blob);
                ok++;
                logEntry(`✔ Packed img_${i+1} (${(blob.size/1024).toFixed(1)} KB)`, 'success');
            } catch(e) {
                logEntry(`✖ img_${i+1}: ${e.message}`, 'fail');
            }
            done++;
            const el = (Date.now() - t0) / 1000;
            const sp = bytes / Math.max(el, 0.1);
            const spTxt = sp < 1048576 ? `${(sp/1024).toFixed(1)} KB/s` : `${(sp/1048576).toFixed(1)} MB/s`;
            const rem = done > 0 ? (el/done) * (targets.length - done) : 0;
            updateStats((done/targets.length)*80, spTxt, rem < 60 ? `${Math.ceil(rem)}s` : `${Math.floor(rem/60)}m ${Math.ceil(rem%60)}s`);
            downloadModalStatus.textContent = `${done}/${targets.length} fetched…`;
        });

        if (downloadAborted || ok === 0) {
            logEntry('ZIP cancelled — no images fetched.', 'fail');
            doneModal(null);
            return;
        }

        logEntry('Compressing ZIP…', 'info');
        progressBarFill.classList.add('indeterminate');
        downloadModalStatus.textContent = 'Compressing…';

        try {
            const content = await zip.generateAsync({ type: 'blob' });
            progressBarFill.classList.remove('indeterminate');
            updateStats(100, '—', 'Done');
            const a = document.createElement('a');
            a.href = URL.createObjectURL(content);
            a.download = `yandex_images_${Date.now().toString().slice(-6)}.zip`;
            document.body.appendChild(a); a.click(); URL.revokeObjectURL(a.href); a.remove();
            const sizeMB = (content.size / 1048576).toFixed(2);
            logEntry(`✅ ZIP: ${sizeMB} MB`, 'success');
            doneModal(`ZIP saved — ${sizeMB} MB (${ok} images)`);
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
        } else { window.open(img.url, '_blank'); }
    });
    lightboxModal.addEventListener('click', e => { if (e.target === lightboxModal) closeLightbox(); });
    document.addEventListener('keydown', e => {
        if (!lightboxModal.classList.contains('active')) return;
        if (e.key === 'Escape') closeLightbox();
        else if (e.key === 'ArrowLeft') lightboxPrevBtn.click();
        else if (e.key === 'ArrowRight') lightboxNextBtn.click();
    });

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
            else lightboxPrevBtn.click();
        }
    }, { passive: true });
});
