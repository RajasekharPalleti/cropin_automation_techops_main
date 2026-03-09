/**
 * sse.js — Server-Sent Events & Batched Log Rendering
 *
 * Manages the EventSource connection for real-time log streaming.
 * Uses requestAnimationFrame batching to prevent UI freezes when
 * logs arrive faster than the browser can render them.
 *
 * Depends on (window globals set by earlier modules):
 *   window.getClientId()     — from session.js
 *   window.releaseWakeLock() — from wake_lock.js
 *
 * Exposes:
 *   window.connectSSE(onOpen?)  — open/resume SSE connection
 *   window.closeSSE()           — close connection immediately
 *   window.pushToLogBuffer(msg) — push a message into the render queue
 */

document.addEventListener('DOMContentLoaded', () => {

    let evtSource = null;
    let logBuffer = [];
    let isRenderPending = false;

    // DOM refs — resolved once at init
    const consoleBox = document.getElementById('console-box');
    const consoleContent = document.getElementById('console-content');
    const statusArea = document.getElementById('status-area');

    // Run / Stop buttons are created by execution.js but accessible by ID
    function getRunBtn() { return document.getElementById('run-script-btn'); }
    function getStopBtn() { return document.getElementById('stop-script-btn'); }

    // ----------------------------------------------------------------
    // Native Desktop Notifications wrapper
    // ----------------------------------------------------------------
    function notifyUser(title, options = {}) {
        if (!("Notification" in window)) return;

        if (Notification.permission === "granted") {
            new Notification(title, { icon: '/static/images/logo.png', ...options });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    new Notification(title, { icon: '/static/images/logo.png', ...options });
                }
            });
        }
    }

    // ----------------------------------------------------------------
    // Batched log renderer — processes up to 100 messages per frame
    // ----------------------------------------------------------------
    function flushLogs() {
        if (logBuffer.length === 0) {
            isRenderPending = false;
            return;
        }

        const runBtn = getRunBtn();
        const stopBtn = getStopBtn();
        const fragment = document.createDocumentFragment();
        const batch = logBuffer.splice(0, 100);

        batch.forEach(msgData => {

            // --- Job completed ---
            if (msgData.startsWith('JOB_COMPLETED::')) {
                const filename = msgData.split('::')[1];

                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = '#00ff00';
                line.textContent = '> Execution Finished. Downloading ' + filename + '...';
                fragment.appendChild(line);

                sessionStorage.setItem('is_script_running', 'false');
                if (window.releaseWakeLock) window.releaseWakeLock();
                notifyUser('Script Completed', { body: `Script automation completed and ${filename} is successfully downloaded in downloads folder.` });

                setTimeout(() => {
                    window.location.href = '/api/download/' + encodeURIComponent(filename);
                    if (statusArea) statusArea.innerHTML = '<div style="color: green;">Success! Check downloads.</div>';
                    if (runBtn) { runBtn.disabled = false; runBtn.innerHTML = '▶ Run Script'; }
                    if (stopBtn) stopBtn.style.display = 'none';
                    closeSSE();

                    const closeLine = document.createElement('div');
                    closeLine.className = 'console-line';
                    closeLine.style.color = 'green';
                    closeLine.textContent = '> Connection closed. Job Done.';
                    if (consoleContent) consoleContent.appendChild(closeLine);
                    if (consoleBox) consoleBox.scrollTop = consoleBox.scrollHeight;
                }, 0);
                return;
            }

            // --- Job failed ---
            if (msgData.startsWith('JOB_FAILED::')) {
                const errorMsg = msgData.split('::')[1];

                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = '#ff4444';
                line.textContent = '> ERROR: ' + errorMsg;
                fragment.appendChild(line);

                if (window.releaseWakeLock) window.releaseWakeLock();
                const scriptName = document.getElementById('selected-text') ? document.getElementById('selected-text').textContent : 'Script';
                notifyUser('Script Failed', { body: `Script automation failed for ${scriptName}. Error: ${errorMsg}` });

                setTimeout(() => {
                    if (statusArea) statusArea.innerHTML = '<div style="color: red;">Execution Failed</div>';
                    if (runBtn) { runBtn.disabled = false; runBtn.innerHTML = '▶ Run Script'; }
                    if (stopBtn) stopBtn.style.display = 'none';
                    sessionStorage.setItem('is_script_running', 'false');
                }, 0);
                return;
            }

            // --- Job stopped by user ---
            if (msgData === 'STOP_UI_NOW') {
                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = 'orange';
                line.textContent = '> JOB STOPPED SUCCESSFULLY. READY FOR NEW RUN.';
                fragment.appendChild(line);

                setTimeout(() => {
                    if (statusArea) statusArea.innerHTML = '<div style="color: Orange;">Job Stopped Successfully</div>';
                    if (runBtn) { runBtn.disabled = false; runBtn.innerHTML = '▶ Run Script'; }
                    if (stopBtn) stopBtn.style.display = 'none';
                    sessionStorage.setItem('is_script_running', 'false');

                    // Generate a fresh client ID for the next run
                    const newId = 'client_' + Math.random().toString(36).slice(2, 11);
                    if (window.setClientId) window.setClientId(newId);
                    console.log('New Client ID generated:', newId);
                }, 0);
                return;
            }

            // --- Job force-stopped by admin ---
            if (msgData.startsWith('JOB_STOPPED::')) {
                const reason = msgData.split('::')[1] || 'Closed forcefully by admin.';

                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = '#ff8c00';
                line.style.fontWeight = '600';
                line.textContent = '> ⚠ ADMIN ACTION: ' + reason + ' Script execution terminated.';
                fragment.appendChild(line);

                if (window.releaseWakeLock) window.releaseWakeLock();

                setTimeout(() => {
                    if (statusArea) statusArea.innerHTML = '<div style="color: #ff8c00; font-weight:600;">⚠ Stopped by Admin</div>';
                    if (runBtn) { runBtn.disabled = false; runBtn.innerHTML = '▶ Run Script'; }
                    if (stopBtn) stopBtn.style.display = 'none';
                    sessionStorage.setItem('is_script_running', 'false');

                    // Generate a fresh client ID for the next run
                    const newId = 'client_' + Math.random().toString(36).slice(2, 11);
                    if (window.setClientId) window.setClientId(newId);
                    console.log('New Client ID generated after admin stop:', newId);
                }, 0);
                return;
            }

            // --- Normal log line ---
            const logLine = document.createElement('div');
            logLine.className = 'console-line';
            logLine.textContent = '> ' + msgData;
            fragment.appendChild(logLine);
        });

        // Smart auto-scroll: check BEFORE appending
        const isNearBottom = consoleBox
            ? (consoleBox.scrollHeight - consoleBox.scrollTop - consoleBox.clientHeight < 150)
            : false;

        if (consoleContent) consoleContent.appendChild(fragment);
        if (isNearBottom && consoleBox) consoleBox.scrollTop = consoleBox.scrollHeight;

        if (logBuffer.length > 0) {
            requestAnimationFrame(flushLogs);
        } else {
            isRenderPending = false;
        }
    }

    // Expose so stop button in execution.js can trigger a flush
    window.flushLogsInstance = flushLogs;

    // ----------------------------------------------------------------
    // SSE connection
    // ----------------------------------------------------------------
    function connectSSE(onOpen = null) {
        if (evtSource && evtSource.readyState !== EventSource.CLOSED) return;

        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');
        console.log('Connecting SSE for logs...');
        evtSource = new EventSource('/api/logs/' + clientId);

        // Reset batch state on each new connection
        logBuffer = [];
        isRenderPending = false;
        window.flushLogsInstance = flushLogs;

        evtSource.onopen = () => {
            console.log('SSE Connected');
            if (onOpen) {
                onOpen();
                onOpen = null; // Prevent re-execution on reconnect
            }
        };

        evtSource.onmessage = (event) => {
            logBuffer.push(event.data);
            if (!isRenderPending) {
                isRenderPending = true;
                requestAnimationFrame(flushLogs);
            }
        };

        evtSource.onerror = (err) => {
            console.error('SSE Error (Connection Lost?):', err);
            closeSSE();

            // Auto-reconnect only if a script is still running
            if (sessionStorage.getItem('is_script_running') === 'true') {
                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = 'orange';
                line.textContent = '> Connection lost. Attempting to reconnect in 5s...';
                if (consoleContent) consoleContent.appendChild(line);

                setTimeout(() => {
                    console.log('Attempting auto-reconnect...');
                    connectSSE();
                }, 5000);
            }
        };
    }

    function closeSSE() {
        if (evtSource) {
            evtSource.close();
            evtSource = null;
        }
    }

    function pushToLogBuffer(msg) {
        logBuffer.push(msg);
        if (!isRenderPending) {
            isRenderPending = true;
            requestAnimationFrame(flushLogs);
        }
    }

    // ----------------------------------------------------------------
    // Expose to other modules
    // ----------------------------------------------------------------
    window.connectSSE = connectSSE;
    window.closeSSE = closeSSE;
    window.pushToLogBuffer = pushToLogBuffer;

});
