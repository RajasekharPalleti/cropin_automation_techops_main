document.addEventListener('DOMContentLoaded', () => {
    const configToggle = document.getElementById('config-toggle');
    const configContent = document.getElementById('config-content');
    const scriptSelect = document.getElementById('script-select');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const statusArea = document.getElementById('status-area');
    const generateTemplateBtn = document.getElementById('generate-template-btn');

    // =============================================
    // GENERIC CUSTOM SELECT UTILITY
    // Converts any native <select> into a green-themed custom dropdown.
    // Keeps the original <select> hidden so any existing JS that reads
    // .value from it continues to work unchanged.
    // =============================================
    function initCustomSelect(selectEl) {
        if (!selectEl || selectEl.dataset.customized) return;
        selectEl.dataset.customized = 'true';
        selectEl.style.display = 'none';

        // Build wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'custom-dropdown custom-select-wrapper';

        // Selected display
        const selected = document.createElement('div');
        selected.className = 'dropdown-selected';

        const selectedText = document.createElement('span');
        const defaultOpt = selectEl.options[selectEl.selectedIndex];
        selectedText.textContent = defaultOpt ? defaultOpt.text : '';

        const arrow = document.createElement('span');
        arrow.className = 'arrow';
        arrow.textContent = '▼';

        selected.appendChild(selectedText);
        selected.appendChild(arrow);

        // Menu
        const menu = document.createElement('div');
        menu.className = 'dropdown-menu';

        const list = document.createElement('ul');
        list.className = 'dropdown-list';

        Array.from(selectEl.options).forEach(opt => {
            const li = document.createElement('li');
            li.textContent = opt.text;
            li.dataset.value = opt.value;
            if (opt.selected) li.classList.add('selected-item');
            li.addEventListener('click', () => {
                selectedText.textContent = opt.text;
                selectEl.value = opt.value;
                // Dispatch change event so any existing listeners still fire
                selectEl.dispatchEvent(new Event('change'));
                // Highlight active item
                list.querySelectorAll('li').forEach(el => el.classList.remove('selected-item'));
                li.classList.add('selected-item');
                menu.classList.remove('show');
                selected.classList.remove('active');
            });
            list.appendChild(li);
        });

        menu.appendChild(list);
        wrapper.appendChild(selected);
        wrapper.appendChild(menu);

        // Toggle open/close
        selected.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            // Close all other custom selects first
            document.querySelectorAll('.custom-select-wrapper .dropdown-menu.show').forEach(m => {
                m.classList.remove('show');
                m.previousElementSibling.classList.remove('active');
            });
            if (!isOpen) {
                menu.classList.add('show');
                selected.classList.add('active');
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                menu.classList.remove('show');
                selected.classList.remove('active');
            }
        });

        // Insert after the hidden select
        selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
    }

    // Convert all config-area selects (excludes the script/env custom dropdowns which are already custom)
    [
        'use-farmer-id',
        'attr-count-select',
        'addr-count-select',
        'removal-count-select',
        'force-crop-audited',
        'worker-count',
        'ca-action-select'
    ].forEach(id => initCustomSelect(document.getElementById(id)));

    // Mobile Sidebar Toggle
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mainSidebar = document.querySelector('.sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            mainSidebar.classList.toggle('active');
            if (sidebarOverlay) sidebarOverlay.classList.toggle('active');
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', () => {
            mainSidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        });
    }

    // Prevent accidental refresh (Close/Toolbar Refresh)
    window.addEventListener('beforeunload', (e) => {
        if (sessionStorage.getItem('is_script_running') === 'true') {
            const msg = "Script is running! Refreshing or Closing the browser is NOT allowed. Please wait for the process to complete.";
            e.preventDefault();
            e.returnValue = msg;
            return msg;
        }
    });

    // Block Keyboard Refresh (F5, Ctrl+R)
    window.addEventListener('keydown', (e) => {
        if (sessionStorage.getItem('is_script_running') === 'true') {
            if (
                (e.key === 'F5') ||
                (e.ctrlKey && e.key === 'r') ||
                (e.metaKey && e.key === 'r')
            ) {
                e.preventDefault();
                alert("Refresh is disabled while the script is running!");
            }
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
            eyeIcon.textContent = 'visibility'; // Material icon name
        } else {
            passIn.type = 'password';
            eyeIcon.textContent = 'visibility_off'; // Material icon name
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
        // Close keyboard on mobile to prevent scroll jumps
        if (document.activeElement) {
            document.activeElement.blur();
        }

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
                if (selectedScript.name === 'Update_Asset_Additional_Attribute.py' || selectedScript.name === 'Update_Farmer_Additional_Attribute.py' || selectedScript.name === 'Update_Farmer_Details.py' || selectedScript.name === 'Update_Asset_Details.py' || selectedScript.name === 'Update_Farmer_Number_Data.py') {
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

            // Toggle time Config
            const timeConfig = document.getElementById('time-delay-config');
            if (timeConfig) {
                const scriptsWithDelay = [
                    'Update_DOS_Variety_to_CA.py', 'Update_DOS_to_CA.py', 'Update_Variety_to_CA.py',
                    'PR_Enablement_Bulk.py', 'Add_Geotag_or_Update_Lat_Long_to_CA.py',
                    'Add_Subcompany_Permissons_To_Variety.py',
                    'Bulk_Delete_Assets.py', 'Bulk_Delete_Farmers.py', 'CA_Close_and_Delete.py',
                    'Enable_Or_Disable_User.py', 'PR_Enablement.py', 'PR_and_Weather_Enablement.py',
                    'Update_Asset_Tags.py', 'Update_Farmer_Tags.py',
                    'Update_Farmer_Details.py', 'Update_Asset_Details.py',
                    'Update_Farmer_Additional_Attribute.py', 'Update_Asset_Additional_Attribute.py',
                    'Update_Asset_Address.py', 'Update_Farmer_Address.py',
                    'Delete_Asset_Tags.py', 'Delete_Farmer_Tags.py',
                    'Remove_Variety_Data.py', 'Area_Audit_To_CA.py', 'Area_Audit_Removal.py',
                    'Split_CAs.py', 'AddTagsWithNewAPI.py', 'Add_Cropstages_to_Variety.py',
                    'Add_Seed_Grades_to_Variety.py', 'Update_Farmer_Number_Data.py',
                    'Add_Users.py', 'Add_Varieties_or_Sub_Varieties.py',
                    'Edit_Plans_in_Variety_with_or_without_recurring.py',
                    'RefreshPlans.py', 'Farmer_Refresh_EditandSave.py',
                    'Asset_Refresh_EditandSave.py', 'Enable_Cropin_Connect.py',
                    'Delete_Users.py'
                ];
                if (scriptsWithDelay.includes(selectedScript.name)) {
                    timeConfig.style.display = 'block';
                } else {
                    timeConfig.style.display = 'none';
                }
            }


            // Toggle CA Close and Delete Config
            const caCloseDeleteConfig = document.getElementById('ca-close-delete-config');
            if (caCloseDeleteConfig) {
                if (selectedScript.name === 'CA_Close_and_Delete.py') {
                    caCloseDeleteConfig.style.display = 'block';
                } else {
                    caCloseDeleteConfig.style.display = 'none';
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


            // Toggle Variety Removal Config
            const removalConfig = document.getElementById('variety-removal-config');
            if (removalConfig) {
                if (selectedScript.name === 'Remove_Variety_Data.py') {
                    removalConfig.style.display = 'block';
                } else {
                    removalConfig.style.display = 'none';
                }
            }

            // Logic for Variety Removal Count Dropdown
            const removalCountSelect = document.getElementById('removal-count-select');
            if (removalCountSelect) {
                removalCountSelect.addEventListener('change', function () {
                    const count = parseInt(this.value);
                    document.getElementById('group-remove-1').style.display = 'block';
                    document.getElementById('group-remove-2').style.display = count >= 2 ? 'block' : 'none';
                    document.getElementById('group-remove-3').style.display = count >= 3 ? 'block' : 'none';
                    document.getElementById('group-remove-4').style.display = count >= 4 ? 'block' : 'none';
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

    // --- Screen Wake Lock ---
    let wakeLock = null;

    async function requestWakeLock() {
        if ('wakeLock' in navigator) {
            try {
                if (wakeLock && !wakeLock.released) {
                    console.log('Wake Lock already active');
                    return;
                }
                wakeLock = await navigator.wakeLock.request('screen');
                console.log('Wake Lock active');

                if (statusArea) {
                    // visual indicator check
                    const lockIndicator = document.getElementById('wake-lock-indicator');
                    if (!lockIndicator) {
                        const newIndicator = document.createElement('div');
                        newIndicator.id = 'wake-lock-indicator';
                        newIndicator.style.cssText = "font-size: 0.8em; color: green; margin-top: 5px;";
                        newIndicator.textContent = '⚡ Screen Wake Lock Active';
                        statusArea.appendChild(newIndicator);
                    }
                }

                wakeLock.addEventListener('release', () => {
                    console.log('Wake Lock released');
                    const indicator = document.getElementById('wake-lock-indicator');
                    if (indicator) indicator.remove();
                });

            } catch (err) {
                console.error('Wake Lock failed:', err);
                if (statusArea) {
                    statusArea.innerHTML += '<div style="color: orange; font-size: 0.8em;">⚠️ Wake Lock Failed: Screen may sleep.</div>';
                }
            }
        }
    }

    function releaseWakeLock() {
        if (wakeLock) {
            wakeLock.release()
                .then(() => {
                    wakeLock = null;
                });
        }
        const indicator = document.getElementById('wake-lock-indicator');
        if (indicator) indicator.remove();
    }

    // Re-acquire lock when page comes back to visibility
    document.addEventListener('visibilitychange', async () => {
        if (wakeLock !== null && document.visibilityState === 'visible') {
            await requestWakeLock();
        } else if (sessionStorage.getItem('is_script_running') === 'true' && document.visibilityState === 'visible') {
            // Failsafe: If script is running but lock is null (maybe lost during background), try to get it back
            console.log('Visibility restored, re-acquiring Wake Lock...');
            await requestWakeLock();
        }
    });

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
            // Stop Wake Lock
            releaseWakeLock();

            // Fire and forget stop request
            fetch('/api/stop/' + clientId, { method: 'POST' }).catch(err => console.error("Stop request failed:", err));

            // IMMEDIATELY Kill Connection and Stop Processing
            if (evtSource) {
                evtSource.close();
                evtSource = null;
            }

            // Push Stop Command to Buffer (processed AFTER pending logs)
            logBuffer.push('STOP_UI_NOW');

            // Trigger flush if not already running
            if (!isRenderPending && window.flushLogsInstance) {
                isRenderPending = true;
                requestAnimationFrame(window.flushLogsInstance);
            } else if (!window.flushLogsInstance) {
                // Fallback if SSE never connected
                const stopLine = document.createElement('div');
                stopLine.className = 'console-line';
                stopLine.style.color = 'orange';
                stopLine.textContent = '> JOB STOPPED SUCCESSFULLY. READY FOR NEW RUN.';
                consoleContent.appendChild(stopLine);
                statusArea.innerHTML = '<div style="color: Orange;">Job Stopped Successfully</div>';
                runBtn.disabled = false;
                runBtn.innerHTML = '▶ Run Script';
                stopBtn.style.display = 'none';
                sessionStorage.setItem('is_script_running', 'false');
                clientId = 'client_' + Math.random().toString(36).slice(2, 11);
                sessionStorage.setItem('clientId', clientId);
            }
        }
    });

    const consoleContent = document.getElementById('console-content');

    // Generate persistent client ID (Session based functionality)
    let clientId = sessionStorage.getItem('clientId');

    // RECOVERY LOGIC: If no session active, check backend for orphaned session for this machine
    if (!clientId) {
        // Attempt recovery
        const savedTenant = localStorage.getItem('tenant_code');
        const savedUser = localStorage.getItem('username');
        const savedMachine = localStorage.getItem('unique_machine_id');

        if (savedTenant && savedUser && savedMachine) {
            // Synchronous-like fetch is not possible, so we use async approach.
            // But clientId is needed immediately for some parts?
            // Actually, we can fetch, and IF found, reload/update state. 
            // Since this is init, we can fire the check.

            fetch('/api/recover_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    machine_id: savedMachine,
                    username: savedUser,
                    tenant_code: savedTenant
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.found && data.client_id) {
                        console.log("Recovered orphaned session:", data);
                        sessionStorage.setItem('clientId', data.client_id);
                        sessionStorage.setItem('is_script_running', 'true');
                        sessionStorage.setItem('running_script_name', data.script_name);

                        // Reload to pick up state cleanly (simplest way to re-init everything)
                        location.reload();
                    } else {
                        // No session found, proceed as new
                        initNewSession();
                    }
                })
                .catch(e => {
                    console.error("Recovery check failed:", e);
                    initNewSession();
                });
        } else {
            initNewSession();
        }
    } else {
        // Session exists, proceed
    }

    function initNewSession() {
        if (!sessionStorage.getItem('clientId')) {
            const newId = 'client_' + Math.random().toString(36).slice(2, 11);
            sessionStorage.setItem('clientId', newId);
            // Ensure global clientId var is updated if it was read before? 
            // We need to make sure the rest of code uses the right ID. 
            // Since clientId var is let, we can update it.
            clientId = newId;
        }
    }

    // NOTE: Because fetch is async, clientId might be null for a few milliseconds.
    // However, the rest of the code (SSE connection etc) relies on `clientId`.
    // If we are recovering, we RELOAD page, so it's fine.
    // If we are NOT recovering (initNewSession), we set it immediately.
    // We need to make sure initNewSession is called immediately if credentials missing.

    // Refined Logic to handle async delay for variable accessibility:

    if (!clientId) {
        const savedTenant = localStorage.getItem('tenant_code');
        const savedUser = localStorage.getItem('username');
        const savedMachine = localStorage.getItem('unique_machine_id');

        // Temporary ID to avoid crashes while checking
        clientId = 'client_' + Math.random().toString(36).slice(2, 11);

        // Check backend for orphaned session for this machine
        // RATIONALE: This check runs on page load to see if a previous session is still active on the server.
        // It helps purely for recovery purposes (e.g. tab closed accidentally).
        if (savedTenant && savedUser && savedMachine) {
            fetch('/api/recover_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    machine_id: savedMachine,
                    username: savedUser,
                    tenant_code: savedTenant
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.found && data.client_id) {
                        console.log("Recovered orphaned session:", data);
                        sessionStorage.setItem('clientId', data.client_id);
                        sessionStorage.setItem('is_script_running', 'true');
                        sessionStorage.setItem('running_script_name', data.script_name);
                        location.reload();
                    } else {
                        // Persist the temporary ID we created
                        sessionStorage.setItem('clientId', clientId);
                    }
                })
                .catch(() => {
                    sessionStorage.setItem('clientId', clientId);
                });
        } else {
            sessionStorage.setItem('clientId', clientId);
        }
    }

    // SSE Manager
    let evtSource = null;
    let logBuffer = [];
    let isRenderPending = false;

    function connectSSE(onOpen = null) {
        if (evtSource && evtSource.readyState !== EventSource.CLOSED) return;

        console.log("Connecting SSE for logs...");
        evtSource = new EventSource('/api/logs/' + clientId);

        evtSource.onopen = () => {
            console.log("SSE Connected");
            if (onOpen) {
                onOpen();
                onOpen = null; // Prevent re-execution on reconnect
            }
        };

        // Reset buffer on new connection
        logBuffer = [];
        isRenderPending = false;

        // Expose flushLogs to be callable from outside (for Stop button)
        window.flushLogsInstance = flushLogs;

        function flushLogs() {
            if (logBuffer.length === 0) {
                isRenderPending = false;
                return;
            }

            const fragment = document.createDocumentFragment();
            // Process up to 100 messages at a time to stay responsive
            const batch = logBuffer.splice(0, 100);

            batch.forEach(msgData => {



                if (msgData.startsWith('JOB_COMPLETED::')) {
                    const filename = msgData.split('::')[1];
                    const finishLine = document.createElement('div');
                    finishLine.className = 'console-line';
                    finishLine.style.color = '#00ff00';
                    finishLine.textContent = '> Execution Finished. Downloading ' + filename + '...';
                    fragment.appendChild(finishLine);

                    sessionStorage.setItem('is_script_running', 'false');

                    // Stop Wake Lock
                    releaseWakeLock();

                    // Trigger Download logic (defer to next tick to avoid blocking fragment append)
                    setTimeout(() => {
                        window.location.href = '/api/download/' + encodeURIComponent(filename);
                        statusArea.innerHTML = '<div style="color: green;">Success! Check downloads.</div>';
                        runBtn.disabled = false;
                        runBtn.innerHTML = '▶ Run Script';
                        stopBtn.style.display = 'none';
                        if (evtSource) { evtSource.close(); evtSource = null; }

                        const closeLine = document.createElement('div');
                        closeLine.className = 'console-line';
                        closeLine.style.color = 'green';
                        closeLine.textContent = '> Connection closed. Job Done.';
                        consoleContent.appendChild(closeLine);
                        consoleBox.scrollTop = consoleBox.scrollHeight;
                    }, 0);
                    return;
                }

                if (msgData.startsWith('JOB_FAILED::')) {
                    const errorMsg = msgData.split('::')[1];
                    const errLine = document.createElement('div');
                    errLine.className = 'console-line';
                    errLine.style.color = '#ff4444';
                    errLine.textContent = '> ERROR: ' + errorMsg;
                    fragment.appendChild(errLine);

                    // Stop Wake Lock
                    releaseWakeLock();

                    setTimeout(() => {
                        statusArea.innerHTML = '<div style="color: red;">Execution Failed</div>';
                        runBtn.disabled = false;
                        runBtn.innerHTML = '▶ Run Script';
                        stopBtn.style.display = 'none';
                        sessionStorage.setItem('is_script_running', 'false');
                    }, 0);
                    return;
                }

                if (msgData === 'STOP_UI_NOW') {
                    const stopLine = document.createElement('div');
                    stopLine.className = 'console-line';
                    stopLine.style.color = 'orange';
                    stopLine.textContent = '> JOB STOPPED SUCCESSFULLY. READY FOR NEW RUN.';
                    fragment.appendChild(stopLine);

                    // Force UI Reset inside the loop to ensure sync with logs
                    setTimeout(() => {
                        statusArea.innerHTML = '<div style="color: Orange;">Job Stopped Successfully</div>';
                        runBtn.disabled = false;
                        runBtn.innerHTML = '▶ Run Script';
                        stopBtn.style.display = 'none';
                        sessionStorage.setItem('is_script_running', 'false');

                        // Regenerate Client ID
                        clientId = 'client_' + Math.random().toString(36).slice(2, 11);
                        sessionStorage.setItem('clientId', clientId);
                        console.log("New Client ID generated:", clientId);
                    }, 0);
                    return;
                }

                // Normal Log
                const logLine = document.createElement('div');
                logLine.className = 'console-line';
                logLine.textContent = '> ' + msgData;
                fragment.appendChild(logLine);
            });

            // Smart Auto-Scroll: Check BEFORE appending
            const isNearBottom = consoleBox.scrollHeight - consoleBox.scrollTop - consoleBox.clientHeight < 150;

            consoleContent.appendChild(fragment);

            if (isNearBottom) {
                consoleBox.scrollTop = consoleBox.scrollHeight;
            }

            if (logBuffer.length > 0) {
                requestAnimationFrame(flushLogs);
            } else {
                isRenderPending = false;
            }
        }

        evtSource.onmessage = (event) => {
            logBuffer.push(event.data);
            if (!isRenderPending) {
                isRenderPending = true;
                requestAnimationFrame(flushLogs);
            }
        };

        evtSource.onerror = (err) => {
            console.error("SSE Error (Connection Lost?):", err);
            if (evtSource) {
                evtSource.close();
                evtSource = null;
            }

            // AUTO-RECONNECT LOGIC
            if (sessionStorage.getItem('is_script_running') === 'true') {
                // Only reconnect if we really think a script is running
                const consoleContent = document.getElementById('console-content');
                const errLine = document.createElement('div');
                errLine.className = 'console-line';
                errLine.style.color = 'orange';
                errLine.textContent = '> Connection lost. Attempting to reconnect in 5s...';
                if (consoleContent) consoleContent.appendChild(errLine);

                // Retry connection
                setTimeout(() => {
                    console.log("Attempting auto-reconnect...");
                    connectSSE();
                }, 5000);
            }
        };
    }

    // Check if we need to restore session
    if (sessionStorage.getItem('is_script_running') === 'true') {
        const consoleBox = document.getElementById('console-box');
        const runBtn = document.getElementById('run-script-btn');
        const stopBtn = document.getElementById('stop-script-btn');


        // --- OPTIMISTIC RESTORE ---
        // Immediately show "Running" state based on Session Storage
        // This ensures button is visible even if network is flaky on wake

        const savedScriptName = sessionStorage.getItem('running_script_name');
        if (savedScriptName) {
            selectScript(savedScriptName);
        }

        // Show Console & Disable Run
        if (consoleBox) consoleBox.style.display = 'block';
        if (runBtn) {
            runBtn.disabled = true;
            runBtn.innerHTML = '<span class="spinner"></span> Restoring session...';
        }

        // Force runContainer visible
        const runContainer = document.getElementById('run-container');
        if (runContainer) runContainer.style.display = 'flex';

        // SHOW STOP BUTTON
        if (stopBtn) {
            stopBtn.style.display = 'inline-block';
            stopBtn.disabled = false;
        }

        const resumeLine = document.createElement('div');
        resumeLine.className = 'console-line';
        resumeLine.style.color = '#FFA500'; // Orange
        resumeLine.textContent = '> Restoring session connection...';
        consoleContent.appendChild(resumeLine);

        // Resume Wake Lock
        requestWakeLock();

        // Add Reset Button
        addResetButton();


        // --- VERIFY WITH SERVER ---
        fetch('/api/status/' + clientId)
            .then(r => r.json())
            .then(status => {
                if (status.is_running) {
                    // SERVER CONFIRMED
                    if (runBtn) runBtn.innerHTML = '<span class="spinner"></span> Processing...';

                    const confirmedLine = document.createElement('div');
                    confirmedLine.className = 'console-line';
                    confirmedLine.style.color = '#00AA00'; // Green
                    confirmedLine.textContent = '> Session confirmed. Resuming logs...';
                    consoleContent.appendChild(confirmedLine);

                    connectSSE();

                } else {
                    // SERVER DENIED: Ghost Session (Server likely restarted)
                    console.warn("Server reported no active task. Clearing ghost session.");
                    sessionStorage.setItem('is_script_running', 'false');
                    sessionStorage.removeItem('running_script_name');
                    releaseWakeLock();

                    // Optional: Notify user
                    if (statusArea) statusArea.innerHTML = '<div style="color: orange;">Previous session was not found on server. Ready for new run.</div>';

                    // Reset UI
                    if (consoleBox) consoleBox.style.display = 'none';
                    if (runBtn) {
                        runBtn.disabled = false;
                        runBtn.innerHTML = '▶ Run Script';
                    }
                    if (stopBtn) stopBtn.style.display = 'none';

                    // Remove reset button?
                    const resetBtn = document.getElementById('reset-session-btn');
                    if (resetBtn) resetBtn.remove();
                }
            })
            .catch(err => {
                console.error("Status Check Failed (Network Error?):", err);
                // IF NETWORK FAILS (e.g. laptop waking up), KEEP STOP BUTTON VISIBLE!
                // Do not hide it. User can try to "Stop" which naturally handles network errors or they can use "Force Reset".

                const errLine = document.createElement('div');
                errLine.className = 'console-line';
                errLine.style.color = 'red';
                errLine.textContent = '> Warning: Could not reach server to verify status. Check network connection.';
                consoleContent.appendChild(errLine);

                // Allow "Force Reset" to be used
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
                sessionStorage.setItem('is_script_running', 'false');
                sessionStorage.removeItem('running_script_name');
                releaseWakeLock(); // Release lock on force reset
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

        // Show Confirmation Modal Logic
        const confirmModal = document.getElementById('confirmation-modal');
        const confirmTenant = document.getElementById('confirm-tenant');
        const confirmUser = document.getElementById('confirm-user');
        const confirmScriptName = document.getElementById('confirm-script-name');

        // Populate fields
        confirmTenant.textContent = tenantIn.value || "Not Set";
        confirmUser.textContent = userIn.value || "Not Set";
        confirmScriptName.textContent = scriptSelect.value || "Unknown Script";

        confirmModal.style.display = 'block';
    });

    // Confirmation Modal Logic
    const confirmModal = document.getElementById('confirmation-modal');
    const closeConfirmModal = document.getElementById('close-confirm-modal');
    const cancelRunBtn = document.getElementById('cancel-run-btn');
    const confirmRunBtn = document.getElementById('confirm-run-btn');

    const closeConfirmation = () => {
        confirmModal.style.display = 'none';
        // Re-enable run button if it was disabled during check
        if (confirmRunBtn) {
            confirmRunBtn.disabled = false;
            confirmRunBtn.innerHTML = 'Yes, Run Script';
        }
    };

    if (closeConfirmModal) closeConfirmModal.addEventListener('click', closeConfirmation);
    if (cancelRunBtn) cancelRunBtn.addEventListener('click', closeConfirmation);

    // Close on click outside
    window.addEventListener('click', (event) => {
        // Only backup modal closes on outside click (if we want to keep that behavior for backup)
        // Or strictly prevent confirmation modal from closing
        if (event.target == confirmModal) {
            // Do nothing - prevent closing
            return;
        }
        // Backup modal listener logic is handled elsewhere or check if backup modal needs similar treatment
        const backupModal = document.getElementById('backup-modal');
        if (event.target == backupModal) {
            backupModal.style.display = "none";
        }
    });

    if (confirmRunBtn) {
        confirmRunBtn.addEventListener('click', () => {
            // LAST CHECK: Is this machine already running something according to server?
            // (In case Auto-Recovery failed or User ignored it)
            const machineId = localStorage.getItem('unique_machine_id');
            const tenant = document.getElementById('tenant-code').value; // Use current input
            const user = document.getElementById('username').value; // Use current input

            confirmRunBtn.disabled = true;
            confirmRunBtn.innerHTML = '<span class="spinner"></span> Checking...';

            fetch(`/api/recover_session?machine_id=${machineId}&username=${user}&tenant_code=${tenant}`)
                .then(r => r.json())
                .then(data => {
                    if (data.found) {
                        // IT IS RUNNING!
                        alert("SESSION ACTIVE: A script is already running on this machine (possibly in another tab).\n\nYou cannot start a new session until the current one finishes or is Force Reset.");

                        // Optional: Auto-recover?
                        if (confirm("Do you want to join the running session?")) {
                            sessionStorage.setItem('clientId', data.client_id);
                            sessionStorage.setItem('is_script_running', 'true');
                            sessionStorage.setItem('running_script_name', data.script_name);
                            location.reload();
                        } else {
                            closeConfirmation();
                        }
                    } else {
                        // Not running, proceed
                        closeConfirmation();
                        executeScriptLogic();
                    }
                })
                .catch(() => {
                    // Fallback if check fails (network error?), just try running
                    closeConfirmation();
                    executeScriptLogic();
                });
        });
    }

    function executeScriptLogic() {

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
        sessionStorage.setItem('is_script_running', 'true');
        sessionStorage.setItem('running_script_name', scriptSelect.value);

        // Persist Credentials for Auto-Recovery (Machine scope)
        localStorage.setItem('tenant_code', document.getElementById('tenant-code').value);
        localStorage.setItem('username', document.getElementById('username').value);

        // Start Wake Lock
        requestWakeLock();

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
                ca_action: document.getElementById('ca-action-select') ? document.getElementById('ca-action-select').value : 'none', // Added ca_action
                use_farmer_id: useFarmerId,
                attr_keys: attrKeys,
                unit: areaUnit,
                force_crop_audited: forceCropAuditedVal,
                unit: areaUnit,
                force_crop_audited: forceCropAuditedVal,
                delay_time: document.getElementById('delay-time-input') ? document.getElementById('delay-time-input').value : 1,
                worker_count: document.getElementById('worker-count') ? parseInt(document.getElementById('worker-count').value) : 1,
                fields_to_remove: attrKeys // Re-using attrKeys variable which we populated above, or we could add a new key to config object
            };

            const formData = new FormData();
            formData.append('script_name', scriptSelect.value);
            if (currentUploadedFilename) {
                formData.append('input_filename', currentUploadedFilename);
            }
            formData.append('config', JSON.stringify(config));
            formData.append('client_id', clientId);

            // --- MACHINE ID for Locking (One script per machine) ---
            let machineId = localStorage.getItem('unique_machine_id');
            if (!machineId) {
                machineId = 'machine_' + Math.random().toString(36).slice(2, 11) + '_' + Date.now();
                localStorage.setItem('unique_machine_id', machineId);
            }
            formData.append('machine_id', machineId);

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
                    sessionStorage.setItem('is_script_running', 'false');
                });
        }
    }

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

    // --- Backup Logic ---
    const backupBtn = document.getElementById('backup-btn');
    const backupModal = document.getElementById('backup-modal');
    const closeModal = document.getElementById('close-modal');
    const uploadedList = document.getElementById('uploaded-list');
    const downloadedList = document.getElementById('downloaded-list');

    let nextPageToken = null;
    let isLoadingBackups = false;

    // Make openTab global for onclick
    window.openTab = function (evt, tabName) {
        // Declare all variables
        var i, tabcontent, tablinks;

        // Get all elements with class="tab-content" and hide them
        tabcontent = document.getElementsByClassName("tab-content");
        for (i = 0; i < tabcontent.length; i++) {
            tabcontent[i].style.display = "none";
            tabcontent[i].classList.remove("active");
        }

        // Get all elements with class="tab-link" and remove the class "active"
        tablinks = document.getElementsByClassName("tab-link");
        for (i = 0; i < tablinks.length; i++) {
            tablinks[i].className = tablinks[i].className.replace(" active", "");
        }

        // Show the current tab, and add an "active" class to the button that opened the tab
        document.getElementById(tabName).style.display = "block";
        document.getElementById(tabName).classList.add("active");
        if (evt) evt.currentTarget.className += " active";
    }

    if (backupBtn) {
        backupBtn.addEventListener('click', () => {
            backupModal.style.display = "block";
            fetchBackups(true); // Initial load (reset)
        });
    }

    if (closeModal) {
        closeModal.addEventListener('click', () => {
            backupModal.style.display = "none";
        });
    }

    // Scroll listeners for infinite scroll
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(tab => {
        tab.addEventListener('scroll', () => {
            // Check if near bottom (within 50px)
            if (tab.scrollTop + tab.clientHeight >= tab.scrollHeight - 50) {
                if (nextPageToken && !isLoadingBackups) {
                    fetchBackups(false); // Load more
                }
            }
        });
    });

    // window.addEventListener('click', (event) => {
    //     if (event.target == backupModal) {
    //         backupModal.style.display = "none";
    //     }
    // });

    function fetchBackups(reset = false) {
        if (isLoadingBackups) return;
        isLoadingBackups = true;

        if (reset) {
            nextPageToken = null;
            uploadedList.innerHTML = '';
            downloadedList.innerHTML = '';
            // Don't show loading here if you want to keep existing items while loading?
            // But for reset, we clear.
            const loadingLi = document.createElement('li');
            loadingLi.className = 'loading-indicator';
            loadingLi.textContent = 'Loading...';
            uploadedList.appendChild(loadingLi.cloneNode(true));
            downloadedList.appendChild(loadingLi);
        } else {
            // Append loading indicator at bottom if not exists
            if (!document.querySelector('.loading-indicator')) {
                // Might need one per list
                // Simplification: logic updates both lists, so indicators might be tricky if one list ends and other doesn't.
                // But API returns next page for the whole drive folder.
            }
        }

        let url = '/api/backups?page_size=100'; // Default page size
        if (nextPageToken && !reset) {
            url += '&page_token=' + encodeURIComponent(nextPageToken);
        }

        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Remove loading indicators
                document.querySelectorAll('.loading-indicator').forEach(el => el.remove());

                nextPageToken = data.nextPageToken; // Update global token

                renderFileList(data.uploaded, uploadedList);
                renderFileList(data.downloaded, downloadedList);
            })
            .catch(err => {
                console.error("Failed to fetch backups:", err);
                // Remove loading indicators
                document.querySelectorAll('.loading-indicator').forEach(el => el.remove());

                if (reset) {
                    uploadedList.innerHTML = '<li class="empty-state">Failed to load backups. Error: ' + err.message + '</li>';
                    downloadedList.innerHTML = '<li class="empty-state">Failed to load backups.</li>';
                }
            })
            .finally(() => {
                isLoadingBackups = false;
            });
    }

    function renderFileList(files, listElement) {
        if ((!files || files.length === 0) && listElement.children.length === 0) {
            listElement.innerHTML = '<li class="empty-state">No files found.</li>';
            return;
        }

        if (!files) return;

        files.forEach(file => {
            const li = document.createElement('li');
            li.className = 'file-item';

            // Format Date
            const date = new Date(file.createdTime).toLocaleString();

            // Build Link
            const link = file.webContentLink || file.webViewLink || '#';

            li.innerHTML = `
                <div class="file-info">
                    <span class="file-name">${file.name}</span>
                    <span class="file-meta">${date} • ${(file.size / 1024).toFixed(1)} KB</span>
                </div>
                <a href="${link}" target="_blank" class="download-btn">
                    <span class="material-icons" style="font-size: 16px;">download</span> Download
                </a>
            `;
            listElement.appendChild(li);
        });
    }

    // Re-acquire lock if tab becomes visible again and script is running
    document.addEventListener('visibilitychange', async () => {
        if (wakeLock !== null && document.visibilityState === 'visible' && sessionStorage.getItem('is_script_running') === 'true') {
            // Check if released
            if (wakeLock.released) {
                await requestWakeLock();
            }
        }
    });

});
