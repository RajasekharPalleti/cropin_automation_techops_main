/**
 * admin_logs.js — Admin Server Logs Live Viewer (Easter Egg)
 *
 * Provides a floating console window when the user clicks the Cropin logo 10 times.
 * - Draggable console header.
 * - Minimize/Restore functionality.
 * - Auto-scroll on new logs.
 * - Continuous polling of /api/server_logs.
 * - Search/Filter input field.
 */

document.addEventListener('DOMContentLoaded', () => {

    const logo = document.querySelector('.header-left img');
    if (!logo) return;

    // --- Easter Egg Tracking ---
    let clickCount = 0;
    let clickTimer = null;
    const requiredClicks = 10;
    const clickTimeoutMs = 2000; // time window to perform 10 clicks

    logo.style.cursor = 'pointer'; // Make it look clickable

    logo.addEventListener('click', () => {
        clickCount++;
        clearTimeout(clickTimer);

        if (clickCount >= requiredClicks) {
            clickCount = 0; // reset
            toggleAdminConsole();
        } else {
            clickTimer = setTimeout(() => {
                clickCount = 0; // reset if too slow
            }, clickTimeoutMs);
        }
    });

    // --- Create Console DOM Elements ---
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
        <div class="admin-console-toolbar">
            <input type="text" class="admin-search-input" id="admin-search-input" placeholder="Search logs (e.g., 'ERROR', 'INFO')...">
        </div>
        <div class="admin-console-body" id="admin-console-body">
            <!-- Logs will be populated here -->
        </div>
    `;

    document.body.appendChild(consoleWrapper);

    const header = document.getElementById('admin-console-header');
    const minimizeBtn = document.getElementById('admin-console-minimize');
    const maximizeBtn = document.getElementById('admin-console-maximize');
    const closeBtn = document.getElementById('admin-console-close');
    const body = document.getElementById('admin-console-body');
    const searchInput = document.getElementById('admin-search-input');

    let isPolling = false;
    let pollInterval = null;
    let logsCache = [];
    let isMinimized = false;
    let isMaximized = false;

    // --- Console State Management ---
    function toggleAdminConsole() {
        if (consoleWrapper.style.display === 'none' || consoleWrapper.style.display === '') {
            consoleWrapper.style.display = 'flex';
            startPolling();
        } else {
            // If already open, just flash it to show it received the command
            consoleWrapper.style.opacity = '0.5';
            setTimeout(() => consoleWrapper.style.opacity = '1', 200);
        }
    }

    function closeConsole() {
        consoleWrapper.style.display = 'none';
        stopPolling();
    }

    function toggleMinimize() {
        if (isMaximized) toggleMaximize(); // cancel maximize if shrinking to minimize
        isMinimized = !isMinimized;
        if (isMinimized) {
            consoleWrapper.classList.add('minimized');
            minimizeBtn.innerHTML = '<span class="material-icons">crop_square</span>'; // Restore icon

            // Revert any drag translations so it snaps cleanly to the bottom right
            consoleWrapper.style.transform = '';
            consoleWrapper.style.left = 'auto';
            consoleWrapper.style.top = 'auto';
            consoleWrapper.style.right = '20px';
            consoleWrapper.style.bottom = '0';
            currentTransformX = 0;
            currentTransformY = 0;
            offsetX = 0;
            offsetY = 0;
        } else {
            consoleWrapper.classList.remove('minimized');
            minimizeBtn.innerHTML = '<span class="material-icons">remove</span>';
            // Give it some breathing room from the very bottom when restored
            consoleWrapper.style.bottom = '20px';
            // Auto scroll to bottom when restored if at bottom
            scrollToBottom();
        }
    }

    function toggleMaximize() {
        if (isMinimized) toggleMinimize(); // restore first if minimized
        isMaximized = !isMaximized;
        if (isMaximized) {
            consoleWrapper.classList.add('fullscreen');
            maximizeBtn.innerHTML = '<span class="material-icons">fullscreen_exit</span>';
        } else {
            consoleWrapper.classList.remove('fullscreen');
            maximizeBtn.innerHTML = '<span class="material-icons">fullscreen</span>';
            scrollToBottom();
        }
    }

    closeBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent drag
        closeConsole();
        isMinimized = false;
        isMaximized = false;
        consoleWrapper.classList.remove('minimized', 'fullscreen');
    });

    minimizeBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent drag
        toggleMinimize();
    });

    maximizeBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent drag
        toggleMaximize();
    });

    // Clicking header of minimized window restores it, etc.
    header.addEventListener('click', (e) => {
        if (e.target.closest('.admin-console-btn')) return;
        if (isMinimized) toggleMinimize();
    });

    let currentOffset = 0;
    let totalServerLines = 0;
    let isLoadingOlder = false;
    const MAX_LOG_LINES = 5000;
    const BATCH_SIZE = 1000;

    // --- Search Functionality ---
    searchInput.addEventListener('input', () => {
        renderLogs(false); // Re-render from cache with new search filter, no auto-scroll
    });

    // --- Scroll Event for Infinite Loading ---
    body.addEventListener('scroll', () => {
        if (body.scrollTop <= 10 && !isLoadingOlder && currentOffset < totalServerLines) {
            fetchOlderLogs();
        }
    });

    let eventSource = null;

    // --- SSE Stream Logic ---
    function startPolling() {
        if (isPolling) return;
        isPolling = true;

        // Step 1: Fetch initial snapshot (last 1000 lines)
        fetch(`/api/server_logs?offset_line=0&limit=${BATCH_SIZE}`)
            .then(r => r.json())
            .then(data => {
                if (data.logs) {
                    logsCache = data.logs;
                    currentOffset = data.returned_count;
                    totalServerLines = data.total_lines;
                    renderLogs(true);
                }

                // Step 2: Open SSE stream for new lines
                openStream();
            })
            .catch(err => {
                logsCache = [`[Live Viewer] Network error fetching initial logs: ${err.message}`];
                renderLogs(false);
            });
    }

    function openStream() {
        if (eventSource) return;
        eventSource = new EventSource('/api/server_logs/stream');

        eventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);
                const newLine = data.line;

                // Check scroll position BEFORE updating the DOM
                const wasScrolledToBottom = body.scrollHeight - body.clientHeight <= body.scrollTop + 20;

                logsCache.push(newLine + "\\n"); // Ensure newline is appended just like python readline returns 
                currentOffset++; // We read one more line forward
                totalServerLines++;

                manageMemory();

                // Only force scroll to bottom on new logs if user was already at the bottom
                renderLogs(wasScrolledToBottom);

            } catch (e) {
                console.error("SSE Parse error", e);
            }
        };

        eventSource.onerror = function () {
            // Reconnect logic is handled natively by browser EventSource automatically
            console.log("SSE Stream disconnected, browser will retry...");
        };
    }

    function stopPolling() {
        isPolling = false;
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }

    // Fetches older logs (prepended to the top)
    function fetchOlderLogs() {
        isLoadingOlder = true;

        // Show loading indicator briefly visually
        const loadingDiv = document.createElement('div');
        loadingDiv.innerText = "Loading older logs...";
        loadingDiv.style.textAlign = 'center';
        loadingDiv.style.color = '#888';
        loadingDiv.style.fontStyle = 'italic';
        body.insertBefore(loadingDiv, body.firstChild);

        fetch(`/api/server_logs?offset_line=${currentOffset}&limit=${BATCH_SIZE}`)
            .then(r => r.json())
            .then(data => {
                if (data.logs && data.logs.length > 0) {
                    // Record current scroll height before adding elements to preserve scroll position
                    const oldScrollHeight = body.scrollHeight;

                    logsCache = data.logs.concat(logsCache);
                    currentOffset += data.returned_count;
                    totalServerLines = data.total_lines; // in case it grew

                    manageMemory();

                    // Re-render and restore scroll
                    renderLogs(false);
                    body.scrollTop = body.scrollHeight - oldScrollHeight;
                } else {
                    // Remove loading div visually since there was nothing
                    if (body.firstChild === loadingDiv) body.removeChild(loadingDiv);
                }
            })
            .catch(err => console.error("Error loading older logs:", err))
            .finally(() => {
                isLoadingOlder = false;
            });
    }

    function manageMemory() {
        if (logsCache.length > MAX_LOG_LINES) {
            // Trim from the top (oldest logs) if we exceed our safety limit
            const overage = logsCache.length - MAX_LOG_LINES;
            logsCache = logsCache.slice(overage);
            // We do NOT modify currentOffset because offset tracks how far back we've read from the file.
            // If we trimmed memory from the top, scrolling up again will just hit the cache limit constraint 
            // but we accept that to save browser memory.
        }
    }

    function renderLogs(forceScrollToBottom = false) {
        const searchTerm = searchInput.value.toLowerCase().trim();
        let html = '';

        logsCache.forEach(line => {
            // Filter out the polling logs from the UI entirely
            if (line.includes('/api/server_logs')) return;

            const lowerLine = line.toLowerCase();
            let isMatch = searchTerm !== '' && lowerLine.includes(searchTerm);

            // Only show matching lines if search is active, OR show all if no search
            if (searchTerm === '' || isMatch) {
                // simple sanitize
                let safeLine = line.replace(/</g, "&lt;").replace(/>/g, "&gt;");

                // Highlight matches if there is a search term
                if (searchTerm !== '' && isMatch) {
                    // This simple regex highlights the search term case-insensitively
                    const regex = new RegExp(searchTerm.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'gi');
                    safeLine = safeLine.replace(regex, match => `<span style="background-color: yellow; color: black;">${match}</span>`);
                }

                html += `<div class="admin-log-line ${isMatch && searchTerm !== '' ? 'search-match' : ''}">${safeLine}</div>`;
            }
        });

        if (html === '' && searchTerm !== '') {
            html = '<div style="color: #888; text-align: center; padding: 20px;">No logs match your search.</div>';
        }

        const isScrolledToBottom = body.scrollHeight - body.clientHeight <= body.scrollTop + 20;

        body.innerHTML = html;

        // Auto-scroll logic:
        if (forceScrollToBottom && !isMinimized) {
            scrollToBottom();
        } else if (isScrolledToBottom && !isMinimized && !isLoadingOlder) { // Prevent snap down while loading old logs
            scrollToBottom();
        }
    }


    function scrollToBottom() {
        body.scrollTop = body.scrollHeight;
    }

    // --- Drag functionality ---
    let isDragging = false;
    let initialX, initialY;
    let offsetX = 0, offsetY = 0;

    // Store original CSS position string to track current translation
    let currentTransformX = 0;
    let currentTransformY = 0;

    header.addEventListener('mousedown', (e) => {
        if (isMinimized || isMaximized || e.target.closest('.admin-console-btn')) return; // Don't drag if min/maxed or clicking buttons

        isDragging = true;
        initialX = e.clientX;
        initialY = e.clientY;

        // Disable text selection while dragging
        document.body.style.userSelect = 'none';

        // Remove bottom/right pinning and switch to transform-based moving for smoothness
        const rect = consoleWrapper.getBoundingClientRect();

        if (consoleWrapper.style.bottom !== 'auto') {
            // First time dragging: freeze current computed position
            consoleWrapper.style.bottom = 'auto';
            consoleWrapper.style.right = 'auto';
            consoleWrapper.style.left = rect.left + 'px';
            consoleWrapper.style.top = rect.top + 'px';

            // Re-read initial positions based on explicit left/top
            currentTransformX = 0;
            currentTransformY = 0;
        }

        consoleWrapper.style.transition = 'none'; // Disable transition during drag
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        e.preventDefault();

        const dx = e.clientX - initialX;
        const dy = e.clientY - initialY;

        offsetX = currentTransformX + dx;
        offsetY = currentTransformY + dy;

        consoleWrapper.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;

        // Save current transform state
        currentTransformX = offsetX;
        currentTransformY = offsetY;

        document.body.style.userSelect = '';

        // Re-enable specific transitions
        consoleWrapper.style.transition = 'width 0.3s, height 0.3s, bottom 0.3s, right 0.3s';

        // Prevent window from getting lost off-screen
        const rect = consoleWrapper.getBoundingClientRect();
        if (rect.top < 0 || rect.left < 0 || rect.right > window.innerWidth || rect.bottom > window.innerHeight) {
            // Reset position if dragged way out of bounds
            consoleWrapper.style.transform = 'translate(0px, 0px)';
            currentTransformX = 0;
            currentTransformY = 0;
            consoleWrapper.style.left = 'auto';
            consoleWrapper.style.top = 'auto';
            consoleWrapper.style.right = '20px';
            consoleWrapper.style.bottom = '20px';
        }
    });

});
