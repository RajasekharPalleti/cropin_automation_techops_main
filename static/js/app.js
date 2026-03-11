/**
 * app.js — Main Orchestrator
 *
 * Initialises the application after all other JS modules have loaded:
 *   - Credential persistence (localStorage)
 *   - Password visibility toggle
 *   - Script dropdown (fetch /api/scripts, populateDropdown, selectScript)
 *   - Environment custom dropdown
 *   - Auth validation helper
 *   - Template download button
 *   - Session restore UI (if a script was running when the page was reloaded)
 *
 * Depends on (window globals set by earlier scripts):
 *   window.getClientId(), window.setClientId()            — session.js
 *   window.requestWakeLock(), window.releaseWakeLock()    — wake_lock.js
 *   window.connectSSE()                                   — sse.js
 *   window.executeScriptLogic(), window.addResetButton()  — execution.js
 *   window.handleFile()                                   — execution.js
 */

document.addEventListener('DOMContentLoaded', () => {

    // 1) Initialize UI State (Deferred slightly to ensure ui.js is parsed)
    setTimeout(() => {
        if (window.loadFormState) window.loadFormState();

        // Bind form state saving to all inputs
        document.querySelectorAll('input:not([type="file"]), select').forEach(el => {
            el.addEventListener('change', window.saveFormState);
            el.addEventListener('input', window.saveFormState);
        });
    }, 100);

    // DOM refs
    const configToggle = document.getElementById('config-toggle');
    const configContent = document.getElementById('config-content');
    const scriptSelect = document.getElementById('script-select');
    const statusArea = document.getElementById('status-area');
    const generateTemplateBtn = document.getElementById('generate-template-btn');
    const consoleContent = document.getElementById('console-content');
    const consoleBox = document.getElementById('console-box');

    // Custom script dropdown elements
    const customDropdown = document.getElementById('custom-dropdown');
    const dropdownSelected = document.getElementById('dropdown-selected');
    const selectedText = document.getElementById('selected-text');
    const dropdownMenu = document.getElementById('dropdown-menu');
    const searchInput = document.getElementById('dropdown-search-input');
    const dropdownList = document.getElementById('dropdown-list');

    let scriptsData = [];
    window.scriptsData = scriptsData; // Expose for execution.js if needed

    // ================================================================
    // CREDENTIAL PERSISTENCE
    // ================================================================
    const tenantIn = document.getElementById('tenant-code');
    const userIn = document.getElementById('username');
    const passIn = document.getElementById('password');

    if (localStorage.getItem('tenant_code')) tenantIn.value = localStorage.getItem('tenant_code');
    if (localStorage.getItem('username')) userIn.value = localStorage.getItem('username');
    if (localStorage.getItem('password')) passIn.value = localStorage.getItem('password');

    const saveCreds = () => {
        localStorage.setItem('tenant_code', tenantIn.value);
        localStorage.setItem('username', userIn.value);
        localStorage.setItem('password', passIn.value);
    };
    tenantIn.addEventListener('input', saveCreds);
    userIn.addEventListener('input', saveCreds);
    passIn.addEventListener('input', saveCreds);

    // Password visibility toggle
    const eyeIcon = document.querySelector('.eye-icon');
    if (eyeIcon) {
        eyeIcon.addEventListener('click', () => {
            if (passIn.type === 'password') {
                passIn.type = 'text';
                eyeIcon.textContent = 'visibility';
            } else {
                passIn.type = 'password';
                eyeIcon.textContent = 'visibility_off';
            }
        });
    }

    // ================================================================
    // AUTH VALIDATION
    // ================================================================
    function checkAuthAndAlert() {
        const missing = [];
        if (!tenantIn.value.trim()) missing.push('Tenant Name');
        if (!userIn.value.trim()) missing.push('Username');
        if (!passIn.value.trim()) missing.push('Password');
        if (missing.length > 0) {
            window.showToast('Please enter valid ' + missing.join(', ') + ' to proceed.', 'error');
            return false;
        }
        return true;
    }
    // Expose so execution.js can call it via checkAuthAndAlert()
    window.checkAuthAndAlert = checkAuthAndAlert;

    // ================================================================
    // SCRIPT DROPDOWN — populate & select
    // ================================================================
    function populateDropdown(scripts) {
        dropdownList.innerHTML = '';
        scriptSelect.innerHTML = '<option value="" disabled selected>Select a script...</option>';

        scripts.forEach(scriptObj => {
            const scriptName = scriptObj.name;
            let displayName = scriptName.replace('.py', '').replace(/_/g, ' ');
            displayName = displayName.replace(/([a-z])([A-Z])/g, '$1 $2');

            const option = document.createElement('option');
            option.value = scriptName;
            option.textContent = displayName;
            scriptSelect.appendChild(option);

            const li = document.createElement('li');
            li.textContent = displayName;
            li.dataset.value = scriptName;
            li.addEventListener('click', () => selectScript(scriptName, displayName));
            dropdownList.appendChild(li);
        });
    }

    function selectScript(value, displayName) {
        // Close keyboard on mobile
        if (document.activeElement) document.activeElement.blur();

        if (!displayName) {
            displayName = value.replace('.py', '').replace(/_/g, ' ');
            displayName = displayName.replace(/([a-z])([A-Z])/g, '$1 $2');
        }
        if (selectedText) selectedText.textContent = displayName;
        scriptSelect.value = value;

        // Reset upload state
        window.currentUploadedFilename = null;
        if (statusArea) statusArea.innerHTML = '';
        if (consoleBox) consoleBox.style.display = 'none';

        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-upload');
        const dropText = dropZone?.querySelector('.drop-text');
        if (dropText) dropText.innerHTML = '<strong>Drag and drop file here</strong><p>Limit 200MB per file • XLSX</p>';
        if (fileInput) fileInput.value = '';

        document.getElementById('config-placeholder').style.display = 'none';
        document.getElementById('config-fields-container').style.display = 'block';

        const selectedScript = scriptsData.find(s => s.name === value);
        if (selectedScript) {
            // Primary URL
            if (selectedScript.base_api_url) document.getElementById('base-api-url').value = selectedScript.base_api_url;
            const label = document.querySelector('label[for="base-api-url"]');
            if (label && selectedScript.label) label.textContent = selectedScript.label;

            // Secondary URL
            const secGroup = document.getElementById('group-secondary-url');
            const secInput = document.getElementById('second-base-api-url');
            const secLabel = document.querySelector('label[for="second-base-api-url"]');
            if (selectedScript.second_base_api_url) {
                secGroup.style.display = 'block';
                secInput.value = selectedScript.second_base_api_url;
                if (secLabel) secLabel.textContent = selectedScript.label2 || 'Secondary Api Url';
            } else {
                secGroup.style.display = 'none';
            }

            const toggle = (id, show) => { const el = document.getElementById(id); if (el) el.style.display = show ? 'block' : 'none'; };
            
            toggle('google-api-config', selectedScript.show_google_api_config);

            toggle('pr-weather-config', selectedScript.show_pr_weather);
            toggle('attribute-config', selectedScript.show_attribute_config);
            toggle('address-config', selectedScript.show_address_config);
            toggle('area-audit-config', selectedScript.show_area_audit_config);
            toggle('variety-removal-config', selectedScript.show_variety_removal_config);
            toggle('threading-config', selectedScript.show_threading_config);
            toggle('time-delay-config', selectedScript.show_time_delay_config);
            toggle('ca-close-delete-config', selectedScript.show_ca_close_delete);
            toggle('threading-config', selectedScript.show_threading);

            // Count dropdowns
            const setupCountDropdown = (selectId, groupPrefix, max = 4) => {
                const sel = document.getElementById(selectId);
                if (!sel || sel.dataset.countBound) return;
                sel.dataset.countBound = 'true';
                sel.addEventListener('change', function () {
                    const count = parseInt(this.value);
                    for (let i = 1; i <= max; i++) {
                        const g = document.getElementById(`${groupPrefix}-${i}`);
                        if (g) g.style.display = (i === 1 || i <= count) ? 'block' : 'none';
                    }
                });
            };
            setupCountDropdown('attr-count-select', 'group-key');
            setupCountDropdown('removal-count-select', 'group-remove');
            setupCountDropdown('addr-count-select', 'group-addr');

            // Upload vs Direct Run mode
            const stepOne = document.querySelector('.step-one');
            const uploadLabel = document.querySelector('.step-two label');
            const runContainer = document.getElementById('run-container');
            const dropZoneEl = document.getElementById('drop-zone');

            if (selectedScript.requires_input === false) {
                if (stepOne) stepOne.style.display = 'none';
                if (dropZoneEl) dropZoneEl.style.display = 'none';
                if (uploadLabel) uploadLabel.style.display = 'none';
                if (runContainer) runContainer.style.display = 'flex';
                if (statusArea) statusArea.innerHTML = '<div style="color: blue;">Ready to run (No input file required).</div>';
            } else {
                if (stepOne) stepOne.style.display = 'block';
                if (dropZoneEl) dropZoneEl.style.display = 'flex';
                if (uploadLabel) uploadLabel.style.display = 'block';
                if (runContainer) runContainer.style.display = 'none';
            }

            // Script details panel
            const detailsDesc = document.getElementById('script-description');
            const detailsInputs = document.getElementById('script-inputs');
            const detailsInputsContainer = document.getElementById('details-inputs-container');
            if (detailsDesc) detailsDesc.textContent = selectedScript.description || 'No description available.';
            if (detailsInputs) detailsInputs.textContent = selectedScript.input_description || 'Standard Excel Input.';
            if (detailsInputsContainer) detailsInputsContainer.style.display = 'flex';
        }

        scriptSelect.dispatchEvent(new Event('change'));
        closeDropdown();
    }
    // Expose so session restore can call selectScript(savedName)
    window.selectScript = selectScript;

    // Fetch scripts from API
    fetch('/api/scripts')
        .then(r => r.json())
        .then(data => {
            scriptsData = data.scripts;
            window.scriptsData = scriptsData;
            populateDropdown(scriptsData);
        });

    // Dropdown open/close
    dropdownSelected.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdownMenu.classList.toggle('show');
        dropdownSelected.classList.toggle('active');
        if (dropdownMenu.classList.contains('show')) searchInput.focus();
    });

    function closeDropdown() {
        dropdownMenu.classList.remove('show');
        dropdownSelected.classList.remove('active');
    }

    // Search filter
    searchInput.addEventListener('click', e => e.stopPropagation());
    searchInput.addEventListener('input', (e) => {
        // Split the search query by any whitespace or non-alphanumeric characters like _ or -
        const tokens = e.target.value.toLowerCase().split(/[\s_\-]+/).filter(t => t.trim() !== '');

        const filtered = scriptsData.filter(s => {
            // Re-create the exact display name used in the UI
            let displayName = s.name.replace('.py', '').replace(/_/g, ' ');
            displayName = displayName.replace(/([a-z])([A-Z])/g, '$1 $2');

            const searchableText = (s.name + ' ' + displayName).toLowerCase();

            // Script matches if EVERY token typed by the user is found in either the name or display name
            return tokens.every(token => searchableText.includes(token));
        });
        dropdownList.innerHTML = '';
        if (filtered.length > 0) {
            filtered.forEach(scriptObj => {
                const scriptName = scriptObj.name;
                let displayName = scriptName.replace('.py', '').replace(/_/g, ' ');
                displayName = displayName.replace(/([a-z])([A-Z])/g, '$1 $2');

                const li = document.createElement('li');
                li.textContent = displayName;
                li.dataset.value = scriptName;
                li.addEventListener('click', () => selectScript(scriptName, displayName));
                dropdownList.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.className = 'no-results';
            li.textContent = 'No scripts found';
            dropdownList.appendChild(li);
        }
    });

    // Close dropdowns on outside click
    document.addEventListener('click', (e) => {
        if (customDropdown && !customDropdown.contains(e.target)) closeDropdown();
        const envDropdown = document.getElementById('env-dropdown');
        if (envDropdown && !envDropdown.contains(e.target)) closeEnvDropdown();
    });

    // Auto-open config panel on script selection
    scriptSelect.addEventListener('change', () => {
        if (configContent) configContent.classList.add('open');
    });


    // ================================================================
    // ENVIRONMENT DROPDOWN
    // ================================================================
    const envDropdown = document.getElementById('env-dropdown');
    const envSelected = document.getElementById('env-selected');
    const envSelectedText = document.getElementById('env-selected-text');
    const envMenu = document.getElementById('env-menu');
    const envList = document.getElementById('env-list');
    const envNativeSelect = document.getElementById('environment');

    envSelected.addEventListener('click', (e) => {
        e.stopPropagation();
        envMenu.classList.toggle('show');
        envSelected.classList.toggle('active');
        closeDropdown();
    });

    function closeEnvDropdown() {
        envMenu.classList.remove('show');
        envSelected.classList.remove('active');
    }

    envList.querySelectorAll('li').forEach(item => {
        item.addEventListener('click', () => {
            envSelectedText.textContent = item.textContent;
            envNativeSelect.value = item.getAttribute('data-value');
            envNativeSelect.dispatchEvent(new Event('change'));
            closeEnvDropdown();
        });
    });


    // ================================================================
    // RUN BUTTON — opens confirmation modal
    // ================================================================
    const runBtn = document.getElementById('run-script-btn');
    if (runBtn) {
        runBtn.addEventListener('click', () => {
            const selectedScriptName = scriptSelect.value;
            const selectedScript = scriptsData.find(s => s.name === selectedScriptName);

            if (selectedScript && selectedScript.requires_input !== false) {
                if (!window.currentUploadedFilename) {
                    window.showToast('No file uploaded', 'error');
                    return;
                }
            }

            const confirmModal = document.getElementById('confirmation-modal');
            const confirmTenant = document.getElementById('confirm-tenant');
            const confirmUser = document.getElementById('confirm-user');
            const confirmScriptName = document.getElementById('confirm-script-name');

            if (confirmTenant) confirmTenant.textContent = tenantIn.value || 'Not Set';
            if (confirmUser) confirmUser.textContent = userIn.value || 'Not Set';
            if (confirmScriptName) confirmScriptName.textContent = scriptSelect.value || 'Unknown Script';

            if (confirmModal) confirmModal.style.display = 'block';
        });
    }


    // ================================================================
    // TEMPLATE DOWNLOAD
    // ================================================================
    if (generateTemplateBtn) {
        generateTemplateBtn.addEventListener('click', () => {
            if (!scriptSelect.value) {
                window.showToast('Please select a script first.', 'error');
                return;
            }

            const templateInfoBox = document.getElementById('template-info-box');
            if (templateInfoBox) {
                templateInfoBox.style.color = 'blue';
                templateInfoBox.innerHTML = '<strong>Generating template...</strong>';
            }

            fetch('/api/template/' + scriptSelect.value)
                .then(r => {
                    if (r.ok) return r.blob();
                    return r.json().then(err => { throw new Error(err.detail || 'Error generating template'); });
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'Template_' + scriptSelect.value.replace('.py', '.xlsx');
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    if (templateInfoBox) {
                        templateInfoBox.style.color = 'green';
                        templateInfoBox.textContent = 'Template downloaded successfully';
                    }
                })
                .catch(err => {
                    if (templateInfoBox) {
                        templateInfoBox.style.color = 'red';
                        templateInfoBox.textContent = 'Template Error: ' + err.message;
                    }
                    window.showToast('Template Error: ' + err.message, 'error');
                });
        });
    }


    // ================================================================
    // SESSION RESTORE
    // If the page refreshes mid-run, show the running state and
    // reconnect the SSE log stream.
    // ================================================================
    if (sessionStorage.getItem('is_script_running') === 'true') {
        const runContainer = document.getElementById('run-container');
        const stopBtn = document.getElementById('stop-script-btn');

        const savedScriptName = sessionStorage.getItem('running_script_name');
        if (savedScriptName) selectScript(savedScriptName);

        if (consoleBox) consoleBox.style.display = 'block';
        if (runContainer) runContainer.style.display = 'flex';
        if (runBtn) { runBtn.disabled = true; runBtn.innerHTML = '<span class="spinner"></span> Restoring session...'; }
        if (stopBtn) { stopBtn.style.display = 'inline-block'; stopBtn.disabled = false; }

        const resumeLine = document.createElement('div');
        resumeLine.className = 'console-line';
        resumeLine.style.color = '#FFA500';
        resumeLine.textContent = '> Restoring session connection...';
        if (consoleContent) consoleContent.appendChild(resumeLine);

        if (window.requestWakeLock) window.requestWakeLock();
        if (window.addResetButton) window.addResetButton();

        const clientId = window.getClientId ? window.getClientId() : sessionStorage.getItem('clientId');

        fetch('/api/status/' + clientId)
            .then(r => r.json())
            .then(status => {
                if (status.is_running) {
                    if (runBtn) runBtn.innerHTML = '<span class="spinner"></span> Processing...';

                    const confirmedLine = document.createElement('div');
                    confirmedLine.className = 'console-line';
                    confirmedLine.style.color = '#00AA00';
                    confirmedLine.textContent = '> Session confirmed. Resuming logs...';
                    if (consoleContent) consoleContent.appendChild(confirmedLine);

                    if (window.connectSSE) window.connectSSE();
                } else {
                    // Ghost session — server restarted
                    sessionStorage.setItem('is_script_running', 'false');
                    sessionStorage.removeItem('running_script_name');
                    if (window.releaseWakeLock) window.releaseWakeLock();
                    if (statusArea) statusArea.innerHTML = '<div style="color: orange;">Previous session was not found on server. Ready for new run.</div>';
                    if (consoleBox) consoleBox.style.display = 'none';
                    if (runBtn) { runBtn.disabled = false; runBtn.innerHTML = '▶ Run Script'; }
                    if (stopBtn) stopBtn.style.display = 'none';
                    const resetBtn = document.getElementById('reset-session-btn');
                    if (resetBtn) resetBtn.remove();
                }
            })
            .catch(err => {
                console.error('Status Check Failed:', err);
                const line = document.createElement('div');
                line.className = 'console-line';
                line.style.color = 'red';
                line.textContent = '> Warning: Could not reach server to verify status. Check network connection.';
                if (consoleContent) consoleContent.appendChild(line);
            });
    }

});
