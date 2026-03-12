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

        const scriptNameForCfg = scriptSelect.value;
        const useFarmerId = document.getElementById('use-farmer-id')?.value;
        if (useFarmerId) config.use_farmer_id = useFarmerId;

        // 1. Threading Config
        const threadingContainer = document.getElementById('threading-config');
        if (threadingContainer && threadingContainer.style.display !== 'none') {
            config.worker_count = parseInt(document.getElementById('worker-count')?.value) || 1;
        }

        // 2. Extra Appended Config (Secondary URL & Google API)
        const secondaryGroup = document.getElementById('group-secondary-url');
        if (secondaryGroup && secondaryGroup.style.display !== 'none') {
            const secondBaseApiUrl = document.getElementById('second-base-api-url')?.value;
            if (secondBaseApiUrl) config.second_base_api_url = secondBaseApiUrl;
        }

        const googleApiConfig = document.getElementById('google-api-config');
        if (googleApiConfig && googleApiConfig.style.display !== 'none') {
            const xApiKey = document.getElementById('x-api-key')?.value;
            if (xApiKey) config.x_api_key = xApiKey;
        }

        // 3. CA Control Config
        const caControl = document.getElementById('ca-close-delete-config');
        if (caControl && caControl.style.display !== 'none') {
            config.ca_action = document.getElementById('ca-action-select')?.value || 'none';

            let caBatchSizeRaw = parseInt(document.getElementById('ca-batch-size')?.value);
            if (isNaN(caBatchSizeRaw) || caBatchSizeRaw < 1) caBatchSizeRaw = 50;
            if (caBatchSizeRaw > 100) {
                window.showToast("Batch size cannot exceed 100. Lowering to 100.", "error", "Invalid Input");
                document.getElementById('ca-batch-size').value = 100;
                caBatchSizeRaw = 100;
            }
            config.ca_batch_size = caBatchSizeRaw;
            config.ca_x_api_key = document.getElementById('ca-x-api-key')?.value || 'SEF5qQ6RTDGFWUc36SNuCKGYW1tVuGgGrX1iApUs5DGOc7MS';
        }

        // 4. Attribute Config (Generic Attributes)
        const attributeConfig = document.getElementById('attribute-config');
        if (attributeConfig && attributeConfig.style.display !== 'none') {
            const attrCount = parseInt(document.getElementById('attr-count-select').value) || 1;
            let attrKeys = [];
            ['attr-key-1', 'attr-key-2', 'attr-key-3', 'attr-key-4'].forEach((id, i) => {
                if (i < attrCount) attrKeys.push(document.getElementById(id)?.value || '');
            });
            config.attr_keys = attrKeys;
            // Many legacy scripts expect 'fields_to_remove' via the exact same array layout
            config.fields_to_remove = attrKeys;
        }

        // 5. Address Config
        const addressConfig = document.getElementById('address-config');
        if (addressConfig && addressConfig.style.display !== 'none') {
            const addrCount = parseInt(document.getElementById('addr-count-select').value) || 1;
            let addrKeys = [];
            ['address-key-1', 'address-key-2', 'address-key-3', 'address-key-4'].forEach((id, i) => {
                if (i < addrCount) {
                    const v = document.getElementById(id)?.value;
                    if (v) addrKeys.push(v);
                }
            });
            config.attr_keys = addrKeys;
            config.fields_to_remove = addrKeys;
        }

        // 6. Area Audit Config
        const areaAuditConfig = document.getElementById('area-audit-config');
        if (areaAuditConfig && areaAuditConfig.style.display !== 'none') {
            config.unit = document.getElementById('area-unit-select')?.value || 'Hectare';
            config.force_crop_audited = document.getElementById('force-crop-audited')?.value || 'none';
        }

        // 7. Variety Removal Config
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

        // 8. Time Delay Config
        const timeDelayConfig = document.getElementById('time-delay-config');
        if (timeDelayConfig && timeDelayConfig.style.display !== 'none') {
            config.delay_time = document.getElementById('delay-time-input')?.value || 1;
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
        if (scheduleModal) scheduleModal.style.display = 'block';
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

        if (parent) {
            parent.addEventListener('mouseenter', updateTooltip);
            parent.addEventListener('mouseleave', hideTooltip);
        }
        openScheduleModalBtn.addEventListener('mouseenter', updateTooltip);
        openScheduleModalBtn.addEventListener('mouseleave', hideTooltip);
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
            fetchScheduledJobs(); // Custom polling function to write next
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
        fetch('/api/scheduled_jobs')
            .then(r => r.json())
            .then(data => {
                renderJobs(data.jobs || []);
            })
            .catch(err => console.error("Failed to fetch jobs", err));
    }

    function renderJobs(jobs) {
        const schedContainer = document.getElementById('scheduled-jobs-container');
        const runContainer = document.getElementById('running-jobs-container');
        const histContainer = document.getElementById('history-jobs-container');

        const pendingJobs = jobs.filter(j => j.status === 'pending');
        const runningJobs = jobs.filter(j => j.status === 'running');
        const historyJobs = jobs.filter(j => ['completed', 'failed', 'cancelled'].includes(j.status));

        // Render Pending
        if (pendingJobs.length === 0) {
            if (schedContainer) schedContainer.innerHTML = '<p style="color:#666; font-style:italic;">No upcoming scheduled scripts.</p>';
        } else {
            if (schedContainer) schedContainer.innerHTML = pendingJobs.map(j => `
                <div id="job-card-${j.job_id}" style="border:1px solid #ddd; padding:15px; border-radius:6px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                    <div id="job-info-${j.job_id}">
                        <strong style="color:#333; font-size:1.1rem;">${j.script_name}</strong>
                        <div style="color:#666; font-size:0.9rem; margin-top:5px;" id="job-time-${j.job_id}">📅 ${new Date(j.run_time).toLocaleString()}</div>
                    </div>
                    <div style="display:flex; gap:10px;" id="job-actions-${j.job_id}">
                        <button onclick="window.runJobNow('${j.job_id}')" class="btn-primary" style="padding:6px 12px; font-size:0.9rem;">▶ Run Now</button>
                        <button onclick="window.editJob('${j.job_id}', '${j.run_time}')" class="btn-secondary" style="padding:6px 12px; font-size:0.9rem;">Edit</button>
                        <button onclick="window.deleteJob('${j.job_id}')" class="btn-secondary" style="color:#dc3545; border-color:#dc3545; padding:6px 12px; font-size:0.9rem;">Delete</button>
                    </div>
                </div>
            `).join('');
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
                    }

                    const timeStr = j.completed_at ? new Date(j.completed_at).toLocaleString() : 'Recently';

                    return `
                        <div style="border:1px solid #ddd; padding:12px; border-radius:6px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <strong style="color:#333;">${j.script_name}</strong>
                                <div style="color:#666; font-size:0.85rem; margin-top:4px;">
                                    Finished: ${timeStr}
                                </div>
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
