/**
 * execution.js — Script Execution, File Upload, Stop & Confirmation Modal
 *
 * Handles the full run lifecycle:
 *   1. File drag-and-drop / browse upload  → /api/upload
 *   2. Confirmation modal (pre-flight check via /api/recover_session)
 *   3. Execute  → clears session → connects SSE → posts to /api/execute
 *   4. Stop     → /api/stop, closes SSE, triggers STOP_UI_NOW
 *   5. Force Reset button
 *
 * Depends on (window globals):
 *   window.getClientId(), window.setClientId()   — session.js
 *   window.requestWakeLock(), window.releaseWakeLock() — wake_lock.js
 *   window.connectSSE(), window.closeSSE(), window.pushToLogBuffer() — sse.js
 *
 * Exposes:
 *   window.handleFile(file)         — upload a File object
 *   window.executeScriptLogic()     — run the selected script
 *   window.addResetButton()         — add Force Reset button to UI
 *   window.currentUploadedFilename  — currently staged filename (string | null)
 */

document.addEventListener('DOMContentLoaded', () => {

    // DOM refs
    const scriptSelect = document.getElementById('script-select');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const statusArea = document.getElementById('status-area');
    const runContainer = document.getElementById('run-container');
    const runBtn = document.getElementById('run-script-btn');
    const consoleBox = document.getElementById('console-box');
    const consoleContent = document.getElementById('console-content');

    let currentUploadedFilename = null;

    // ----------------------------------------------------------------
    // Dynamic Stop button
    // ----------------------------------------------------------------
    const stopBtn = document.createElement('button');
    stopBtn.id = 'stop-script-btn';
    stopBtn.textContent = 'Stop Process';
    stopBtn.style.cssText = 'display: none; background-color: #ff4444; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-weight: bold;';
    if (runContainer) runContainer.appendChild(stopBtn);

    stopBtn.addEventListener('click', async () => {
        if (!(await window.showConfirm('Stop Process', 'Are you sure you want to stop the running process?'))) return;

        stopBtn.disabled = true;
        stopBtn.textContent = 'Stopping...';

        if (window.releaseWakeLock) window.releaseWakeLock();

        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');
        fetch('/api/stop/' + clientId, { method: 'POST' })
            .catch(err => {
                console.error('Stop request failed:', err);
                window.showToast('Failed to reach server to stop the process.', 'error');
            });

        // Close SSE immediately
        if (window.closeSSE) window.closeSSE();

        // Push STOP_UI_NOW into the log buffer so flushLogs resets the UI
        if (window.pushToLogBuffer) {
            window.pushToLogBuffer('STOP_UI_NOW');
        } else {
            // Fallback if SSE was never connected
            statusArea.innerHTML = '<div style="color: Orange;">Job Stopped Successfully</div>';
            runBtn.disabled = false;
            runBtn.innerHTML = '▶ Run Script';
            stopBtn.style.display = 'none';
            sessionStorage.setItem('is_script_running', 'false');
            const newId = 'client_' + Math.random().toString(36).slice(2, 11);
            if (window.setClientId) window.setClientId(newId);
        }
    });

    // ----------------------------------------------------------------
    // Refresh / keyboard guards — block accidental page refresh mid-run
    // ----------------------------------------------------------------
    window.addEventListener('beforeunload', (e) => {
        if (sessionStorage.getItem('is_script_running') === 'true') {
            window.showToast('WARNING: A script is currently running! If you leave or refresh this page now, the process may be interrupted and your session will be lost. Please wait for the script to finish.', 'warning', 'Do Not Close Page');
            e.preventDefault();
        }
    });

    window.addEventListener('keydown', (e) => {
        if (sessionStorage.getItem('is_script_running') === 'true') {
            if (e.key === 'F5' || (e.ctrlKey && e.key === 'r') || (e.metaKey && e.key === 'r')) {
                e.preventDefault();
                window.showToast('Refresh is disabled while the script is running!', 'warning');
            }
        }
    });

    // ----------------------------------------------------------------
    // File drag-and-drop and browse
    // ----------------------------------------------------------------
    function checkAuthAndAlert() {
        if (window.checkAuthAndAlert) return window.checkAuthAndAlert();
        return true; // Fallback — app.js exposes the real one
    }

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (!checkAuthAndAlert()) return;
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener('click', (e) => {
        if (!checkAuthAndAlert()) e.preventDefault();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });

    // ----------------------------------------------------------------
    // handleFile — upload a selected file to /api/upload
    // ----------------------------------------------------------------
    function handleFile(file) {
        if (!scriptSelect.value) {
            window.showToast('Please select a script first.', 'error');
            return;
        }

        const dropText = dropZone.querySelector('.drop-text');
        if (dropText) dropText.innerHTML = `<strong>${file.name}</strong><p>Ready to upload</p>`;

        statusArea.innerHTML = '<div style="color: blue;">Uploading ' + file.name + '...</div>';

        const formData = new FormData();
        formData.append('file', file);

        fetch('/api/upload', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                currentUploadedFilename = data.filename;
                statusArea.innerHTML = '<div style="color: green;">Uploaded: ' + file.name + '</div>';
                if (runContainer) runContainer.style.display = 'flex';
                if (dropText) dropText.innerHTML = `<strong>${file.name}</strong><p style="color: green;">✅ Uploaded Successfully</p>`;
            })
            .catch(err => {
                statusArea.innerHTML = '<div style="color: red;">Upload Failed: ' + err.message + '</div>';
                if (dropText) dropText.innerHTML = `<strong>${file.name}</strong><p style="color: red;">❌ Upload Failed</p>`;
            });
    }

    // ----------------------------------------------------------------
    // Confirmation modal
    // ----------------------------------------------------------------
    const confirmModal = document.getElementById('confirmation-modal');
    const closeConfirmModal = document.getElementById('close-confirm-modal');
    const cancelRunBtn = document.getElementById('cancel-run-btn');
    const confirmRunBtn = document.getElementById('confirm-run-btn');

    const closeConfirmation = () => {
        if (confirmModal) confirmModal.style.display = 'none';
        if (confirmRunBtn) {
            confirmRunBtn.disabled = false;
            confirmRunBtn.innerHTML = 'Yes, Run Script';
        }
    };

    if (closeConfirmModal) closeConfirmModal.addEventListener('click', closeConfirmation);
    if (cancelRunBtn) cancelRunBtn.addEventListener('click', closeConfirmation);

    window.addEventListener('click', (event) => {
        if (event.target === confirmModal) return; // Don't close confirmation on outside click
        const backupModal = document.getElementById('backup-modal');
        if (event.target === backupModal) backupModal.style.display = 'none';
    });

    if (confirmRunBtn) {
        confirmRunBtn.addEventListener('click', () => {
            const machineId = localStorage.getItem('unique_machine_id');
            const tenant = document.getElementById('tenant-code').value;
            const user = document.getElementById('username').value;

            confirmRunBtn.disabled = true;
            confirmRunBtn.innerHTML = '<span class="spinner"></span> Checking...';

            fetch(`/api/recover_session?machine_id=${machineId}&username=${user}&tenant_code=${tenant}`)
                .then(r => r.json())
                .then(data => {
                    if (data.found) {
                        window.showToast('SESSION ACTIVE: A script is already running on this machine.\n\nYou cannot start a new session until the current one finishes or is Force Reset.', 'error', 'Action Blocked');
                        window.showConfirm('Session Active', 'Do you want to join the running session?').then(agreed => {
                            if (agreed) {
                                if (window.setClientId) window.setClientId(data.client_id);
                                sessionStorage.setItem('is_script_running', 'true');
                                sessionStorage.setItem('running_script_name', data.script_name || '');
                                location.reload();
                            } else {
                                closeConfirmation();
                            }
                        });
                    } else {
                        closeConfirmation();
                        executeScriptLogic();
                    }
                })
                .catch(() => {
                    closeConfirmation();
                    executeScriptLogic();
                });
        });
    }

    // ----------------------------------------------------------------
    // executeScriptLogic — wires SSE then fires /api/execute
    // ----------------------------------------------------------------
    function executeScriptLogic() {
        if (consoleBox) consoleBox.style.display = 'block';
        setTimeout(() => {
            const mainContent = document.querySelector('.main-content');
            if (mainContent) mainContent.scrollTo({ top: mainContent.scrollHeight, behavior: 'smooth' });
        }, 0);

        if (consoleContent) consoleContent.innerHTML = '';

        const connLine = document.createElement('div');
        connLine.className = 'console-line';
        connLine.textContent = '> Connecting to console...';
        if (consoleContent) {
            consoleContent.appendChild(connLine);
        }

        if (runBtn) { runBtn.disabled = true; runBtn.innerHTML = '<span class="spinner"></span> Processing...'; }
        if (stopBtn) { stopBtn.style.display = 'inline-block'; stopBtn.disabled = false; stopBtn.textContent = 'Stop Process'; }

        sessionStorage.setItem('is_script_running', 'true');
        sessionStorage.setItem('running_script_name', scriptSelect.value);

        // Persist credentials for auto-recovery
        localStorage.setItem('tenant_code', document.getElementById('tenant-code').value);
        localStorage.setItem('username', document.getElementById('username').value);

        if (window.requestWakeLock) window.requestWakeLock();

        // Close any existing SSE connection before starting fresh
        if (window.closeSSE) window.closeSSE();

        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');

        fetch('/api/clear_session/' + clientId, { method: 'POST' })
            .finally(() => {
                if (window.connectSSE) {
                    window.connectSSE(() => { startExecution(); });
                } else {
                    startExecution();
                }
            });
    }

    // ----------------------------------------------------------------
    // startExecution — builds config and POSTs to /api/execute
    // ----------------------------------------------------------------
    function startExecution() {
        const startLine = document.createElement('div');
        startLine.className = 'console-line';
        startLine.textContent = '> Starting execution...';
        if (consoleContent) consoleContent.appendChild(startLine);

        const postApiUrl = document.getElementById('put-api-url').value;
        const useFarmerId = document.getElementById('use-farmer-id').value;
        const scriptNameForCfg = scriptSelect.value;
        const attrCount = parseInt(document.getElementById('attr-count-select').value) || 1;

        let attrKeys = [];
        if (scriptNameForCfg === 'Update_Farmer_Address.py' || scriptNameForCfg === 'Update_Asset_Address.py') {
            const addrCount = parseInt(document.getElementById('addr-count-select').value) || 1;
            ['address-key-1', 'address-key-2', 'address-key-3', 'address-key-4'].forEach((id, i) => {
                if (i < addrCount) {
                    const v = document.getElementById(id)?.value;
                    if (v) attrKeys.push(v);
                }
            });
        } else {
            ['attr-key-1', 'attr-key-2', 'attr-key-3', 'attr-key-4'].forEach((id, i) => {
                if (i < attrCount) attrKeys.push(document.getElementById(id)?.value || '');
            });
        }

        const areaUnit = document.getElementById('area-unit-select')?.value || 'Hectare';
        const forceCropAudited = document.getElementById('force-crop-audited')?.value || 'none';
        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');

        const config = {
            username: document.getElementById('username').value,
            password: document.getElementById('password').value,
            environment: document.getElementById('environment').value,
            tenant_code: document.getElementById('tenant-code').value,
            post_api_url: postApiUrl,
            secondary_api_url: document.getElementById('secondary-api-url')?.value || '',
            x_api_key: document.getElementById('x-api-key')?.value || '',
            ca_action: document.getElementById('ca-action-select')?.value || 'none',
            use_farmer_id: useFarmerId,
            attr_keys: attrKeys,
            fields_to_remove: attrKeys,
            unit: areaUnit,
            force_crop_audited: forceCropAudited,
            delay_time: document.getElementById('delay-time-input')?.value || 1,
            worker_count: parseInt(document.getElementById('worker-count')?.value) || 1,
        };

        const formData = new FormData();
        formData.append('script_name', scriptSelect.value);
        if (currentUploadedFilename) formData.append('input_filename', currentUploadedFilename);
        formData.append('config', JSON.stringify(config));
        formData.append('client_id', clientId);

        // Machine ID — ensures one script per machine per user
        let machineId = localStorage.getItem('unique_machine_id');
        if (!machineId) {
            machineId = 'machine_' + Math.random().toString(36).slice(2, 11) + '_' + Date.now();
            localStorage.setItem('unique_machine_id', machineId);
        }
        formData.append('machine_id', machineId);

        fetch('/api/execute', { method: 'POST', body: formData })
            .then(r => {
                if (r.ok) return r.json();
                return r.json().then(err => { throw new Error(err.detail || 'Execution Failed'); });
            })
            .then(data => {
                const line = document.createElement('div');
                line.className = 'console-line';
                line.textContent = '> ' + data.message;
                if (consoleContent) consoleContent.appendChild(line);
            })
            .catch(err => {
                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = '#ff4444';
                line.textContent = '> Request Failed: ' + err.message;
                if (consoleContent) consoleContent.appendChild(line);

                if (statusArea) statusArea.innerHTML = '<div style="color: red;">Request Failed</div>';
                if (runBtn) { runBtn.disabled = false; }
                sessionStorage.setItem('is_script_running', 'false');
            });
    }

    // ----------------------------------------------------------------
    // Force Reset button
    // ----------------------------------------------------------------
    function addResetButton() {
        if (document.getElementById('reset-session-btn')) return;

        const resetBtn = document.createElement('button');
        resetBtn.id = 'reset-session-btn';
        resetBtn.textContent = 'Force Reset';
        resetBtn.style.cssText = 'margin-left: 10px; background-color: #ff4444; color: white; border: none; padding: 5px 10px; cursor: pointer; border-radius: 4px;';

        const rc = document.getElementById('run-container');
        if (rc) rc.appendChild(resetBtn);

        resetBtn.addEventListener('click', async () => {
            const confirmed = await window.showConfirm('Force Reset', 'Are you sure you want to force reset the session? Any running task logs will be disconnected.');
            if (confirmed) {
                sessionStorage.setItem('is_script_running', 'false');
                sessionStorage.removeItem('running_script_name');
                if (window.releaseWakeLock) window.releaseWakeLock();
                location.reload();
            }
        });
    }

    // ----------------------------------------------------------------
    // Expose to other modules
    // ----------------------------------------------------------------
    window.handleFile = handleFile;
    window.executeScriptLogic = executeScriptLogic;
    window.addResetButton = addResetButton;

    // Expose currentUploadedFilename as an accessor so any module can
    // read/write it and the closure variable stays in sync.
    Object.defineProperty(window, 'currentUploadedFilename', {
        get: () => currentUploadedFilename,
        set: (v) => { currentUploadedFilename = v; },
        configurable: true
    });

});
