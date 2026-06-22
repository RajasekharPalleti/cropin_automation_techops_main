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
    // Helper: extract plain text from console-content lines
    // ----------------------------------------------------------------
    function getConsoleText() {
        if (!consoleContent) return '';
        return Array.from(consoleContent.querySelectorAll('.console-line, div'))
            .map(el => el.textContent)
            .join('\n')
            .trim();
    }

    // ----------------------------------------------------------------
    // Copy Logs button
    // ----------------------------------------------------------------
    const copyLogsBtn = document.getElementById('copy-logs-btn');
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener('click', () => {
            const text = getConsoleText();
            if (!text) { window.showToast('No console output to copy.', 'error'); return; }

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    copyLogsBtn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">check</span> Copied!';
                    setTimeout(() => {
                        copyLogsBtn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">content_copy</span> Copy';
                    }, 2000);
                }).catch(() => window.showToast('Failed to copy. Try downloading instead.', 'error'));
            } else {
                // Fallback for older browsers
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.cssText = 'position:fixed;opacity:0;';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                ta.remove();
                copyLogsBtn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">check</span> Copied!';
                setTimeout(() => {
                    copyLogsBtn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">content_copy</span> Copy';
                }, 2000);
            }
        });
    }

    // ----------------------------------------------------------------
    // Download Logs button
    // ----------------------------------------------------------------
    const downloadLogsBtn = document.getElementById('download-logs-btn');
    if (downloadLogsBtn) {
        downloadLogsBtn.addEventListener('click', () => {
            const text = getConsoleText();
            if (!text) { window.showToast('No console output to download.', 'error'); return; }

            const scriptName = (document.getElementById('script-select')?.value || 'script').replace('.py', '');
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            const filename = `${scriptName}_logs_${timestamp}.txt`;

            const blob = new Blob([text], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        });
    }

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
                checkScheduleEligibility();
            })
            .catch(err => {
                statusArea.innerHTML = '<div style="color: red;">Upload Failed: ' + err.message + '</div>';
                if (dropText) dropText.innerHTML = `<strong>${file.name}</strong><p style="color: red;">❌ Upload Failed</p>`;
                checkScheduleEligibility();
            });
    }

    // ----------------------------------------------------------------
    // Schedule Run Eligibility Check
    // ----------------------------------------------------------------
    const openScheduleModalBtn = document.getElementById('open-schedule-modal-btn');

    function checkScheduleEligibility() {
        const tenant = document.getElementById('tenant-code')?.value;
        const username = document.getElementById('username')?.value;
        const password = document.getElementById('password')?.value;
        const scriptSelected = document.getElementById('script-select')?.value;

        if (tenant && username && password && scriptSelected && currentUploadedFilename && openScheduleModalBtn) {
            openScheduleModalBtn.disabled = false;
        } else if (openScheduleModalBtn) {
            openScheduleModalBtn.disabled = true;
        }
    }

    // Attach to inputs so they watch actively for typing
    ['tenant-code', 'username', 'password', 'script-select'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', checkScheduleEligibility);
            el.addEventListener('input', checkScheduleEligibility);
        }
    });

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

    // Modals now only close via their specific close buttons or actions.

    if (confirmRunBtn) {
        confirmRunBtn.addEventListener('click', () => {
            const machineId = localStorage.getItem('unique_machine_id');
            const tenant = document.getElementById('tenant-code').value;
            const user = document.getElementById('username').value;

            confirmRunBtn.disabled = true;
            confirmRunBtn.innerHTML = '<span class="spinner"></span> Checking...';

            fetch('/api/recover_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    machine_id: machineId,
                    username: user,
                    tenant_code: tenant
                })
            })
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

        // Proactively request notification permission
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }

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
    // buildScriptConfig — Extracts inputs into the config dictionary
    // ----------------------------------------------------------------
    function buildScriptConfig() {
        // Core fields that are ALWAYS required:
        const config = {
            username: document.getElementById('username').value,
            password: document.getElementById('password').value,
            environment: document.getElementById('environment').value,
            tenant_code: document.getElementById('tenant-code').value,
            base_api_url: document.getElementById('base-api-url').value,
        };

        // scriptSelect.value is available via the outer-scope `scriptSelect` ref if needed

        // 1. PR / Weather Config — only send use_farmer_id when section is visible
        const prWeatherConfig = document.getElementById('pr-weather-config');
        if (prWeatherConfig && prWeatherConfig.style.display !== 'none') {
            const useFarmerId = document.getElementById('use-farmer-id')?.value;
            if (useFarmerId) config.use_farmer_id = useFarmerId;
        }

        // 2. Threading Config
        const threadingContainer = document.getElementById('threading-config');
        if (threadingContainer && threadingContainer.style.display !== 'none') {
            config.worker_count = parseInt(document.getElementById('worker-count')?.value) || 1;
        }

        // 3. Extra Appended Config (Secondary URL & Google API)
        const secondaryGroup = document.getElementById('group-secondary-url');
        if (secondaryGroup && secondaryGroup.style.display !== 'none') {
            const secondBaseApiUrl = document.getElementById('second-base-api-url')?.value;
            if (secondBaseApiUrl) config.second_base_api_url = secondBaseApiUrl;
        }

        // 4. Google API Config
        const googleApiConfig = document.getElementById('google-api-config');
        if (googleApiConfig && googleApiConfig.style.display !== 'none') {
            const xApiKey = document.getElementById('x-api-key')?.value;
            if (xApiKey) config.x_api_key = xApiKey;
        }

        // 5. CA Control Config
        const caControl = document.getElementById('ca-close-delete-config');
        if (caControl && caControl.style.display !== 'none') {
            config.ca_action = document.getElementById('ca-action-select')?.value || 'none';
            config.ca_x_api_key = document.getElementById('ca-x-api-key')?.value || 'SEF5qQ6RTDGFWUc36SNuCKGYW1tVuGgGrX1iApUs5DGOc7MS';
        }

        // 6. Common Batch Size Config
        const commonBatchConfig = document.getElementById('common-batch-config');
        if (commonBatchConfig && commonBatchConfig.style.display !== 'none') {
            const batchInput = document.getElementById('common-batch-size');
            const selectedScriptName = document.getElementById('script-select')?.value;
            const selectedScriptData = (window.scriptsData || []).find(s => s.name === selectedScriptName);
            const isUnlimited = selectedScriptData?.unlimited_batch_size === true;

            let batchSizeRaw = parseInt(batchInput?.value);
            if (isNaN(batchSizeRaw) || batchSizeRaw < 1) batchSizeRaw = isUnlimited ? 200 : 100;
            if (!isUnlimited && batchSizeRaw > 100) {
                window.showToast("Batch size cannot exceed 100. Lowering to 100.", "error", "Invalid Input");
                batchInput.value = 100;
                batchSizeRaw = 100;
            }
            config.batch_size = batchSizeRaw;
        }

        // 7. Attribute Config (Generic Attributes)
        const attributeConfig = document.getElementById('attribute-config');
        if (attributeConfig && attributeConfig.style.display !== 'none') {
            const attrCount = parseInt(document.getElementById('attr-count-select').value) || 1;
            let attrKeys = [];
            ['attr-key-1', 'attr-key-2', 'attr-key-3', 'attr-key-4', 'attr-key-5', 'attr-key-6', 'attr-key-7', 'attr-key-8', 'attr-key-9', 'attr-key-10'].forEach((id, i) => {
                if (i < attrCount) attrKeys.push(document.getElementById(id)?.value || '');
            });
            config.attr_keys = attrKeys;
            // Many legacy scripts expect 'fields_to_remove' via the exact same array layout
            config.fields_to_remove = attrKeys;
        }

        // 8. Address Config
        const addressConfig = document.getElementById('address-config');
        if (addressConfig && addressConfig.style.display !== 'none') {
            const addrCount = parseInt(document.getElementById('addr-count-select').value) || 1;
            let addrKeys = [];
            ['address-key-1', 'address-key-2', 'address-key-3', 'address-key-4', 'address-key-5', 'address-key-6', 'address-key-7', 'address-key-8', 'address-key-9', 'address-key-10'].forEach((id, i) => {
                if (i < addrCount) {
                    const v = document.getElementById(id)?.value;
                    if (v) addrKeys.push(v);
                }
            });
            config.attr_keys = addrKeys;
            config.fields_to_remove = addrKeys;
        }

        // 9. Area Audit Config
        const areaAuditConfig = document.getElementById('area-audit-config');
        if (areaAuditConfig && areaAuditConfig.style.display !== 'none') {
            config.unit = document.getElementById('area-unit-select')?.value || 'Hectare';
            config.force_crop_audited = document.getElementById('force-crop-audited')?.value || 'true';
        }

        // 10. Variety Removal Config
        const varietyRemovalConfig = document.getElementById('variety-removal-config');
        if (varietyRemovalConfig && varietyRemovalConfig.style.display !== 'none') {
            const remCount = parseInt(document.getElementById('removal-count-select')?.value) || 1;
            let remKeys = [];
            ['remove-key-1', 'remove-key-2', 'remove-key-3', 'remove-key-4'].forEach((id, i) => {
                if (i < remCount) {
                    const v = document.getElementById(id)?.value;
                    if (v) remKeys.push(v);
                }
            });
            config.attr_keys = remKeys;
            config.fields_to_remove = remKeys;
        }

        // 11. Coordinate Order Config
        const coordOrderConfig = document.getElementById('coordinate-order-config');
        if (coordOrderConfig && coordOrderConfig.style.display !== 'none') {
            config.coordinate_order = document.getElementById('coordinate-order')?.value || 'Long, Lat';
        }

        // 12. Time Delay Config — always read when the section is visible
        const timeDelayConfig = document.getElementById('time-delay-config');
        if (timeDelayConfig && timeDelayConfig.style.display !== 'none') {
            const delayVal = parseFloat(document.getElementById('delay-time-input')?.value);
            config.delay_time = isNaN(delayVal) || delayVal < 0 ? 1 : delayVal;
        }

        return config;
    }

    // ----------------------------------------------------------------
    // startExecution — builds config and POSTs to /api/execute
    // ----------------------------------------------------------------
    function startExecution() {
        const startLine = document.createElement('div');
        startLine.className = 'console-line';
        startLine.textContent = '> Starting execution...';
        if (consoleContent) consoleContent.appendChild(startLine);

        const config = buildScriptConfig();
        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');

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
    // Scheduled Scripts UI & Logic
    // ----------------------------------------------------------------
    const scheduleModal = document.getElementById('schedule-run-modal');
    const closeScheduleModal = document.getElementById('close-schedule-run');
    const cancelScheduleBtn = document.getElementById('cancel-schedule-run-btn');
    const saveScheduleBtn = document.getElementById('save-schedule-run-btn');
    const scheduleDatetime = document.getElementById('schedule-datetime');

    if (openScheduleModalBtn) openScheduleModalBtn.addEventListener('click', () => {
        if (scheduleModal) {
            // Set min to current time (YYYY-MM-DDTHH:MM)
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const minDateTime = `${year}-${month}-${day}T${hours}:${minutes}`;

            if (scheduleDatetime) {
                scheduleDatetime.min = minDateTime;
                // Default to 5 minutes from now if empty or in past
                if (!scheduleDatetime.value || scheduleDatetime.value < minDateTime) {
                    const future = new Date(now.getTime() + 5 * 60000);
                    const fYear = future.getFullYear();
                    const fMonth = String(future.getMonth() + 1).padStart(2, '0');
                    const fDay = String(future.getDate()).padStart(2, '0');
                    const fHours = String(future.getHours()).padStart(2, '0');
                    const fMinutes = String(future.getMinutes()).padStart(2, '0');
                    scheduleDatetime.value = `${fYear}-${fMonth}-${fDay}T${fHours}:${fMinutes}`;
                }
            }
            scheduleModal.style.display = 'block';
        }
    });

    const hideScheduleModal = () => { if (scheduleModal) scheduleModal.style.display = 'none'; };
    if (closeScheduleModal) closeScheduleModal.addEventListener('click', hideScheduleModal);
    if (cancelScheduleBtn) cancelScheduleBtn.addEventListener('click', hideScheduleModal);

    // Show hover message (tooltip) matching project UI
    if (openScheduleModalBtn) {
        const parent = openScheduleModalBtn.parentElement;
        let tooltip = document.getElementById('schedule-tooltip');

        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'schedule-tooltip';
            tooltip.className = 'custom-tooltip';
            document.body.appendChild(tooltip);
        }

        const updateTooltip = () => {
            if (openScheduleModalBtn.disabled) {
                tooltip.textContent = 'Schedule Run is currently inactive. Please select a script, enter credentials, and upload a template to enable it.';
            } else {
                tooltip.textContent = 'Schedule this script for a future time. It will run automatically even if you close the browser.';
            }

            // Show it hidden first to get dimensions
            tooltip.style.visibility = 'hidden';
            tooltip.classList.add('show');

            // Wait a tiny bit (next tick) to ensure width/height are populated
            requestAnimationFrame(() => {
                const rect = openScheduleModalBtn.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();

                // Center horizontally relative to button
                let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
                // Position above button with space for the arrow
                let top = rect.top - tooltipRect.height - 12;

                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
                tooltip.style.visibility = 'visible';
            });
        };

        const hideTooltip = () => {
            tooltip.classList.remove('show');
            tooltip.style.visibility = 'hidden';
        };

        openScheduleModalBtn.addEventListener('mouseenter', updateTooltip);
        openScheduleModalBtn.addEventListener('mouseleave', hideTooltip);
    }

    if (scheduleDatetime) {
        scheduleDatetime.addEventListener('change', () => {
            if (scheduleDatetime.min && scheduleDatetime.value < scheduleDatetime.min) {
                window.showToast('Please select a future date and time.', 'warning');
                scheduleDatetime.value = scheduleDatetime.min;
            }
        });
    }

    if (saveScheduleBtn) saveScheduleBtn.addEventListener('click', () => {
        if (!scheduleDatetime.value) {
            window.showToast('Please select a date and time.', 'error');
            return;
        }

        saveScheduleBtn.disabled = true;
        saveScheduleBtn.innerHTML = '<span class="spinner"></span> Saving...';

        const config = buildScriptConfig();

        const formData = new FormData();
        formData.append('script_name', scriptSelect.value);
        if (currentUploadedFilename) formData.append('input_filename', currentUploadedFilename);
        formData.append('config', JSON.stringify(config));
        formData.append('run_time', scheduleDatetime.value);
        formData.append('recurrence', document.getElementById('schedule-recurrence')?.value || 'none');
        formData.append('max_retries', document.getElementById('schedule-max-retries')?.value || '1');


        fetch('/api/schedule', { method: 'POST', body: formData })
            .then(r => {
                if (r.ok) return r.json();
                return r.json().then(err => { throw new Error(err.detail || 'Failed'); });
            })
            .then(data => {
                window.showToast('Script successfully scheduled!', 'success');
                hideScheduleModal();
                setTimeout(() => {
                    location.reload();
                }, 1500);
            })
            .catch(err => {
                window.showToast('Failed to schedule: ' + err.message, 'error');
                saveScheduleBtn.disabled = false;
                saveScheduleBtn.innerHTML = 'Save & Schedule';
            });
    });

    // --- Schedule List Management ---
    const scheduledListModal = document.getElementById('scheduled-list-modal');
    const openScheduledListBtn = document.getElementById('scheduled-list-btn');
    const closeScheduledListBtn = document.getElementById('close-scheduled-list');

    if (openScheduledListBtn) openScheduledListBtn.addEventListener('click', () => {
        if (scheduledListModal) {
            scheduledListModal.style.display = 'block';
            // Explicitly click the first tab to ensure UI resets and fetches data
            if (tabScheduled) tabScheduled.click();
            else fetchScheduledJobs();
        }
    });

    if (closeScheduledListBtn) closeScheduledListBtn.addEventListener('click', () => {
        if (scheduledListModal) scheduledListModal.style.display = 'none';
    });

    const tabScheduled = document.getElementById('tab-scheduled');
    const tabRunning = document.getElementById('tab-running');
    const tabHistory = document.getElementById('tab-history');
    const contentScheduled = document.getElementById('content-scheduled');
    const contentRunning = document.getElementById('content-running');
    const contentHistory = document.getElementById('content-history');

    if (tabScheduled && tabRunning && tabHistory) {
        const switchTab = (activeTab, activeContent) => {
            [tabScheduled, tabRunning, tabHistory].forEach(t => {
                t.classList.remove('active');
                t.style.borderBottomColor = 'transparent';
                t.style.color = '#666';
                t.style.fontWeight = '500';
            });
            [contentScheduled, contentRunning, contentHistory].forEach(c => {
                if (c) c.style.display = 'none';
            });

            activeTab.classList.add('active');
            activeTab.style.borderBottomColor = '#009ade';
            activeTab.style.color = '#009ade';
            activeTab.style.fontWeight = '600';
            if (activeContent) activeContent.style.display = 'block';
            fetchScheduledJobs();
        };

        tabScheduled.addEventListener('click', () => switchTab(tabScheduled, contentScheduled));
        tabRunning.addEventListener('click', () => switchTab(tabRunning, contentRunning));
        tabHistory.addEventListener('click', () => switchTab(tabHistory, contentHistory));
    }

    // Modal Polling Logic
    function fetchScheduledJobs() {
        const schedContainer = document.getElementById('scheduled-jobs-container');
        const runContainer = document.getElementById('running-jobs-container');
        const histContainer = document.getElementById('history-jobs-container');

        const loadingHTML = '<div style="display:flex; align-items:center; gap:10px; color:#666; font-style:italic;"><span class="spinner" style="border-top-color:#009ade; width:16px; height:16px;"></span> Loading scripts...</div>';

        if (schedContainer) schedContainer.innerHTML = loadingHTML;
        if (runContainer) runContainer.innerHTML = loadingHTML;
        if (histContainer) histContainer.innerHTML = loadingHTML;

        fetch('/api/scheduled_jobs')
            .then(r => {
                if (!r.ok) throw new Error("Server error: " + r.status);
                return r.json();
            })
            .then(data => {
                renderJobs(data.jobs || []);
            })
            .catch(err => {
                console.error("Failed to fetch jobs", err);
                const errorHTML = `<p style="color:#dc3545; font-weight:500;">❌ Failed to load: ${err.message}</p>`;
                if (schedContainer) schedContainer.innerHTML = errorHTML;
                if (runContainer) runContainer.innerHTML = errorHTML;
                if (histContainer) histContainer.innerHTML = errorHTML;
            });
    }

    function renderJobs(jobs) {
        const schedContainer = document.getElementById('scheduled-jobs-container');
        const runContainer = document.getElementById('running-jobs-container');
        const histContainer = document.getElementById('history-jobs-container');

        const pendingJobs = jobs.filter(j => j.status === 'pending');
        const runningJobs = jobs.filter(j => j.status === 'running');
        const historyJobs = jobs.filter(j => ['completed', 'failed', 'cancelled', 'missed'].includes(j.status));

        // Render Pending
        if (pendingJobs.length === 0) {
            if (schedContainer) schedContainer.innerHTML = '<p style="color:#666; font-style:italic;">No upcoming scheduled scripts.</p>';
        } else {
            if (schedContainer) schedContainer.innerHTML = pendingJobs.map(j => {
                const recurrenceBadge = (j.recurrence && j.recurrence !== 'none')
                    ? `<span style="background:#6a1b9a; color:white; padding:2px 7px; border-radius:10px; font-size:0.7rem; margin-left:8px; vertical-align:middle;">🔁 ${j.recurrence === 'daily' ? 'Daily' : 'Weekly'}</span>`
                    : '';
                const retryBadge = (j.retry_count && j.retry_count > 0)
                    ? `<span style="color:#e65100; font-size:0.8rem; margin-top:3px; display:block;">⚠ Retry attempt ${j.retry_count}/${j.max_retries}</span>`
                    : '';
                return `
                <div id="job-card-${j.job_id}" style="border:1px solid #ddd; padding:15px; border-radius:6px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                    <div id="job-info-${j.job_id}">
                        <span style="color:#333; font-size:1.1rem; font-weight:600;">${j.script_name}</span>${recurrenceBadge}
                        <div style="color:#666; font-size:0.9rem; margin-top:5px;" id="job-time-${j.job_id}">📅 ${new Date(j.run_time).toLocaleString()}</div>
                        ${retryBadge}
                    </div>
                    <div style="display:flex; gap:10px;" id="job-actions-${j.job_id}">
                        <button onclick="window.runJobNow('${j.job_id}')" class="btn-primary" style="padding:6px 12px; font-size:0.9rem;">▶ Run Now</button>
                        <button onclick="window.editJob('${j.job_id}', '${j.run_time}')" class="btn-secondary" style="padding:6px 12px; font-size:0.9rem;">Edit</button>
                        <button onclick="window.deleteJob('${j.job_id}')" class="btn-secondary" style="color:#dc3545; border-color:#dc3545; padding:6px 12px; font-size:0.9rem;">Delete</button>
                    </div>
                </div>
            `;
            }).join('');
        }


        // Render Running
        if (runningJobs.length === 0) {
            if (runContainer) runContainer.innerHTML = '<p style="color:#666; font-style:italic;">No scripts are currently running.</p>';
        } else {
            if (runContainer) runContainer.innerHTML = runningJobs.map(j => `
                <div style="border:1px solid #17a2b8; background:#e0f7fa; padding:15px; border-radius:6px; margin-bottom:10px;">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span class="spinner" style="border-top-color:#17a2b8;"></span>
                            <strong style="color:#00838f; font-size:1.1rem;">${j.script_name}</strong>
                            ${j.started_at ? `<span style="margin-left:10px; font-size:0.85rem; color:#006064; background-color:#b2ebf2; padding:2px 8px; border-radius:12px;">Started At: ${new Date(j.started_at).toLocaleString()}</span>` : ''}
                        </div>
                        <button onclick="window.stopScheduledJob('${j.job_id}', this)" class="btn-primary" 
                                style="background-color:#dc3545; border-color:#dc3545; color:white; padding:6px 12px; font-size:0.9rem;">
                            Stop script execution
                        </button>
                    </div>
                    <p style="color:#006064; font-size:0.95rem; margin:0;">
                        Scheduled running is in progress. The server is processing this in the background.
                    </p>
                </div>
            `).join('');
        }

        // Render History
        if (histContainer) {
            if (historyJobs.length === 0) {
                histContainer.innerHTML = '<p style="color:#666; font-style:italic;">No history available.</p>';
            } else {
                histContainer.innerHTML = historyJobs.map(j => {
                    let statusColor = '#28a745';
                    let statusText = 'Success';

                    if (j.status === 'failed') {
                        statusColor = '#dc3545';
                        statusText = 'Failed';
                    } else if (j.status === 'cancelled') {
                        statusColor = '#ffc107'; // Yellow/Orange
                        statusText = 'Cancelled';
                    } else if (j.status === 'missed') {
                        statusColor = '#6c757d'; // Grey
                        statusText = 'Missed';
                    }

                    const timeStr = j.completed_at ? new Date(j.completed_at).toLocaleString() : 'Recently';

                    return `
                        <div style="border:1px solid #ddd; padding:12px; border-radius:6px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <strong style="color:#333;">${j.script_name}</strong>
                                ${j.recurrence && j.recurrence !== 'none' ? `<span style="background:#6a1b9a; color:white; padding:1px 6px; border-radius:9px; font-size:0.65rem; margin-left:6px;">🔁 ${j.recurrence}</span>` : ''}
                                <div style="color:#666; font-size:0.85rem; margin-top:4px;">
                                    Finished: ${timeStr}
                                </div>
                                ${j.retry_count ? `<div style="color:#e65100; font-size:0.78rem; margin-top:2px;">Retried ${j.retry_count}/${j.max_retries} time(s)</div>` : ''}
                            </div>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="background:${statusColor}; color:white; padding:3px 8px; border-radius:12px; font-size:0.75rem; font-weight:bold;">${statusText}</span>
                                <button onclick="window.deleteJob('${j.job_id}')" title="Remove from history" 
                                        style="background:none; border:none; color:#999; cursor:pointer; padding:5px;"><span class="material-icons" style="font-size:1.1rem;">delete</span></button>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }
    }

    window.runJobNow = (jobId) => {
        fetch('/api/scheduled_jobs/' + jobId + '/run_now', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                window.showToast("Job kicked off. Moving to running tab...", "success");
                tabRunning.click();
            });
    };

    window.deleteJob = (jobId) => {
        fetch('/api/scheduled_jobs/' + jobId, { method: 'DELETE' })
            .then(r => r.json())
            .then(d => {
                window.showToast("Schedule removed", "success");
                fetchScheduledJobs();
            });
    };

    window.editJob = (jobId, currentTime) => {
        const timeEl = document.getElementById('job-time-' + jobId);
        const actionsEl = document.getElementById('job-actions-' + jobId);
        if (!timeEl || !actionsEl) return;

        // Store original content for cancel
        const originalTimeHTML = timeEl.innerHTML;
        const originalActionsHTML = actionsEl.innerHTML;

        // Inject datetime-local input
        timeEl.innerHTML = `
            <input type="datetime-local" id="edit-time-${jobId}" value="${currentTime}" 
                   style="padding:5px; border:1px solid #009ade; border-radius:4px; font-size:0.9rem; width:100%; box-sizing:border-box; margin-top:5px;">
            <div style="font-size:0.75rem; color:#888; margin-top:2px;">(IST Timezone)</div>
        `;

        // Inject Save and Cancel buttons
        actionsEl.innerHTML = `
            <button onclick="window.saveJobEdit('${jobId}', '${currentTime}')" class="btn-primary" 
                    style="padding:6px 12px; font-size:0.9rem; background-color:#28a745; border-color:#28a745;">Save</button>
            <button onclick="window.cancelEdit('${jobId}', \`${originalTimeHTML.replace(/"/g, '&quot;')}\`, \`${originalActionsHTML.replace(/"/g, '&quot;')}\`)" class="btn-secondary" 
                    style="padding:6px 12px; font-size:0.9rem;">Cancel</button>
        `;
    };

    window.cancelEdit = (jobId, originalTimeHTML, originalActionsHTML) => {
        const timeEl = document.getElementById('job-time-' + jobId);
        const actionsEl = document.getElementById('job-actions-' + jobId);
        if (timeEl) timeEl.innerHTML = originalTimeHTML;
        if (actionsEl) actionsEl.innerHTML = originalActionsHTML;
    };

    window.saveJobEdit = (jobId, oldTime) => {
        const input = document.getElementById('edit-time-' + jobId);
        const newTime = input?.value;

        if (!newTime) {
            window.showToast('Please select a valid date and time.', 'error');
            return;
        }

        if (newTime === oldTime) {
            // No change, just refresh to reset UI
            fetchScheduledJobs();
            return;
        }

        fetch('/api/scheduled_jobs/' + jobId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_time: newTime })
        })
            .then(r => r.json())
            .then(d => {
                window.showToast(d.message || "Job rescheduled successfully", "success");
                fetchScheduledJobs();
            })
            .catch(err => {
                window.showToast("Failed to reschedule: " + err.message, "error");
            });
    };

    window.stopScheduledJob = (jobId, btn) => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="border-top-color:#fff; width:12px; height:12px; border-width:2px; vertical-align:middle;"></span> Stopping...';

        fetch('/api/stop/Scheduled_' + jobId, { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                window.showToast("Warning: Background script forced to abort execution.", "error");
                setTimeout(fetchScheduledJobs, 1000); // Reload the tab to see it disappear
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerText = "Stop script execution";
                window.showToast("Failed to stop job.", "error");
            });
    };

    // ----------------------------------------------------------------
    // Deforestation modal — three-screen flow
    // Screen 1: Auth (env + tenant + username + password → token fetched silently)
    // Screen 2: Base URL
    // Screen 3: API actions
    // ----------------------------------------------------------------
    let deforestToken        = null;
    let deforestBaseUrl      = null;
    let deforestTemplateId   = null;
    let deforestTemplateName = null;
    let deforestUploadId     = null;

    const deforestBtn      = document.getElementById('open-deforestation-modal-btn');
    const deforestModal    = document.getElementById('deforestation-modal');
    const deforestClose    = document.getElementById('deforestation-modal-close');
    const deforestScreen1  = document.getElementById('deforestation-screen-1');
    const deforestScreen2  = document.getElementById('deforestation-screen-2');
    const deforestScreen3  = document.getElementById('deforestation-screen-3');
    const deforestError1   = document.getElementById('deforestation-error-1');
    const deforestError2   = document.getElementById('deforestation-error-2');
    const deforestError3   = document.getElementById('deforestation-error-3');
    const deforestGenBtn   = document.getElementById('deforestation-generate-btn');
    const deforestGenStatus = document.getElementById('deforestation-generate-status');
    const deforestDlBtn    = document.getElementById('deforestation-dl-btn');
    const deforestDlStatus = document.getElementById('deforestation-dl-status');
    const deforestProcessBtn    = document.getElementById('deforestation-process-btn');
    const deforestProcessStatus = document.getElementById('deforestation-process-status');
    const deforestStatusBtn      = document.getElementById('deforestation-status-btn');
    const deforestStatusResponse = document.getElementById('deforestation-status-response');
    const deforestStatusJson     = document.getElementById('deforestation-status-json');
    const deforestStatusError    = document.getElementById('deforestation-status-error');
    const deforestUploadBtn    = document.getElementById('deforestation-upload-btn');
    const deforestUploadStatus = document.getElementById('deforestation-upload-status');

    function showDeforestScreen(n) {
        deforestScreen1.style.display = n === 1 ? '' : 'none';
        deforestScreen2.style.display = n === 2 ? '' : 'none';
        deforestScreen3.style.display = n === 3 ? 'flex' : 'none';
    }

    function resetDeforestModal() {
        showDeforestScreen(1);
        deforestToken        = null;
        deforestBaseUrl      = null;
        deforestTemplateId   = null;
        deforestTemplateName = null;
        deforestUploadId     = null;
        deforestError1.style.display = 'none';
        deforestError2.style.display = 'none';
        deforestError3.style.display = 'none';
        deforestGenStatus.textContent    = '';
        deforestDlStatus.textContent     = '';
        deforestUploadStatus.textContent = '';
        deforestProcessStatus.textContent = '';
        deforestDlBtn.disabled      = true;
        deforestProcessBtn.disabled = true;
        deforestStatusBtn.disabled  = true;
        deforestStatusResponse.style.display = 'none';
        document.getElementById('deforestation-tenant').value   = '';
        document.getElementById('deforestation-username').value = '';
        document.getElementById('deforestation-password').value = '';
        document.getElementById('deforestation-base-url').value = '';
    }

    deforestBtn.addEventListener('click', () => {
        resetDeforestModal();
        deforestModal.style.display = 'block';
    });

    deforestClose.addEventListener('click', () => {
        deforestModal.style.display = 'none';
    });

    // Screen 1 → Auth API → Screen 2
    const SSO_CONFIG = {
        QA:   { base: 'https://v2sso-gcp.cropin.co.in',     extraParams: {} },
        UAT:  { base: 'https://v2sso-uat-gcp.cropin.co.in', extraParams: {} },
        PROD: { base: 'https://sso.sg.cropin.in',            extraParams: {} }
    };

    document.getElementById('deforestation-proceed-btn').addEventListener('click', async () => {
        const env      = document.getElementById('deforestation-env').value;
        const tenant   = document.getElementById('deforestation-tenant').value.trim();
        const username = document.getElementById('deforestation-username').value.trim();
        const password = document.getElementById('deforestation-password').value.trim();

        deforestError1.style.display = 'none';
        if (!tenant || !username || !password) {
            deforestError1.textContent = 'Tenant Name, Username and Password are required.';
            deforestError1.style.display = 'block';
            return;
        }

        const proceedBtn = document.getElementById('deforestation-proceed-btn');
        proceedBtn.disabled = true;
        proceedBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">hourglass_top</span> Authenticating…';

        try {
            const { base: ssoBase, extraParams } = SSO_CONFIG[env];
            const body = new URLSearchParams({
                username,
                password,
                grant_type:    'password',
                client_id:     'resource_server',
                client_secret: 'resource_server',
                ...extraParams
            });
            const res = await fetch(
                `${ssoBase}/auth/realms/${encodeURIComponent(tenant)}/protocol/openid-connect/token`,
                { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body }
            );
            if (!res.ok) throw new Error(`Auth failed: ${res.status} ${res.statusText}`);
            const data = await res.json();
            if (!data.access_token) throw new Error('No access_token in response.');
            deforestToken = data.access_token;
            showDeforestScreen(2);
        } catch (err) {
            deforestError1.textContent = err.message;
            deforestError1.style.display = 'block';
        } finally {
            proceedBtn.disabled = false;
            proceedBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">lock_open</span> Authenticate & Proceed';
        }
    });

    // Screen 2 → Screen 3
    document.getElementById('deforestation-baseurl-proceed-btn').addEventListener('click', () => {
        const url = document.getElementById('deforestation-base-url').value.trim().replace(/\/$/, '');
        deforestError2.style.display = 'none';
        if (!url) {
            deforestError2.textContent = 'Base URL is required.';
            deforestError2.style.display = 'block';
            return;
        }
        deforestBaseUrl = url;
        showDeforestScreen(3);
    });

    // Generate Template
    deforestGenBtn.addEventListener('click', async () => {
        deforestError3.style.display = 'none';
        deforestGenBtn.disabled = true;
        deforestGenStatus.textContent = 'Generating…';
        try {
            const res = await fetch(
                `${deforestBaseUrl}/services/fileupload-service/api/bulk-downloads/template?feature=ONBOARD_FARMER_ASSET_FORM`,
                { headers: { 'Authorization': `Bearer ${deforestToken}` } }
            );
            if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
            const data = await res.json();
            deforestTemplateId   = data.id   ?? data.templateId   ?? data.data?.id;
            deforestTemplateName = data.name  ?? data.templateName ?? data.data?.name;
            if (!deforestTemplateId || !deforestTemplateName) throw new Error('Could not find id or name in the response.');
            deforestGenStatus.innerHTML = `<span style="color:#2e7d32;">&#10003; ID: <strong>${deforestTemplateId}</strong> &nbsp;|&nbsp; Name: <strong>${deforestTemplateName}</strong> saved.</span>`;
            deforestDlBtn.disabled = false;
            deforestDlStatus.textContent = '';
        } catch (err) {
            deforestGenStatus.textContent = '';
            deforestError3.textContent = 'Generate Template: ' + err.message;
            deforestError3.style.display = 'block';
        } finally {
            deforestGenBtn.disabled = false;
        }
    });

    // Download Template
    deforestDlBtn.addEventListener('click', async () => {
        deforestError3.style.display = 'none';
        deforestDlBtn.disabled = true;
        deforestDlStatus.textContent = 'Downloading…';
        try {
            const res = await fetch(
                `${deforestBaseUrl}/services/fileupload-service/api/bulk-downloads/mass-upload-template/${deforestTemplateId}`,
                { headers: { 'Authorization': `Bearer ${deforestToken}` } }
            );
            if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
            const blob = await res.blob();
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href = url; a.download = `${deforestTemplateName}.xlsx`; a.click();
            URL.revokeObjectURL(url);
            deforestDlStatus.innerHTML = `<span style="color:#2e7d32;">&#10003; Downloaded as <strong>${deforestTemplateName}.xlsx</strong></span>`;
        } catch (err) {
            deforestDlStatus.textContent = '';
            deforestError3.textContent = 'Download Template: ' + err.message;
            deforestError3.style.display = 'block';
        } finally {
            deforestDlBtn.disabled = false;
        }
    });

    // Sustainability checkbox — toggle required markers on dates
    document.getElementById('deforestation-sustainability').addEventListener('change', function () {
        const show = this.checked ? 'inline' : 'none';
        document.getElementById('deforestation-start-required').style.display = show;
        document.getElementById('deforestation-end-required').style.display   = show;
    });

    // Upload Template
    deforestUploadBtn.addEventListener('click', async () => {
        const file           = document.getElementById('deforestation-upload-file').files[0];
        const projectId      = document.getElementById('deforestation-project-id').value.trim();
        const startDate      = document.getElementById('deforestation-start-date').value;
        const endDate        = document.getElementById('deforestation-end-date').value;
        const sustainability = document.getElementById('deforestation-sustainability').checked;

        deforestError3.style.display = 'none';
        if (!file)      { deforestError3.textContent = 'Please select a file.';   deforestError3.style.display = 'block'; return; }
        if (!projectId) { deforestError3.textContent = 'Project ID is required.'; deforestError3.style.display = 'block'; return; }
        if (sustainability && !startDate) { deforestError3.textContent = 'Start Date is required when SUSTAINABILITY is enabled.'; deforestError3.style.display = 'block'; return; }
        if (sustainability && !endDate)   { deforestError3.textContent = 'End Date is required when SUSTAINABILITY is enabled.';   deforestError3.style.display = 'block'; return; }

        const requestDto = {
            projectId,
            ...(sustainability && startDate && { startDate }),
            ...(sustainability && endDate   && { endDate }),
            ...(sustainability && { enableFeatures: ['SUSTAINABILITY'] })
        };

        const formData = new FormData();
        formData.append('feature', 'ONBOARD_FARMER_ASSET_FORM');
        formData.append('file', file);
        formData.append('bulkUploadRequestDto', new Blob([JSON.stringify(requestDto)], { type: 'application/json' }));

        deforestUploadBtn.disabled = true;
        deforestUploadStatus.textContent = 'Uploading…';
        try {
            const res = await fetch(
                `${deforestBaseUrl}/services/fileupload-service/api/bulk-uploads/template`,
                { method: 'POST', headers: { 'Authorization': `Bearer ${deforestToken}` }, body: formData }
            );
            if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
            const data = await res.json();
            deforestUploadId = data.id ?? data.uploadId ?? data.data?.id;
            if (!deforestUploadId) throw new Error('Could not find id in the upload response.');
            deforestUploadStatus.innerHTML = `<span style="color:#2e7d32;">&#10003; Upload ID: <strong>${deforestUploadId}</strong> saved.</span>`;
            deforestProcessBtn.disabled = false;
        } catch (err) {
            deforestUploadStatus.textContent = '';
            deforestError3.textContent = 'Upload Template: ' + err.message;
            deforestError3.style.display = 'block';
        } finally {
            deforestUploadBtn.disabled = false;
        }
    });

    // Process Template
    deforestProcessBtn.addEventListener('click', async () => {
        deforestError3.style.display = 'none';
        deforestProcessBtn.disabled = true;
        deforestProcessStatus.textContent = 'Processing…';
        try {
            const res = await fetch(
                `${deforestBaseUrl}/services/fileupload-service/api/process-uploads/${deforestUploadId}`,
                { method: 'POST', headers: { 'Authorization': `Bearer ${deforestToken}` } }
            );
            if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
            deforestProcessStatus.innerHTML = `<span style="color:#2e7d32;">&#10003; Process started successfully for Upload ID: <strong>${deforestUploadId}</strong></span>`;
            deforestStatusBtn.disabled = false;
        } catch (err) {
            deforestProcessStatus.textContent = '';
            deforestError3.textContent = 'Process Template: ' + err.message;
            deforestError3.style.display = 'block';
        } finally {
            deforestProcessBtn.disabled = false;
        }
    });

    // Upload Template Status
    deforestStatusBtn.addEventListener('click', async () => {
        deforestStatusError.style.display = 'none';
        deforestStatusResponse.style.display = 'none';
        deforestStatusBtn.disabled = true;
        deforestStatusBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">hourglass_top</span> Checking…';
        try {
            const res = await fetch(
                `${deforestBaseUrl}/services/fileupload-service/api/bulk-uploads/${deforestUploadId}`,
                { headers: { 'Authorization': `Bearer ${deforestToken}` } }
            );
            if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
            const data = await res.json();
            deforestStatusJson.textContent = JSON.stringify(data, null, 2);
            deforestStatusResponse.style.display = 'block';
        } catch (err) {
            deforestStatusError.textContent = 'Upload Template Status: ' + err.message;
            deforestStatusError.style.display = 'block';
        } finally {
            deforestStatusBtn.disabled = false;
            deforestStatusBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">refresh</span> Check Status';
        }
    });

    // API 6: Publish Deforestation — reads SR Plot IDs from Excel, posts each
    const deforestPublishFile     = document.getElementById('deforestation-publish-file');
    const deforestPublishBtn      = document.getElementById('deforestation-publish-btn');
    const deforestPublishFilename = document.getElementById('deforestation-publish-filename');
    const deforestPublishTerminal = document.getElementById('deforestation-publish-terminal');

    let deforestPublishExcelData = null;
    let deforestPublishStopped = false;
    const deforestPublishStopBtn = document.getElementById('deforestation-publish-stop-btn');

    deforestPublishStopBtn.addEventListener('click', () => {
        deforestPublishStopped = true;
        deforestPublishStopBtn.disabled = true;
    });

    function publishLog(msg, color) {
        const line = document.createElement('span');
        line.style.color = color || '#d4d4d4';
        line.textContent = msg + '\n';
        deforestPublishTerminal.appendChild(line);
        deforestPublishTerminal.scrollTop = deforestPublishTerminal.scrollHeight;
    }

    deforestPublishFile.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        deforestPublishFilename.textContent = file.name;
        deforestPublishBtn.disabled = true;
        deforestPublishTerminal.style.display = 'block';
        deforestPublishTerminal.innerHTML = '';
        publishLog(`📂 Reading file: ${file.name}`, '#9cdcfe');
        try {
            const data = await file.arrayBuffer();
            // Use SheetJS if available, else fall back to CSV text parse
            let rows = [];
            if (window.XLSX) {
                const wb = XLSX.read(data, { type: 'array' });
                const ws = wb.Sheets[wb.SheetNames[0]];
                const json = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
                if (json.length < 2) throw new Error('Excel has no data rows');
                const headers = json[0].map(h => String(h).trim());
                // Find SR Plot ID column — look for header containing "SR Plot ID" (case-insensitive) else use index 1
                const srIdx = headers.findIndex(h => /sr\s*plot\s*id/i.test(h));
                const colIdx = srIdx >= 0 ? srIdx : 1;
                publishLog(`✅ Detected column: "${headers[colIdx] || 'column ' + (colIdx+1)}" (index ${colIdx})`, '#4ec9b0');
                rows = json.slice(1).map(r => String(r[colIdx] || '').trim()).filter(v => v);
            } else {
                // CSV fallback
                const text = new TextDecoder().decode(data);
                const lines = text.split(/\r?\n/).filter(l => l.trim());
                if (lines.length < 2) throw new Error('File has no data rows');
                const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
                const srIdx = headers.findIndex(h => /sr\s*plot\s*id/i.test(h));
                const colIdx = srIdx >= 0 ? srIdx : 1;
                publishLog(`✅ Detected column: "${headers[colIdx] || 'column ' + (colIdx+1)}" (index ${colIdx})`, '#4ec9b0');
                rows = lines.slice(1).map(l => {
                    const parts = l.split(',');
                    return String(parts[colIdx] || '').trim().replace(/^"|"$/g, '');
                }).filter(v => v);
            }
            deforestPublishExcelData = rows;
            publishLog(`📋 Found ${rows.length} SR Plot ID(s) to process`, '#ce9178');
            deforestPublishBtn.disabled = false;
        } catch (err) {
            publishLog(`❌ Error reading file: ${err.message}`, '#f44747');
            deforestPublishExcelData = null;
        }
    });

    deforestPublishBtn.addEventListener('click', async () => {
        if (!deforestPublishExcelData || !deforestPublishExcelData.length) return;
        if (!deforestToken || !deforestBaseUrl) {
            publishLog('❌ Missing token or base URL. Please complete authentication first.', '#f44747');
            return;
        }
        deforestPublishStopped = false;
        deforestPublishBtn.disabled = true;
        deforestPublishBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">hourglass_top</span> Publishing…';
        deforestPublishStopBtn.style.display = '';
        deforestPublishStopBtn.disabled = false;
        publishLog(`\n🚀 Starting publish for ${deforestPublishExcelData.length} record(s)…`, '#569cd6');
        publishLog('─'.repeat(50), '#555');

        let success = 0, failed = 0;
        for (let i = 0; i < deforestPublishExcelData.length; i++) {
            if (deforestPublishStopped) {
                publishLog(`⛔ Stopped by user after ${i} record(s).`, '#f4a742');
                break;
            }
            const srPlotId = deforestPublishExcelData[i];
            publishLog(`[${i+1}/${deforestPublishExcelData.length}] Publishing SR Plot ID: ${srPlotId} …`, '#d4d4d4');
            try {
                const url = `${deforestBaseUrl}/services/farm/api/deforestation/publish-status?srPlotId=${encodeURIComponent(srPlotId)}`;
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${deforestToken}`
                    },
                    body: '{}'
                });
                if (res.status === 200) {
                    publishLog(`   ✅ Success (200)`, '#4ec9b0');
                    success++;
                } else {
                    publishLog(`   ❌ Failed (${res.status}: ${res.statusText})`, '#f44747');
                    failed++;
                }
            } catch (err) {
                publishLog(`   ❌ Error: ${err.message}`, '#f44747');
                failed++;
            }
            if (i < deforestPublishExcelData.length - 1) {
                publishLog(`   ⏳ Waiting 2 seconds…`, '#808080');
                await new Promise(r => setTimeout(r, 2000));
            }
        }

        publishLog('─'.repeat(50), '#555');
        publishLog(`✔ Done — ${success} succeeded, ${failed} failed`, success > 0 && failed === 0 ? '#4ec9b0' : '#ce9178');
        deforestPublishBtn.disabled = false;
        deforestPublishBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">publish</span> Publish Deforestation';
        deforestPublishStopBtn.style.display = 'none';
    });

    // API 7: Croppable Areas Sustainability Batch
    const caBatchFile     = document.getElementById('ca-batch-file');
    const caBatchRunBtn   = document.getElementById('ca-batch-run-btn');
    const caBatchStopBtn  = document.getElementById('ca-batch-stop-btn');
    const caBatchFilename = document.getElementById('ca-batch-filename');
    const caBatchTerminal = document.getElementById('ca-batch-terminal');

    let caBatchIds      = null;
    let caBatchStopped  = false;

    function caBatchLog(msg, color) {
        const line = document.createElement('span');
        line.style.color = color || '#d4d4d4';
        line.textContent = msg + '\n';
        caBatchTerminal.appendChild(line);
        caBatchTerminal.scrollTop = caBatchTerminal.scrollHeight;
    }

    caBatchStopBtn.addEventListener('click', () => {
        caBatchStopped = true;
        caBatchStopBtn.disabled = true;
    });

    caBatchFile.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        caBatchFilename.textContent = file.name;
        caBatchRunBtn.disabled = true;
        caBatchTerminal.style.display = 'block';
        caBatchTerminal.innerHTML = '';
        caBatchLog(`📂 Reading file: ${file.name}`, '#9cdcfe');
        try {
            const data = await file.arrayBuffer();
            let ids = [];
            if (window.XLSX) {
                const wb = XLSX.read(data, { type: 'array' });
                const ws = wb.Sheets[wb.SheetNames[0]];
                const json = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
                if (json.length < 2) throw new Error('Excel has no data rows');
                const headers = json[0].map(h => String(h).trim());
                const caIdx = headers.findIndex(h => /ca\s*id/i.test(h));
                const colIdx = caIdx >= 0 ? caIdx : 0;
                caBatchLog(`✅ Detected column: "${headers[colIdx] || 'column ' + (colIdx+1)}" (index ${colIdx})`, '#4ec9b0');
                ids = json.slice(1).map(r => String(r[colIdx] || '').trim()).filter(v => v);
            } else {
                const text = new TextDecoder().decode(data);
                const lines = text.split(/\r?\n/).filter(l => l.trim());
                if (lines.length < 2) throw new Error('File has no data rows');
                const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
                const caIdx = headers.findIndex(h => /ca\s*id/i.test(h));
                const colIdx = caIdx >= 0 ? caIdx : 0;
                caBatchLog(`✅ Detected column: "${headers[colIdx] || 'column ' + (colIdx+1)}" (index ${colIdx})`, '#4ec9b0');
                ids = lines.slice(1).map(l => {
                    const parts = l.split(',');
                    return String(parts[colIdx] || '').trim().replace(/^"|"$/g, '');
                }).filter(v => v);
            }
            caBatchIds = ids;
            caBatchLog(`📋 Found ${ids.length} CA ID(s)`, '#ce9178');
            caBatchRunBtn.disabled = false;
        } catch (err) {
            caBatchLog(`❌ Error reading file: ${err.message}`, '#f44747');
            caBatchIds = null;
        }
    });

    caBatchRunBtn.addEventListener('click', async () => {
        if (!caBatchIds || !caBatchIds.length) return;
        if (!deforestToken || !deforestBaseUrl) {
            caBatchTerminal.style.display = 'block';
            caBatchLog('❌ Missing token or base URL. Please complete authentication first.', '#f44747');
            return;
        }
        const startDate = document.getElementById('ca-batch-start-date').value;
        const endDate   = document.getElementById('ca-batch-end-date').value;
        if (!startDate || !endDate) {
            caBatchTerminal.style.display = 'block';
            caBatchLog('❌ Please select both Start Date and End Date.', '#f44747');
            return;
        }

        caBatchStopped = false;
        caBatchRunBtn.disabled = true;
        caBatchRunBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">hourglass_top</span> Running…';
        caBatchStopBtn.style.display = '';
        caBatchStopBtn.disabled = false;
        caBatchTerminal.style.display = 'block';
        caBatchTerminal.innerHTML = '';

        // Send all IDs in a single POST
        caBatchLog(`🚀 Sending batch of ${caBatchIds.length} CA ID(s)…`, '#569cd6');
        caBatchLog(`   Start Date : ${startDate}`, '#9cdcfe');
        caBatchLog(`   End Date   : ${endDate}`, '#9cdcfe');
        caBatchLog('─'.repeat(50), '#555');

        const CHUNK = 10;
        let success = 0, failed = 0;
        for (let i = 0; i < caBatchIds.length; i += CHUNK) {
            if (caBatchStopped) {
                caBatchLog(`⛔ Stopped by user after ${i} record(s).`, '#f4a742');
                break;
            }
            const chunk = caBatchIds.slice(i, i + CHUNK);
            caBatchLog(`[${i+1}–${Math.min(i+CHUNK, caBatchIds.length)}/${caBatchIds.length}] Posting chunk of ${chunk.length} ID(s)…`, '#d4d4d4');
            try {
                const url = `${deforestBaseUrl}/services/farm/api/croppable-areas/sustainability/v2/batch?features=SUSTAINABILITY`;
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${deforestToken}`
                    },
                    body: JSON.stringify({ croppableAreaIds: chunk, startDate, endDate })
                });
                if (res.status === 200) {
                    let statusText = 'OK';
                    try {
                        const body = await res.json();
                        statusText = body.status || 'OK';
                    } catch {}
                    const isSuccess = statusText === 'SUCCESS';
                    caBatchLog(`   ✅ (200) Status: ${statusText}`, isSuccess ? '#4ec9b0' : '#f4a742');
                    success += chunk.length;
                } else {
                    caBatchLog(`   ❌ Failed (${res.status}: ${res.statusText})`, '#f44747');
                    failed += chunk.length;
                }
            } catch (err) {
                caBatchLog(`   ❌ Error: ${err.message}`, '#f44747');
                failed += chunk.length;
            }
            if (i + CHUNK < caBatchIds.length && !caBatchStopped) {
                caBatchLog(`   ⏳ Waiting 2 seconds…`, '#808080');
                await new Promise(r => setTimeout(r, 2000));
            }
        }

        caBatchLog('─'.repeat(50), '#555');
        caBatchLog(`✔ Done — ${success} succeeded, ${failed} failed`, success > 0 && failed === 0 ? '#4ec9b0' : '#ce9178');
        caBatchRunBtn.disabled = false;
        caBatchRunBtn.innerHTML = '<span class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:4px;">eco</span> Run Batch';
        caBatchStopBtn.style.display = 'none';
    });

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
