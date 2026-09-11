/**
 * weekly_report.js
 * Handles UI interactions for the standalone Weekly Report modal.
 */

document.addEventListener('DOMContentLoaded', () => {
    const navBtn = document.getElementById('weekly-report-nav-btn');
    const modal = document.getElementById('weekly-report-modal');
    const closeBtn = document.getElementById('weekly-report-close');
    const fetchBtn = document.getElementById('weekly-report-fetch-btn');
    const sendBtn = document.getElementById('weekly-report-send-btn');
    const consoleArea = document.getElementById('weekly-report-console');
    const statusDiv = document.getElementById('weekly-report-status');

    function log(message, type = 'info') {
        const line = document.createElement('div');
        line.textContent = `> ${message}`;
        if (type === 'error') line.style.color = '#ff4444';
        else if (type === 'success') line.style.color = '#00C851';
        consoleArea.appendChild(line);
        consoleArea.scrollTop = consoleArea.scrollHeight;
    }


    // --- Config UI Logic ---
    const configToggle = document.getElementById('weekly-report-config-toggle');
    const configBody = document.getElementById('weekly-report-config-body');
    const configIcon = document.getElementById('weekly-report-config-icon');
    const configText = document.getElementById('weekly-report-config-text');
    const configSaveBtn = document.getElementById('weekly-report-save-config-btn');
    const configStatus = document.getElementById('weekly-report-config-status');

    async function loadConfig() {
        try {
            const res = await fetch('/api/weekly-report/config');
            const data = await res.json();
            if (data.error) {
                configText.value = "{\n  // Error loading config or example: " + data.error + "\n}";
            } else {
                configText.value = JSON.stringify(data, null, 2);
            }
        } catch (e) {
            configText.value = "{\n  // Failed to fetch config: " + e.message + "\n}";
        }
    }

    if (configToggle) {
        configToggle.addEventListener('click', () => {
            if (configBody.style.display === 'none') {
                configBody.style.display = 'block';
                configIcon.textContent = '▲';
                loadConfig(); // Load config when opening
            } else {
                configBody.style.display = 'none';
                configIcon.textContent = '▼';
            }
        });
    }

    if (configSaveBtn) {
        configSaveBtn.addEventListener('click', async () => {
            configStatus.style.display = 'block';
            configStatus.textContent = 'Saving...';
            configStatus.style.color = '#334155';
            configSaveBtn.disabled = true;

            try {
                let parsedJson;
                try {
                    parsedJson = JSON.parse(configText.value);
                } catch (e) {
                    throw new Error("Invalid JSON format.");
                }

                const res = await fetch('/api/weekly-report/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(parsedJson)
                });
                
                const data = await res.json();
                if (data.status === 'success') {
                    configStatus.textContent = 'Configuration saved successfully!';
                    configStatus.style.color = '#00C851';
                    setTimeout(() => { configStatus.style.display = 'none'; }, 3000);
                } else {
                    throw new Error(data.error || 'Failed to save configuration');
                }
            } catch (err) {
                configStatus.textContent = err.message;
                configStatus.style.color = '#ff4444';
            } finally {
                configSaveBtn.disabled = false;
            }
        });
    }
    // -----------------------

    if (navBtn) {
        navBtn.addEventListener('click', () => {
            if (modal) modal.style.display = 'block';
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            if (modal) modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    async function executeReport(action) {
        const btn = action === 'fetch' ? fetchBtn : sendBtn;
        const originalHtml = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons" style="font-size:1.1rem;">hourglass_empty</span> Running...';
        
        if (action === 'fetch') {
            consoleArea.innerHTML = ''; // clear logs only on new fetch
            sendBtn.style.display = 'none';
        }
        
        statusDiv.style.display = 'none';
        statusDiv.className = 'alert-info';
        
        log(action === 'fetch' ? 'Fetching data from Jira...' : 'Sending Weekly Report Email...');

        try {
            const response = await fetch(`/api/weekly-report/run?action=${action}`, {
                method: 'POST'
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let result = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                result += chunk;
                
                const lines = chunk.split('\n');
                lines.forEach(l => {
                    if (l.trim()) log(l.trim());
                });
            }
            
            if (response.ok) {
                log(action === 'fetch' ? 'Fetch completed.' : 'Execution completed successfully!', 'success');
                statusDiv.textContent = action === 'fetch' ? 'Data fetched successfully. Review logs above.' : 'Report generated and emailed successfully.';
                statusDiv.style.color = '#00C851';
                statusDiv.style.display = 'block';
                
                if (action === 'fetch') {
                    sendBtn.style.display = 'block';
                }
            } else {
                throw new Error(result || response.statusText);
            }

        } catch (err) {
            console.error(err);
            log(`Error: ${err.message}`, 'error');
            statusDiv.textContent = 'Failed to execute. Check logs.';
            statusDiv.style.color = '#ff4444';
            statusDiv.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }

    if (fetchBtn) {
        fetchBtn.addEventListener('click', () => executeReport('fetch'));
    }
    
    if (sendBtn) {
        sendBtn.addEventListener('click', () => executeReport('send'));
    }
});
