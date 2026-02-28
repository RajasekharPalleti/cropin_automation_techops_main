/**
 * session.js — Client ID & Session Recovery
 * Manages the per-tab client ID used to route SSE logs.
 * On page load, checks the backend for an orphaned session on this machine
 * and reloads to reconnect if one is found.
 *
 * Exposes:
 *   window.getClientId()       — returns current clientId string
 *   window.setClientId(id)     — updates clientId and sessionStorage
 */

document.addEventListener('DOMContentLoaded', () => {

    // ----------------------------------------------------------------
    // Client ID — persisted in sessionStorage (survives page navigation
    // within the same tab, cleared when the tab is closed)
    // ----------------------------------------------------------------
    let clientId = sessionStorage.getItem('clientId');

    function getClientId() { return clientId; }

    function setClientId(id) {
        clientId = id;
        sessionStorage.setItem('clientId', id);
    }

    // ----------------------------------------------------------------
    // Create a brand-new session ID
    // ----------------------------------------------------------------
    function generateId() {
        return 'client_' + Math.random().toString(36).slice(2, 11);
    }

    // ----------------------------------------------------------------
    // Session recovery
    // If we have no clientId yet, create a temporary one immediately so
    // the rest of the app never sees null. Then check the backend to see
    // if this machine has an orphaned running session — if yes, reload
    // so the session restore UI picks it up cleanly.
    // ----------------------------------------------------------------
    if (!clientId) {
        // Assign a temp ID right away to prevent null-reference errors
        setClientId(generateId());

        const savedTenant = localStorage.getItem('tenant_code');
        const savedUser = localStorage.getItem('username');
        const savedMachine = localStorage.getItem('unique_machine_id');

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
                        console.log('Recovered orphaned session:', data);
                        sessionStorage.setItem('clientId', data.client_id);
                        sessionStorage.setItem('is_script_running', 'true');
                        sessionStorage.setItem('running_script_name', data.script_name || '');
                        // Reload so the session restore UI initialises cleanly
                        location.reload();
                    }
                    // If not found, the temp ID we already set is kept — no action needed
                })
                .catch(() => {
                    // Network error during recovery check — keep temp ID and continue
                });
        }
    }

    // ----------------------------------------------------------------
    // Expose to other modules
    // ----------------------------------------------------------------
    window.getClientId = getClientId;
    window.setClientId = setClientId;

});
