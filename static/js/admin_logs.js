/**
 * admin_logs.js — Admin Server Logs Live Viewer (Easter Egg) + Stop All Processes
 *
 * Both the admin console and the Stop All panel are now reusable floating windows.
 * They support:
 *   - Draggable header
 *   - Minimize/Restore (snaps to bottom-right corner like a taskbar)
 *   - Maximize/Fullscreen
 *   - Click-to-Front (clicking any part brings it above siblings)
 */

document.addEventListener('DOMContentLoaded', () => {

    // =========================================================================
    // --- Shared: z-index / Click-to-Front Manager ---
    // =========================================================================
    let highestZIndex = 9999;

    function bringToFront(el) {
        if (!el) return;
        highestZIndex++;
        el.style.zIndex = highestZIndex;
    }

    // =========================================================================
    // --- Shared: Floating Window Factory ---
    // Creates a self-contained floating, draggable, minimizable window.
    //
    // @param {object} opts - Configuration object
    //   opts.wrapper    - The outer wrapper element (div.admin-console-wrapper)
    //   opts.header     - The header bar element (used for drag handle)
    //   opts.minimizeBtn
    //   opts.maximizeBtn  (optional)
    //   opts.closeBtn
    //   opts.onClose    - Callback when window is closed
    //   opts.onMinimize - Callback when minimized (optional)
    //   opts.onRestore  - Callback when restored from minimized (optional)
    //   opts.bottomOffset - The right offset for minimized taskbar position (default: '20px')
    //   opts.minimizedWidth - Width when minimized (default: '300px')
    // =========================================================================
    function setupFloatingWindow(opts) {
        const { wrapper, header, minimizeBtn, maximizeBtn, closeBtn, onClose, onMinimize, onRestore } = opts;
        const bottomOffset = opts.bottomOffset || '20px';
        const minimizedWidth = opts.minimizedWidth || '300px';

        let _isMinimized = false;
        let _isMaximized = false;

        // Click-to-front on any interaction
        wrapper.addEventListener('mousedown', () => bringToFront(wrapper));

        // --- Drag State ---
        let isDragging = false;
        let initialX = 0, initialY = 0;
        let offsetX = 0, offsetY = 0;
        let currentTransformX = 0, currentTransformY = 0;

        header.addEventListener('mousedown', (e) => {
            if (_isMinimized || _isMaximized || e.target.closest('.admin-console-btn')) return;
            isDragging = true;
            initialX = e.clientX;
            initialY = e.clientY;
            document.body.style.userSelect = 'none';

            // Freeze position on first drag
            const rect = wrapper.getBoundingClientRect();
            if (wrapper.style.bottom !== 'auto') {
                wrapper.style.bottom = 'auto';
                wrapper.style.right = 'auto';
                wrapper.style.left = rect.left + 'px';
                wrapper.style.top = rect.top + 'px';
                currentTransformX = 0;
                currentTransformY = 0;
            }
            wrapper.style.transition = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            e.preventDefault();
            const dx = e.clientX - initialX;
            const dy = e.clientY - initialY;
            offsetX = currentTransformX + dx;
            offsetY = currentTransformY + dy;
            wrapper.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
        });

        document.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            currentTransformX = offsetX;
            currentTransformY = offsetY;
            document.body.style.userSelect = '';
            wrapper.style.transition = 'width 0.3s, height 0.3s, bottom 0.3s, right 0.3s';

            // Snap back if dragged off-screen
            const rect = wrapper.getBoundingClientRect();
            if (rect.top < 0 || rect.left < 0 || rect.right > window.innerWidth || rect.bottom > window.innerHeight) {
                wrapper.style.transform = 'translate(0px, 0px)';
                currentTransformX = 0;
                currentTransformY = 0;
                wrapper.style.left = 'auto';
                wrapper.style.top = 'auto';
                wrapper.style.right = bottomOffset;
                wrapper.style.bottom = '20px';
            }
        });

        // --- Minimize / Restore ---
        function toggleMinimize() {
            if (_isMaximized) toggleMaximize();
            _isMinimized = !_isMinimized;
            if (_isMinimized) {
                wrapper.classList.add('minimized');
                wrapper.style.width = minimizedWidth;
                if (minimizeBtn) minimizeBtn.innerHTML = '<span class="material-icons">crop_square</span>';
                // Snap to bottom corner
                wrapper.style.transform = '';
                wrapper.style.left = 'auto';
                wrapper.style.top = 'auto';
                wrapper.style.right = bottomOffset;
                wrapper.style.bottom = '0';
                currentTransformX = 0; currentTransformY = 0;
                offsetX = 0; offsetY = 0;
                if (onMinimize) onMinimize();
            } else {
                wrapper.classList.remove('minimized');
                if (minimizeBtn) minimizeBtn.innerHTML = '<span class="material-icons">horizontal_rule</span>';
                wrapper.style.bottom = '20px';
                if (onRestore) onRestore();
            }
        }

        // --- Maximize ---
        function toggleMaximize() {
            if (_isMinimized) toggleMinimize();
            _isMaximized = !_isMaximized;
            if (_isMaximized) {
                wrapper.classList.add('fullscreen');
                if (maximizeBtn) maximizeBtn.innerHTML = '<span class="material-icons">fullscreen_exit</span>';
            } else {
                wrapper.classList.remove('fullscreen');
                if (maximizeBtn) maximizeBtn.innerHTML = '<span class="material-icons">fullscreen</span>';
            }
        }

        // --- Close ---
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                wrapper.style.display = 'none';
                _isMinimized = false;
                _isMaximized = false;
                wrapper.classList.remove('minimized', 'fullscreen');
                wrapper.style.transform = '';
                wrapper.style.left = 'auto';
                wrapper.style.top = 'auto';
                wrapper.style.right = bottomOffset;
                wrapper.style.bottom = '20px';
                currentTransformX = 0; currentTransformY = 0;
                offsetX = 0; offsetY = 0;
                if (onClose) onClose();
            });
        }

        if (minimizeBtn) {
            minimizeBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleMinimize(); });
        }

        if (maximizeBtn) {
            maximizeBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleMaximize(); });
        }

        // Click on minimized header to restore
        header.addEventListener('click', (e) => {
            if (e.target.closest('.admin-console-btn')) return;
            if (_isMinimized) toggleMinimize();
        });

        // --- Public API ---
        return {
            show() {
                bringToFront(wrapper);
                wrapper.style.display = 'flex';
            },
            hide() {
                wrapper.style.display = 'none';
                if (onClose) onClose();
            },
            flashIfVisible() {
                if (wrapper.style.display === 'flex' || wrapper.style.display === 'block') {
                    bringToFront(wrapper);
                    wrapper.style.opacity = '0.5';
                    setTimeout(() => wrapper.style.opacity = '1', 200);
                    return true;
                }
                return false;
            },
            isVisible() {
                return wrapper.style.display === 'flex' || wrapper.style.display === 'block';
            },
            get isMinimized() { return _isMinimized; }
        };
    }

    // =========================================================================
    // --- Easter Egg: Logo (Admin Logs) ---
    // =========================================================================
    const logo = document.querySelector('.header-left img');
    if (!logo) return;

    let logoClickCount = 0;
    let logoClickTimer = null;
    const REQUIRED_CLICKS = 10;
    const CLICK_TIMEOUT_MS = 2000;

    logo.style.cursor = 'pointer';
    logo.addEventListener('click', () => {
        logoClickCount++;
        clearTimeout(logoClickTimer);
        if (logoClickCount >= REQUIRED_CLICKS) {
            logoClickCount = 0;
            toggleAdminConsole();
        } else {
            logoClickTimer = setTimeout(() => { logoClickCount = 0; }, CLICK_TIMEOUT_MS);
        }
    });

    // =========================================================================
    // --- Easter Egg: Lock Icon (Stop All Processes) ---
    // =========================================================================
    const lockIcon = document.querySelector('.lock-icon');
    if (lockIcon) {
        let lockClickCount = 0;
        let lockClickTimer = null;
        lockIcon.style.cursor = 'pointer';
        lockIcon.addEventListener('click', () => {
            lockClickCount++;
            clearTimeout(lockClickTimer);
            if (lockClickCount >= REQUIRED_CLICKS) {
                lockClickCount = 0;
                toggleStopAllConsole();
            } else {
                lockClickTimer = setTimeout(() => { lockClickCount = 0; }, CLICK_TIMEOUT_MS);
            }
        });
    }

    // =========================================================================
    // --- FLOATING WINDOW 1: Admin Server Logs Console ---
    // =========================================================================
    const consoleWrapper = document.createElement('div');
    consoleWrapper.className = 'admin-console-wrapper';
    consoleWrapper.id = 'admin-console';
    consoleWrapper.innerHTML = `
        <div class="admin-console-header" id="admin-console-header">
            <div class="admin-console-title">
                <span class="material-icons">terminal</span>
                Live Server Logs
            </div>
            <div class="admin-console-controls">
                <button class="admin-console-btn minimize" id="admin-console-minimize" title="Minimize/Restore">
                    <span class="material-icons">remove</span>
                </button>
                <button class="admin-console-btn" id="admin-console-maximize" title="Maximize">
                    <span class="material-icons">fullscreen</span>
                </button>
                <button class="admin-console-btn close" id="admin-console-close" title="Close">
                    <span class="material-icons">close</span>
                </button>
            </div>
        </div>
        <div class="admin-console-toolbar" style="display:flex;align-items:center;gap:8px;">
            <input type="text" class="admin-search-input" id="admin-search-input"
                   placeholder="Search logs (e.g., 'ERROR', 'INFO')..." style="flex:1;">
            <span id="admin-logs-counter"
                  style="font-size:0.75em;color:#888;white-space:nowrap;padding:2px 6px;background:#1e1e1e;border-radius:4px;border:1px solid #333;"
                  title="Lines currently shown / total lines in log files">— / —</span>
        </div>
        <div id="admin-console-body-wrap" style="position:relative;flex:1;overflow:hidden;display:flex;flex-direction:column;">
            <div class="admin-console-body" id="admin-console-body"></div>
            <!-- Jump to Latest button — visible only when scrolled up -->
            <button id="admin-jump-latest"
                    style="display:none;position:absolute;bottom:10px;right:12px;z-index:10;
                           background:#0d6efd;color:#fff;border:none;border-radius:20px;
                           padding:6px 14px;font-size:0.8em;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.4);
                           display:none;align-items:center;gap:4px;">
                <span class="material-icons" style="font-size:1em;vertical-align:middle;">arrow_downward</span>
                Jump to Latest
            </button>
        </div>
    `;
    document.body.appendChild(consoleWrapper);

    const logsHeader = document.getElementById('admin-console-header');
    const logsMinimizeBtn = document.getElementById('admin-console-minimize');
    const logsMaximizeBtn = document.getElementById('admin-console-maximize');
    const logsCloseBtn = document.getElementById('admin-console-close');
    const logsBody = document.getElementById('admin-console-body');
    const logsSearchInput = document.getElementById('admin-search-input');
    const logsCounter = document.getElementById('admin-logs-counter');
    const jumpLatestBtn = document.getElementById('admin-jump-latest');

    let isPolling = false;
    let logsCache = [];
    let isLoadingOlder = false;
    // olderLogsOffset: how many lines from the END of the combined file we have already fetched
    // (only updated by startPolling initial fetch + fetchOlderLogs — NOT by live SSE lines)
    let olderLogsOffset = 0;
    let totalServerLines = 0;
    let eventSource = null;
    const MAX_LOG_LINES = 5000;
    const BATCH_SIZE = 1000;

    const logsWindow = setupFloatingWindow({
        wrapper: consoleWrapper,
        header: logsHeader,
        minimizeBtn: logsMinimizeBtn,
        maximizeBtn: logsMaximizeBtn,
        closeBtn: logsCloseBtn,
        bottomOffset: '340px',  // minimized: sits left of Stop-All panel (300px wide + 20px margin + 20px gap)
        onClose: stopPolling,
        onRestore: () => scrollToBottom(),
    });

    function toggleAdminConsole() {
        if (!logsWindow.isVisible()) {
            logsWindow.show();
            startPolling();
        } else {
            logsWindow.flashIfVisible();
        }
    }

    // --- Search ---
    logsSearchInput.addEventListener('input', () => renderLogs(false));

    // --- Jump to Latest button ---
    jumpLatestBtn.addEventListener('click', () => {
        scrollToBottom();
        jumpLatestBtn.style.display = 'none';
    });

    // --- Infinite scroll (older logs) + Jump to Latest visibility ---
    logsBody.addEventListener('scroll', () => {
        const isNearTop = logsBody.scrollTop <= 10;
        const isNearBottom = logsBody.scrollHeight - logsBody.scrollTop - logsBody.clientHeight < 60;

        // Show / hide Jump to Latest
        jumpLatestBtn.style.display = isNearBottom ? 'none' : 'flex';

        // Load older logs when scrolled to top
        if (isNearTop && !isLoadingOlder && olderLogsOffset < totalServerLines) {
            fetchOlderLogs();
        }
    });

    // Helper: update line counter badge
    function updateCounter() {
        const showing = logsCache.length;
        const total = totalServerLines || 0;
        logsCounter.textContent = `${showing.toLocaleString()} / ${total.toLocaleString()} lines`;
    }

    function startPolling() {
        if (isPolling) return;
        isPolling = true;
        logsCounter.textContent = 'Loading...';
        fetch(`/api/server_logs?offset_line=0&limit=${BATCH_SIZE}`)
            .then(r => r.json())
            .then(data => {
                if (data.logs) {
                    logsCache = data.logs;
                    olderLogsOffset = data.returned_count || 0;
                    totalServerLines = data.total_lines || 0;
                    updateCounter();
                    renderLogs(true);
                }
                openStream();
            })
            .catch(err => {
                logsCache = [`[Live Viewer] Network error fetching initial logs: ${err.message}`];
                updateCounter();
                renderLogs(false);
            });
    }

    function openStream() {
        if (eventSource) return;
        eventSource = new EventSource('/api/server_logs/stream');
        eventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);
                const wasScrolledToBottom = logsBody.scrollHeight - logsBody.clientHeight <= logsBody.scrollTop + 20;
                logsCache.push(data.line);
                totalServerLines++;
                manageMemory();
                updateCounter();
                renderLogs(wasScrolledToBottom);
            } catch (e) {
                console.error("SSE Parse error", e);
            }
        };
        eventSource.onerror = function () {
            console.log("SSE Stream disconnected, browser will retry...");
        };
    }

    function stopPolling() {
        isPolling = false;
        if (eventSource) { eventSource.close(); eventSource = null; }
    }

    function fetchOlderLogs() {
        isLoadingOlder = true;
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'logs-loading-older';
        loadingDiv.innerText = "⏳ Loading older logs...";
        loadingDiv.style.cssText = 'text-align:center;color:#888;font-style:italic;padding:6px;';
        logsBody.insertBefore(loadingDiv, logsBody.firstChild);

        fetch(`/api/server_logs?offset_line=${olderLogsOffset}&limit=${BATCH_SIZE}`)
            .then(r => r.json())
            .then(data => {
                const indicator = document.getElementById('logs-loading-older');
                if (indicator) indicator.remove();

                if (data.logs && data.logs.length > 0) {
                    const oldScrollHeight = logsBody.scrollHeight;
                    logsCache = data.logs.concat(logsCache);
                    olderLogsOffset += data.returned_count;
                    totalServerLines = data.total_lines;
                    manageMemory();
                    updateCounter();
                    renderLogs(false);
                    logsBody.scrollTop = logsBody.scrollHeight - oldScrollHeight;
                } else {
                    // All historical logs loaded — show a banner at the very top
                    const allLoadedDiv = document.getElementById('logs-all-loaded');
                    if (!allLoadedDiv) {
                        const banner = document.createElement('div');
                        banner.id = 'logs-all-loaded';
                        banner.style.cssText = 'text-align:center;color:#28a745;font-size:0.82em;padding:8px;border-bottom:1px solid #333;font-style:italic;';
                        banner.textContent = '✅ Beginning of logs reached. All historical records are shown.';
                        logsBody.insertBefore(banner, logsBody.firstChild);
                    }
                }
            })
            .catch(err => console.error("Error loading older logs:", err))
            .finally(() => { isLoadingOlder = false; });
    }

    function manageMemory() {
        if (logsCache.length > MAX_LOG_LINES) {
            const overage = logsCache.length - MAX_LOG_LINES;
            logsCache = logsCache.slice(overage);
        }
    }

    function renderLogs(forceScrollToBottom = false) {
        const searchTerm = logsSearchInput.value.toLowerCase().trim();
        let html = '';
        logsCache.forEach(line => {
            if (line.includes('/api/server_logs')) return;
            const lowerLine = line.toLowerCase();
            const isMatch = searchTerm !== '' && lowerLine.includes(searchTerm);
            if (searchTerm === '' || isMatch) {
                let safeLine = line.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                if (searchTerm !== '' && isMatch) {
                    const regex = new RegExp(searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                    safeLine = safeLine.replace(regex, m => `<span style="background-color:yellow;color:black;">${m}</span>`);
                }
                html += `<div class="admin-log-line ${isMatch && searchTerm !== '' ? 'search-match' : ''}">${safeLine}</div>`;
            }
        });
        if (html === '' && searchTerm !== '') {
            html = '<div style="color:#888;text-align:center;padding:20px;">No logs match your search.</div>';
        }
        const isAtBottom = logsBody.scrollHeight - logsBody.clientHeight <= logsBody.scrollTop + 20;
        logsBody.innerHTML = html;
        if ((forceScrollToBottom || isAtBottom) && !logsWindow.isMinimized && !isLoadingOlder) {
            scrollToBottom();
        }
    }

    function scrollToBottom() { logsBody.scrollTop = logsBody.scrollHeight; }

    // =========================================================================
    // --- FLOATING WINDOW 2: Stop All Processes ---
    // =========================================================================
    const stopAllWrapper = document.createElement('div');
    stopAllWrapper.className = 'admin-console-wrapper';
    stopAllWrapper.id = 'stop-all-console';
    stopAllWrapper.style.cssText = 'bottom:20px;right:20px;width:560px;height:420px;';
    stopAllWrapper.innerHTML = `
        <div class="admin-console-header" id="stopall-header">
            <div class="admin-console-title">
                <span class="material-icons" style="color:#dc3545;">stop_circle</span>
                Active Background Processes
            </div>
            <div class="admin-console-controls">
                <button class="admin-console-btn minimize" id="stopall-minimize" title="Minimize/Restore">
                    <span class="material-icons">horizontal_rule</span>
                </button>
                <button class="admin-console-btn close" id="stopall-close" title="Close Window">
                    <span class="material-icons">close</span>
                </button>
            </div>
        </div>
        <div class="admin-console-body" id="stopall-body" style="background:#f8f9fa;color:#333;padding:15px;flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:0;">

            <!-- Job list -->
            <p style="margin:0 0 10px;color:#555;font-size:0.88em;">Scripts currently running on the server:</p>
            <div id="stopall-jobs-list" style="flex:1;overflow-y:auto;margin-bottom:10px;">
                <!-- Jobs populated by JS -->
            </div>

            <!-- Inline confirmation banner (hidden by default) -->
            <div id="stopall-confirm-banner" style="display:none;background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px 14px;margin-bottom:10px;">
                <p style="margin:0 0 10px;font-weight:600;color:#856404;font-size:0.92em;">
                    ⚠ Are you sure you want to stop ALL running processes?
                </p>
                <p style="margin:0 0 12px;color:#666;font-size:0.82em;">This will forcefully terminate all active scripts for all users and cannot be undone.</p>
                <div style="display:flex;justify-content:flex-end;gap:10px;">
                    <button id="stopall-confirm-cancel" class="btn-secondary" style="padding:6px 14px;font-size:0.85em;">Cancel</button>
                    <button id="stopall-confirm-proceed" class="btn-primary" style="background:#dc3545;padding:6px 14px;font-size:0.85em;">Stop All</button>
                </div>
            </div>

            <!-- Footer buttons -->
            <div style="display:flex;justify-content:flex-end;gap:10px;padding-top:10px;border-top:1px solid #dee2e6;flex-shrink:0;">
                <button id="stopall-dismiss-btn" class="btn-secondary" style="padding:8px 16px;">Dismiss</button>
                <button id="stopall-closeall-btn" class="btn-primary" style="background-color:#dc3545;padding:8px 16px;">Close All</button>
            </div>
        </div>
    `;
    document.body.appendChild(stopAllWrapper);

    const stopAllHeader = document.getElementById('stopall-header');
    const stopAllMinimizeBtn = document.getElementById('stopall-minimize');
    const stopAllCloseBtn = document.getElementById('stopall-close');   // window X
    const stopAllJobsList = document.getElementById('stopall-jobs-list');
    const stopAllConfirmBanner = document.getElementById('stopall-confirm-banner');
    const stopConfirmCancelBtn = document.getElementById('stopall-confirm-cancel');
    const stopConfirmProceedBtn = document.getElementById('stopall-confirm-proceed');
    const stopAllDismissBtn = document.getElementById('stopall-dismiss-btn');
    const stopAllCloseAllBtn = document.getElementById('stopall-closeall-btn');

    // Helper: hide the confirmation banner
    function hideConfirmBanner() {
        stopAllConfirmBanner.style.display = 'none';
        stopConfirmProceedBtn.disabled = false;
        stopConfirmProceedBtn.textContent = 'Stop All';
    }

    // Helper: update the Close All button state based on job count
    function syncCloseAllBtn(hasJobs) {
        stopAllCloseAllBtn.disabled = !hasJobs;
        stopAllCloseAllBtn.style.opacity = hasJobs ? '1' : '0.5';
        stopAllCloseAllBtn.style.cursor = hasJobs ? 'pointer' : 'not-allowed';
    }

    const stopAllWindow = setupFloatingWindow({
        wrapper: stopAllWrapper,
        header: stopAllHeader,
        minimizeBtn: stopAllMinimizeBtn,
        // X button: if jobs running, show confirm; else just close
        closeBtn: null,        // we wire it manually below
        bottomOffset: '20px',
        minimizedWidth: '300px',
    });

    // Wire window X button manually so we can intercept
    stopAllCloseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const hasJobs = stopAllJobsList.querySelectorAll('li').length > 0;
        if (hasJobs) {
            // Show the confirmation banner instead of closing silently
            stopAllConfirmBanner.style.display = 'block';
            stopAllConfirmBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            stopAllWindow.hide();
        }
    });

    // ---- Load jobs function ----
    function loadActiveJobs() {
        hideConfirmBanner();
        stopAllJobsList.innerHTML = '<div style="text-align:center;color:#666;padding:20px;">Fetching running processes...</div>';
        syncCloseAllBtn(false);

        fetch('/api/server/active_jobs')
            .then(res => res.json())
            .then(data => {
                const jobs = data.jobs || [];
                if (jobs.length === 0) {
                    stopAllJobsList.innerHTML = '<div style="text-align:center;color:#28a745;padding:30px;font-weight:500;">✅ No background processes are currently running.</div>';
                    syncCloseAllBtn(false);
                    return;
                }

                // Build job rows with individual Cancel button
                let html = '<ul style="list-style-type:none;padding:0;margin:0;">';
                jobs.forEach(job => {
                    html += `
                        <li data-client-id="${job.client_id}"
                            style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid #e0e0e0;background:#fff;margin-bottom:5px;border-radius:6px;gap:10px;">
                            <div style="flex:1;min-width:0;">
                                <div style="font-weight:600;color:#333;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${job.script_name}">${job.script_name}</div>
                                <div style="font-size:0.82em;color:#666;">
                                    User <strong>${job.user}</strong> · Tenant <strong>${job.tenant}</strong>
                                </div>
                                <div style="font-size:0.72em;color:#aaa;margin-top:2px;">ID: ${job.client_id}</div>
                            </div>
                            <button class="cancel-job-btn btn-secondary"
                                    data-client-id="${job.client_id}"
                                    style="flex-shrink:0;padding:5px 12px;font-size:0.8em;border-radius:4px;background:#fff;border:1px solid #dc3545;color:#dc3545;cursor:pointer;white-space:nowrap;">
                                Cancel
                            </button>
                        </li>`;
                });
                html += '</ul>';
                stopAllJobsList.innerHTML = html;
                syncCloseAllBtn(true);

                // Wire individual Cancel buttons
                stopAllJobsList.querySelectorAll('.cancel-job-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const clientId = btn.getAttribute('data-client-id');
                        btn.disabled = true;
                        btn.textContent = 'Stopping…';
                        fetch(`/api/stop/${clientId}`, { method: 'POST' })
                            .then(res => res.json())
                            .then(() => {
                                // Remove the row and refresh after a short delay
                                const li = btn.closest('li');
                                if (li) {
                                    li.style.opacity = '0.4';
                                    li.style.pointerEvents = 'none';
                                }
                                setTimeout(() => loadActiveJobs(), 1500);
                            })
                            .catch(err => {
                                console.error('Cancel job error:', err);
                                btn.disabled = false;
                                btn.textContent = 'Cancel';
                            });
                    });
                });
            })
            .catch(err => {
                console.error('Failed to fetch active jobs:', err);
                stopAllJobsList.innerHTML = '<div style="text-align:center;color:#dc3545;padding:20px;">❌ Error fetching active processes. Please try again.</div>';
                syncCloseAllBtn(false);
            });
    }

    // ---- Toggle Stop All console ----
    function toggleStopAllConsole() {
        if (!stopAllWindow.isVisible()) {
            stopAllWindow.show();
            loadActiveJobs();
        } else {
            if (!stopAllWindow.flashIfVisible()) {
                stopAllWindow.show();
                loadActiveJobs();
            }
        }
    }

    // ---- Dismiss button: just hide the panel ----
    stopAllDismissBtn.addEventListener('click', () => {
        hideConfirmBanner();
        stopAllWindow.hide();
    });

    // ---- Close All button: show confirmation banner ----
    stopAllCloseAllBtn.addEventListener('click', () => {
        if (stopAllCloseAllBtn.disabled) return;
        stopAllConfirmBanner.style.display = 'block';
        stopAllConfirmBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    // ---- Confirmation Banner — Cancel ----
    stopConfirmCancelBtn.addEventListener('click', () => hideConfirmBanner());

    // ---- Confirmation Banner — Stop All (confirmed) ----
    stopConfirmProceedBtn.addEventListener('click', () => {
        stopConfirmProceedBtn.disabled = true;
        stopConfirmProceedBtn.textContent = 'Stopping…';

        fetch('/api/server/stop_all', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                hideConfirmBanner();
                // Refresh the list to show all stopped
                loadActiveJobs();
            })
            .catch(err => {
                console.error('Error stopping all jobs:', err);
                stopConfirmProceedBtn.disabled = false;
                stopConfirmProceedBtn.textContent = 'Stop All';
            });
    });

});


