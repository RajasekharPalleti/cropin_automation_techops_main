document.addEventListener('DOMContentLoaded', () => {
    const configToggle = document.getElementById('config-toggle');
    const configContent = document.getElementById('config-content');
    const scriptSelect = document.getElementById('script-select');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const statusArea = document.getElementById('status-area');
    const generateTemplateBtn = document.getElementById('generate-template-btn');

    // Prevent accidental refresh
    window.addEventListener('beforeunload', (e) => {
        if (localStorage.getItem('is_script_running') === 'true') {
            const msg = "The session is running, please wait until finished or stop the process to proceed.";
            e.preventDefault();
            return msg;
        }
    });

    // --- Credential Persistence ---
    const tenantIn = document.getElementById('tenant-code');
    const userIn = document.getElementById('username');
    const passIn = document.getElementById('password');

    // 1. Load from Storage
    if (localStorage.getItem('tenant_code')) tenantIn.value = localStorage.getItem('tenant_code');
    if (localStorage.getItem('username')) userIn.value = localStorage.getItem('username');
    if (localStorage.getItem('password')) passIn.value = localStorage.getItem('password');

    // 2. Save on Change
    const saveCreds = () => {
        localStorage.setItem('tenant_code', tenantIn.value);
        localStorage.setItem('username', userIn.value);
        localStorage.setItem('password', passIn.value);
    };

    tenantIn.addEventListener('input', saveCreds);
    userIn.addEventListener('input', saveCreds);
    passIn.addEventListener('input', saveCreds);

    // Password Toggle
    const eyeIcon = document.querySelector('.eye-icon');

    eyeIcon.addEventListener('click', () => {
        if (passIn.type === 'password') {
            passIn.type = 'text';
            eyeIcon.textContent = '🙈'; // Monkey covering eyes (hidden) or just a slash eye
        } else {
            passIn.type = 'password';
            eyeIcon.textContent = '👁️';
        }
    });

    // Custom Dropdown Elements
    const customDropdown = document.getElementById('custom-dropdown');
    const dropdownSelected = document.getElementById('dropdown-selected');
    const selectedText = document.getElementById('selected-text');
    const dropdownMenu = document.getElementById('dropdown-menu');
    const searchInput = document.getElementById('dropdown-search-input');
    const dropdownList = document.getElementById('dropdown-list');

    let scriptsData = [];

    // Populate Scripts
    fetch('/api/scripts')
        .then(response => response.json())
        .then(data => {
            scriptsData = data.scripts; // Now objects {name: "...", url: "..."}
            populateDropdown(scriptsData);

            // Restore Selection if Running
            // Note: Logic moved to Status Check block to avoid ghost sessions
        });

    function populateDropdown(scripts) {
        // Clear existing
        dropdownList.innerHTML = '';
        scriptSelect.innerHTML = '<option value="" disabled selected>Select a script...</option>';

        scripts.forEach(scriptObj => {
            const scriptName = scriptObj.name;

            // Populate hidden select for compatibility
            const option = document.createElement('option');
            option.value = scriptName;
            option.textContent = scriptName;
            scriptSelect.appendChild(option);

            // Populate custom list
            const li = document.createElement('li');
            li.textContent = scriptName;
            li.dataset.value = scriptName;
            li.addEventListener('click', () => {
                selectScript(scriptName);
            });
            dropdownList.appendChild(li);
        });
    }

    function selectScript(value) {
        selectedText.textContent = value;
        scriptSelect.value = value;

        // Reset state
        currentUploadedFilename = null;
        statusArea.innerHTML = '';
        consoleBox.style.display = 'none';

        // Reset Drop Zone text
        const dropText = dropZone.querySelector('.drop-text');
        if (dropText) {
            dropText.innerHTML = `<strong>Drag and drop file here</strong><p>Limit 200MB per file • XLSX</p>`;
        }
        // Clear file input so 'change' event fires even if same file selected again
        fileInput.value = '';

        // Show config fields if script is selected
        document.getElementById('config-placeholder').style.display = 'none';
        document.getElementById('config-fields-container').style.display = 'block';

        // Auto-update API URL & Label & Extended Config based on selection
        const selectedScript = scriptsData.find(s => s.name === value);

        // UI Toggle for Direct Run vs Upload
        const stepOne = document.querySelector('.step-one');
        // dropZone is already defined in outer scope
        const uploadLabel = document.querySelector('.step-two label'); // "Upload filled Excel"
        const runContainer = document.getElementById('run-container');

        if (selectedScript) {
            if (selectedScript.url) document.getElementById('put-api-url').value = selectedScript.url;
            if (selectedScript.label) {
                const label = document.querySelector('label[for="put-api-url"]');
                if (label) label.textContent = selectedScript.label;
            }

            // Secondary URL Logic
            const secGroup = document.getElementById('group-secondary-url');
            const secInput = document.getElementById('secondary-api-url');
            const secLabel = document.querySelector('label[for="secondary-api-url"]');

            if (selectedScript.url2) {
                secGroup.style.display = 'block';
                secInput.value = selectedScript.url2;
                if (selectedScript.label2) secLabel.textContent = selectedScript.label2;
                else secLabel.textContent = "Secondary Api Url";
            } else {
                secGroup.style.display = 'none';
            }

            // Populate Extended Config
            const extendedConfigDiv = document.getElementById('extended-config');

            if (selectedScript.name === 'Add_Users.py') {
                extendedConfigDiv.style.display = 'block';
                // Only show API Key field, hide others if possible or just show all
                // For simplicity, showing all but we only care about x-api-key
                document.getElementById('dataset').closest('.input-group').style.display = 'none';
                document.getElementById('load-type').closest('.input-group').style.display = 'none';
                document.getElementById('x-api-key').closest('.input-group').style.display = 'block';

                // Update label for x-api-key to say Google API Key
                document.querySelector('label[for="x-api-key"]').textContent = "Google API Key";

            } else if (selectedScript.name === 'GetDiscrollsData.py') {
                extendedConfigDiv.style.display = 'block';
                document.getElementById('dataset').closest('.input-group').style.display = 'block';
                document.getElementById('load-type').closest('.input-group').style.display = 'block';
                document.getElementById('x-api-key').closest('.input-group').style.display = 'block';
                document.querySelector('label[for="x-api-key"]').textContent = "X-API-KEY";
            } else {
                extendedConfigDiv.style.display = 'none';
            }

            // Toggle PR Config (shared for PR enablement scripts)
            const prConfig = document.getElementById('pr-weather-config');
            if (prConfig) {
                if (selectedScript.name === 'PR_Enablement.py' || selectedScript.name === 'PR_and_Weather_Enablement.py' || selectedScript.name === 'PR_Enablement_Bulk.py') {
                    prConfig.style.display = 'block';
                } else {
                    prConfig.style.display = 'none';
                }
            }

            // Toggle Asset Attribute Config
            const attributeConfig = document.getElementById('attribute-config');
            if (attributeConfig) {
                if (selectedScript.name === 'Update_Asset_Additional_Attribute.py' || selectedScript.name === 'Update_Farmer_Additional_Attribute.py' || selectedScript.name === 'Update_Farmer_Details.py' || selectedScript.name === 'Update_Asset_Details.py') {
                    attributeConfig.style.display = 'block';
                } else {
                    attributeConfig.style.display = 'none';
                }
            }

            // Toggle Address Config
            const addrConfig = document.getElementById('address-config');
            if (addrConfig) {
                if (selectedScript.name === 'Update_Farmer_Address.py' || selectedScript.name === 'Update_Asset_Address.py') {
                    addrConfig.style.display = 'block';
                } else {
                    addrConfig.style.display = 'none';
                }
            }

            // Toggle Area Audit Config
            const areaConfig = document.getElementById('area-audit-config');
            if (areaConfig) {
                if (selectedScript.name === 'Area_Audit_To_CA.py') {
                    areaConfig.style.display = 'block';
                } else {
                    areaConfig.style.display = 'none';
                }
            }

            // Toggle Update DOS Config
            const dosConfig = document.getElementById('update-dos-config');
            if (dosConfig) {
                if (selectedScript.name === 'Update_DOS_Variety_to_CA.py') {
                    dosConfig.style.display = 'block';
                } else {
                    dosConfig.style.display = 'none';
                }
            }

            // Logic for Attribute Count Dropdown
            const attrCountSelect = document.getElementById('attr-count-select');
            if (attrCountSelect) {
                attrCountSelect.addEventListener('change', function () {
                    const count = parseInt(this.value);
                    document.getElementById('group-key-1').style.display = 'block'; // Always show 1
                    document.getElementById('group-key-2').style.display = count >= 2 ? 'block' : 'none';
                    document.getElementById('group-key-3').style.display = count >= 3 ? 'block' : 'none';
                    document.getElementById('group-key-4').style.display = count >= 4 ? 'block' : 'none';
                });
            }

            // Logic for Address Count Dropdown
            const addrCountSelect = document.getElementById('addr-count-select');
            if (addrCountSelect) {
                addrCountSelect.addEventListener('change', function () {
                    const count = parseInt(this.value);
                    document.getElementById('group-addr-1').style.display = 'block'; // Always show 1
                    document.getElementById('group-addr-2').style.display = count >= 2 ? 'block' : 'none';
                    document.getElementById('group-addr-3').style.display = count >= 3 ? 'block' : 'none';
                    document.getElementById('group-addr-4').style.display = count >= 4 ? 'block' : 'none';
                });
            }

            if (selectedScript.requires_input === false) {
                // Direct Run Mode
                stepOne.style.display = 'none';
                dropZone.style.display = 'none';
                uploadLabel.style.display = 'none';
                runContainer.style.display = 'flex';
                statusArea.innerHTML = '<div style="color: blue;">Ready to run (No input file required).</div>';
            } else {
                // Default Upload Mode
                stepOne.style.display = 'block';
                dropZone.style.display = 'flex'; // Restore flex
                uploadLabel.style.display = 'block';
                runContainer.style.display = 'none'; // Hide until upload
            }

            // --- Populate Script Details ---
            const detailsCard = document.getElementById('script-details-card');
            const detailsDesc = document.getElementById('script-description');
            const detailsInputs = document.getElementById('script-inputs');
            const detailsInputsContainer = document.getElementById('details-inputs-container');

            if (selectedScript) {
                // Card is always visible
                detailsDesc.textContent = selectedScript.description || "No description available.";
                detailsInputs.textContent = selectedScript.input_description || "Standard Excel Input.";
                if (detailsInputsContainer) detailsInputsContainer.style.display = 'flex';
            } else {
                // Reset to default
                detailsDesc.textContent = "Please select the script to show the details.";
                if (detailsInputsContainer) detailsInputsContainer.style.display = 'none';
            }
        }

        // Trigger change event manually for listeners
        const event = new Event('change');
        scriptSelect.dispatchEvent(event);

        closeDropdown();
    }

    // Toggle Dropdown
    dropdownSelected.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdownMenu.classList.toggle('show');
        dropdownSelected.classList.toggle('active');
        if (dropdownMenu.classList.contains('show')) {
            searchInput.focus();
        }
    });

    // Search Filter
    searchInput.addEventListener('click', (e) => {
        e.stopPropagation();
    });

    searchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        // Filter by name
        const filtered = scriptsData.filter(s => s.name.toLowerCase().includes(term));

        dropdownList.innerHTML = '';
        if (filtered.length > 0) {
            filtered.forEach(scriptObj => {
                const scriptName = scriptObj.name;
                const li = document.createElement('li');
                li.textContent = scriptName;
                li.dataset.value = scriptName;
                li.addEventListener('click', () => {
                    selectScript(scriptName);
                });
                dropdownList.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.className = 'no-results';
            li.textContent = 'No scripts found';
            dropdownList.appendChild(li);
        }
    });

    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!customDropdown.contains(e.target)) {
            closeDropdown();
        }
        if (!envDropdown.contains(e.target)) {
            closeEnvDropdown();
        }
    });

    function closeDropdown() {
        dropdownMenu.classList.remove('show');
        dropdownSelected.classList.remove('active');
    }

    // Auto-open Config on Script Selection (Existing logic listens to scriptSelect change)
    scriptSelect.addEventListener('change', () => {
        configContent.classList.add('open');
    });

    // --- Environment Custom Dropdown Logic ---
    const envDropdown = document.getElementById('env-dropdown');
    const envSelected = document.getElementById('env-selected');
    const envSelectedText = document.getElementById('env-selected-text');
    const envMenu = document.getElementById('env-menu');
    const envList = document.getElementById('env-list');
    const envNativeSelect = document.getElementById('environment');

    // Toggle Env Dropdown
    envSelected.addEventListener('click', (e) => {
        e.stopPropagation();
        envMenu.classList.toggle('show');
        envSelected.classList.toggle('active');
        // Close other dropdown if open
        closeDropdown();
    });

    function closeEnvDropdown() {
        envMenu.classList.remove('show');
        envSelected.classList.remove('active');
    }

    // Handle Env Selection
    const envItems = envList.querySelectorAll('li');
    envItems.forEach(item => {
        item.addEventListener('click', () => {
            const value = item.getAttribute('data-value');
            const text = item.textContent;

            // UI Update
            envSelectedText.textContent = text;

            // Sync with hidden select
            envNativeSelect.value = value;

            closeEnvDropdown();
        });
    });

    // --- Auth Validation Helper ---
    function checkAuthAndAlert() {
        const missing = [];
        if (!tenantIn.value.trim()) missing.push('Tenant Name');
        if (!userIn.value.trim()) missing.push('Username');
        if (!passIn.value.trim()) missing.push('Password');

        if (missing.length > 0) {
            alert('Please enter valid ' + missing.join(', ') + ' to proceed.');
            return false;
        }
        return true;
    }

    // Handle Drag & Drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');

        if (!checkAuthAndAlert()) {
            return;
        }

        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    // Intercept Browse Click
    fileInput.addEventListener('click', (e) => {
        if (!checkAuthAndAlert()) {
            e.preventDefault(); // Stop file dialog from opening
        }
    });

    fileInput.addEventListener('change', (e) => {
        console.log('File input changed:', e.target.files);
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });

    let currentUploadedFilename = null;
    const runContainer = document.getElementById('run-container');
    const runBtn = document.getElementById('run-script-btn');
    const consoleBox = document.getElementById('console-box');

    // Create STOP Button dynamically
    const stopBtn = document.createElement('button');
    stopBtn.id = 'stop-script-btn';
    stopBtn.textContent = 'Stop Process';
    stopBtn.style.cssText = 'display: none; background-color: #ff4444; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-weight: bold;';
    runContainer.appendChild(stopBtn);

    stopBtn.addEventListener('click', () => {
        if (confirm("Are you sure you want to stop the running process?")) {
            stopBtn.disabled = true;
            stopBtn.textContent = 'Stopping...';
            fetch('/api/stop/' + clientId, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    console.log(data);
                    const stopLine = document.createElement('div');
                    stopLine.className = 'console-line';
                    stopLine.style.color = 'orange';
                    stopLine.textContent = '> Stop requested. Waiting for script to terminate...';
                    consoleContent.appendChild(stopLine);
                })
                .catch(err => console.error("Stop Failed:", err));
        }
    });

    const consoleContent = document.getElementById('console-content');

    // Generate persistent client ID
    let clientId = localStorage.getItem('clientId');
    if (!clientId) {
        clientId = 'client_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('clientId', clientId);
    }

    // SSE Manager
    let evtSource = null;

    function connectSSE(onOpen = null) {
        if (evtSource && evtSource.readyState !== EventSource.CLOSED) return;

        console.log("Connecting SSE for logs...");
        evtSource = new EventSource('/api/logs/' + clientId);

        evtSource.onopen = () => {
            console.log("SSE Connected");
            if (onOpen) onOpen();
        };

        evtSource.onmessage = (event) => {
            // Check for Special Events
            if (event.data.startsWith('JOB_COMPLETED::')) {
                const filename = event.data.split('::')[1];

                const finishLine = document.createElement('div');
                finishLine.className = 'console-line';
                finishLine.style.color = '#00ff00';
                finishLine.textContent = '> Execution Finished. Downloading ' + filename + '...';
                consoleContent.appendChild(finishLine);
                consoleContent.scrollTop = consoleContent.scrollHeight;

                localStorage.setItem('is_script_running', 'false');

                // Trigger Download
                window.location.href = '/api/download/' + filename;

                statusArea.innerHTML = '<div style="color: green;">Success! Check downloads.</div>';
                runBtn.disabled = false;
                runBtn.innerHTML = '▶ Run Script';
                stopBtn.style.display = 'none'; // Hide Stop

                // Close SSE
                if (evtSource) {
                    evtSource.close();
                    evtSource = null;
                }
                const closeLine = document.createElement('div');
                closeLine.className = 'console-line';
                closeLine.style.color = 'green';
                closeLine.textContent = '> Connection closed. Job Done.';
                consoleContent.appendChild(closeLine);
                return;
            }

            if (event.data.startsWith('JOB_FAILED::')) {
                const errorMsg = event.data.split('::')[1];
                const errLine = document.createElement('div');
                errLine.className = 'console-line';
                errLine.style.color = '#ff4444';
                errLine.textContent = '> ERROR: ' + errorMsg;
                consoleContent.appendChild(errLine);
                consoleContent.scrollTop = consoleContent.scrollHeight;

                statusArea.innerHTML = '<div style="color: red;">Execution Failed</div>';
                runBtn.disabled = false;
                runBtn.innerHTML = '▶ Run Script';
                stopBtn.style.display = 'none'; // Hide Stop
                localStorage.setItem('is_script_running', 'false');
                return;
            }

            // Normal Log
            const logLine = document.createElement('div');
            logLine.className = 'console-line';
            logLine.textContent = '> ' + event.data;
            consoleContent.appendChild(logLine);
            consoleContent.scrollTop = consoleContent.scrollHeight; // Auto-scroll
        };

        evtSource.onerror = (err) => {
            console.error("SSE Error:", err);
            // Don't close immediately, it might reconnect.
        };
    }

    // Check if we need to restore session
    if (localStorage.getItem('is_script_running') === 'true') {
        const consoleBox = document.getElementById('console-box');
        const runBtn = document.getElementById('run-script-btn');

        // Verify with server if it's ACTUALLY running
        fetch('/api/status/' + clientId)
            .then(r => r.json())
            .then(status => {
                if (status.is_running) {
                    // SERVER CONFIRMED: Proceed with Restore
                    const savedScriptName = localStorage.getItem('running_script_name');
                    if (savedScriptName) {
                        selectScript(savedScriptName);
                        if (consoleBox) consoleBox.style.display = 'block';
                        if (runBtn) runBtn.disabled = true;
                    }
                    consoleBox.style.display = 'block';
                    runBtn.disabled = true;
                    stopBtn.style.display = 'inline-block'; // Show Stop on resume
                    consoleContent.innerHTML = '';
                    const resumeLine = document.createElement('div');
                    resumeLine.className = 'console-line';
                    resumeLine.style.color = '#FFA500'; // Orange
                    resumeLine.textContent = '> The session is running, please wait until finished or stop the process to proceed.';
                    consoleContent.appendChild(resumeLine);
                    connectSSE();

                    // Add Reset Button
                    addResetButton();
                } else {
                    // SERVER DENIED: Ghost Session (Server likely restarted)
                    console.warn("Server reported no active task. Clearing ghost session.");
                    localStorage.setItem('is_script_running', 'false');
                    localStorage.removeItem('running_script_name');

                    // Optional: Notify user
                    if (statusArea) statusArea.innerHTML = '<div style="color: orange;">Previous session was lost (Server restarted). Ready for new run.</div>';

                    // Reset UI
                    if (consoleBox) consoleBox.style.display = 'none';
                    if (runBtn) {
                        runBtn.disabled = false;
                        runBtn.innerHTML = '▶ Run Script';
                    }
                }
            })
            .catch(err => {
                console.error("Status Check Failed:", err);
            });
    }

    function addResetButton() {
        // Check if exists
        if (document.getElementById('reset-session-btn')) return;

        const resetBtn = document.createElement('button');
        resetBtn.id = 'reset-session-btn';
        resetBtn.textContent = 'Force Reset';
        resetBtn.style.cssText = 'margin-left: 10px; background-color: #ff4444; color: white; border: none; padding: 5px 10px; cursor: pointer; border-radius: 4px;';

        // Append near Run button or Status area
        const runContainer = document.getElementById('run-container');
        runContainer.appendChild(resetBtn);

        resetBtn.addEventListener('click', () => {
            if (confirm("Are you sure you want to force reset the session? Any running task logs will be disconnected.")) {
                localStorage.setItem('is_script_running', 'false');
                localStorage.removeItem('running_script_name');
                location.reload();
            }
        });
    }

    function handleFile(file) {
        console.log('Handling file:', file);
        if (!scriptSelect.value) {
            console.warn('No script selected!');
            alert('Please select a script first.');
            return;
        }

        // Update Drop Zone UI to show file
        const dropText = dropZone.querySelector('.drop-text');
        if (dropText) {
            dropText.innerHTML = `<strong>${file.name}</strong><p>Ready to upload</p>`;
        }

        // 1. Upload File immediately
        const formData = new FormData();
        formData.append('file', file);

        statusArea.innerHTML = '<div style="color: blue;">Uploading ' + file.name + '...</div>';

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                currentUploadedFilename = data.filename;
                statusArea.innerHTML = '<div style="color: green;">Uploaded: ' + file.name + '</div>';
                runContainer.style.display = 'flex';
                // Also update dropzone to show success
                if (dropText) {
                    dropText.innerHTML = `<strong>${file.name}</strong><p style="color: green;">✅ Uploaded Successfully</p>`;
                }
            })
            .catch(err => {
                statusArea.innerHTML = '<div style="color: red;">Upload Failed: ' + err.message + '</div>';
                if (dropText) {
                    dropText.innerHTML = `<strong>${file.name}</strong><p style="color: red;">❌ Upload Failed</p>`;
                }
            });
    }

    runBtn.addEventListener('click', () => {
        // Check requirement
        const selectedScriptName = scriptSelect.value;
        const selectedScript = scriptsData.find(s => s.name === selectedScriptName);

        // Only require file if script requires input
        if (selectedScript && selectedScript.requires_input !== false) {
            if (!currentUploadedFilename) {
                alert("No file uploaded");
                return;
            }
        }

        // Show console
        consoleBox.style.display = 'block';
        setTimeout(() => {
            const mainContent = document.querySelector('.main-content');
            mainContent.scrollTo({ top: mainContent.scrollHeight, behavior: 'smooth' });
        }, 0);

        consoleContent.innerHTML = ''; // Clear previous
        const connLine = document.createElement('div');
        connLine.className = 'console-line';
        connLine.textContent = '> Connecting to console...';
        consoleContent.appendChild(connLine);
        consoleContent.appendChild(connLine);
        runBtn.disabled = true;
        runBtn.innerHTML = '<span class="spinner"></span> Processing...';
        stopBtn.style.display = 'inline-block'; // Show Stop 
        stopBtn.disabled = false;
        stopBtn.textContent = 'Stop Process';

        // Persist State
        localStorage.setItem('is_script_running', 'true');
        localStorage.setItem('running_script_name', scriptSelect.value);

        // HARD RESET: Close existing connection if any
        if (evtSource) {
            console.log("Closing existing SSE connection before new run.");
            evtSource.close();
            evtSource = null;
        }

        // Clear Session on Server first, THEN connect SSE, THEN start execution
        fetch('/api/clear_session/' + clientId, { method: 'POST' })
            .then(() => {
                // console.log("Session cleared.");
                connectSSE(() => {
                    startExecution();
                });
            })
            .catch(err => {
                console.error("Failed to clear session:", err);
                const warnLine = document.createElement('div');
                warnLine.className = 'console-line';
                warnLine.style.color = 'orange';
                warnLine.textContent = '> Warning: Could not clear previous session logs. You may see duplicate history.';
                consoleContent.appendChild(warnLine);

                connectSSE(() => {
                    startExecution();
                });
            });

        // startExecution is called by onopen, so just connectSSE is enough to trigger the chain
        // BUT wait, onopen calls startExecution ONLY if sseConnected was set.
        // Let's verify startExecution location.
        // The previous code had:
        // connectSSE();
        // startExecution();
        // But connectSSE -> onopen -> startExecution call logic was: 
        // "Only start execution once we know we are connected".

        // Actually, looking at previous file content, `startExecution` was DEFINED inside the click handler
        // but called explicitly after `connectSSE()` in the snippet I replaced?
        // No, in step 21/30/etc it was:
        // evtSource.onopen = () => { ... if(sseConnected) startExecution(); }

        // So I just need to call connectSSE().

        // Wait, startExecution function definition is inside the click handler scope.
        // If I move connectSSE into a .then(), `startExecution` must be available to onopen?
        // `connectSSE` is defined in outer scope. It uses `onopen`.
        // `onopen` calls `startExecution`.
        // `startExecution` is defined INSIDE the click handler.
        // THIS IS A SCOPE PROBLEM. `connectSSE` (global) cannot call `startExecution` (local).

        // Let's look at `connectSSE` definition in Step 65.
        // It DOES NOT call startExecution.

        /*
        evtSource.onopen = () => {
            console.log("SSE Connected");
        };
        */

        // So `startExecution` was called explicitly in the click handler in Step 65/69?
        // Step 69:
        // connectSSE();
        // startExecution();

        // So there is NO dependency on onopen in the current code (Step 69 view).
        // Correct.

        // So the plan is:
        // 1. Clear Session.
        // 2. connectSSE().
        // 3. startExecution().





        function startExecution() {
            const startLine = document.createElement('div');
            startLine.className = 'console-line';
            startLine.textContent = '> Starting execution...';
            consoleContent.appendChild(startLine);

            const postApiUrl = document.getElementById('put-api-url').value;
            const useFarmerId = document.getElementById('use-farmer-id').value;

            // Asset Attribute Configs
            const attrCount = parseInt(document.getElementById('attr-count-select').value) || 1;
            let attrKeys = [];

            const scriptNameForConfig = scriptSelect.value;

            if (scriptNameForConfig === 'Update_Farmer_Address.py' || scriptNameForConfig === 'Update_Asset_Address.py') {
                const addrCount = parseInt(document.getElementById('addr-count-select').value) || 1;
                attrKeys = [];
                const k1 = document.getElementById('address-key-1').value;
                if (k1) attrKeys.push(k1);
                if (addrCount >= 2) {
                    const k2 = document.getElementById('address-key-2').value;
                    if (k2) attrKeys.push(k2);
                }
                if (addrCount >= 3) {
                    const k3 = document.getElementById('address-key-3').value;
                    if (k3) attrKeys.push(k3);
                }
                if (addrCount >= 4) {
                    const k4 = document.getElementById('address-key-4').value;
                    if (k4) attrKeys.push(k4);
                }
            } else {
                attrKeys.push(document.getElementById('attr-key-1').value);
                if (attrCount >= 2) attrKeys.push(document.getElementById('attr-key-2').value);
                if (attrCount >= 3) attrKeys.push(document.getElementById('attr-key-3').value);
                if (attrCount >= 4) attrKeys.push(document.getElementById('attr-key-4').value);
            }

            const areaUnit = document.getElementById('area-unit-select') ? document.getElementById('area-unit-select').value : "Hectare";
            const forceCropAuditedVal = document.getElementById('force-crop-audited') ? document.getElementById('force-crop-audited').value : "none";

            const config = {
                username: document.getElementById('username').value,
                password: document.getElementById('password').value,
                environment: document.getElementById('environment').value,
                tenant_code: document.getElementById('tenant-code').value,
                post_api_url: postApiUrl,
                secondary_api_url: document.getElementById('secondary-api-url').value,
                x_api_key: document.getElementById('x-api-key').value,
                use_farmer_id: useFarmerId,
                attr_keys: attrKeys,
                unit: areaUnit,
                force_crop_audited: forceCropAuditedVal,
                delay_time: document.getElementById('delay-time-input') ? document.getElementById('delay-time-input').value : 1
            };

            const formData = new FormData();
            formData.append('script_name', scriptSelect.value);
            if (currentUploadedFilename) {
                formData.append('input_filename', currentUploadedFilename);
            }
            formData.append('config', JSON.stringify(config));
            formData.append('client_id', clientId);

            // Execute (Background Task)
            fetch('/api/execute', {
                method: 'POST',
                body: formData
            })
                .then(response => {
                    if (response.ok) {
                        return response.json();
                    }
                    return response.json().then(err => { throw new Error(err.detail || 'Execution Failed'); });
                })
                .then(data => {
                    const queuedLine = document.createElement('div');
                    queuedLine.className = 'console-line';
                    queuedLine.textContent = '> ' + data.message;
                    consoleContent.appendChild(queuedLine);
                })
                .catch(error => {
                    const errLine = document.createElement('div');
                    errLine.className = 'console-line';
                    errLine.style.color = '#ff4444';
                    errLine.textContent = '> Request Failed: ' + error.message;
                    consoleContent.appendChild(errLine);

                    statusArea.innerHTML = '<div style="color: red;">Request Failed</div>';
                    runBtn.disabled = false;
                    localStorage.setItem('is_script_running', 'false');
                });
        }
    });

    // Generate Template Logic (Mock)
    generateTemplateBtn.addEventListener('click', () => {
        if (!scriptSelect.value) {
            alert('Please select a script first.');
            return;
        }
        const scriptName = scriptSelect.value;

        // Target the info box in the "Generate Template" step
        const templateInfoBox = document.getElementById('template-info-box');

        // Show loading state
        templateInfoBox.style.color = 'blue';
        templateInfoBox.innerHTML = '<strong>Generating template...</strong>';

        fetch('/api/template/' + scriptName)
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                return response.json().then(err => { throw new Error(err.detail || 'Error generating template'); });
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'Template_' + scriptName.replace('.py', '.xlsx');
                document.body.appendChild(a);
                a.click();
                a.remove();

                // Show success state
                templateInfoBox.style.color = 'green';
                templateInfoBox.textContent = "Template downloaded successfully";
            })
            .catch(error => {
                // Show error state
                templateInfoBox.style.color = 'red';
                templateInfoBox.textContent = 'Template Error: ' + error.message;
                alert('Template Error: ' + error.message);
            });
    });

    // --- Draggable Sidebar Logic ---
    const resizer = document.getElementById('sidebar-resizer');
    const authSection = document.querySelector('.auth-section');
    const sidebar = document.querySelector('.sidebar');

    if (resizer && authSection && sidebar) {
        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            e.preventDefault(); // Prevent text selection immediately
            resizer.classList.add('active');
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            // Correct calculation: height = mouse position - top of the element
            // This accounts for sidebar padding/offsets automatically
            const authRect = authSection.getBoundingClientRect();
            let newHeight = e.clientY - authRect.top;

            // Constraints (e.g. 150px min to avoid crushing, up to max)
            const sidebarHeight = sidebar.clientHeight;
            const minHeight = 150;
            const maxHeight = sidebarHeight - 150; // Keep space for config

            if (newHeight < minHeight) newHeight = minHeight;
            if (newHeight > maxHeight) newHeight = maxHeight;

            // Apply new height
            authSection.style.height = `${newHeight}px`;
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('active');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }
});
