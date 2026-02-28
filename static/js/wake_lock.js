/**
 * wake_lock.js — Screen Wake Lock
 * Prevents the screen from sleeping while a script is running.
 * Exposes: window.requestWakeLock(), window.releaseWakeLock()
 */

document.addEventListener('DOMContentLoaded', () => {

    let wakeLock = null;

    // ---------------------------------------------------------
    // Request wake lock from the browser
    // ---------------------------------------------------------
    async function requestWakeLock() {
        if (!('wakeLock' in navigator)) return;

        try {
            if (wakeLock && !wakeLock.released) {
                console.log('Wake Lock already active');
                return;
            }
            wakeLock = await navigator.wakeLock.request('screen');
            console.log('Wake Lock active');

            // Show visual indicator in status area
            const statusArea = document.getElementById('status-area');
            if (statusArea && !document.getElementById('wake-lock-indicator')) {
                const indicator = document.createElement('div');
                indicator.id = 'wake-lock-indicator';
                indicator.style.cssText = 'font-size: 0.8em; color: green; margin-top: 5px;';
                indicator.textContent = '⚡ Screen Wake Lock Active';
                statusArea.appendChild(indicator);
            }

            wakeLock.addEventListener('release', () => {
                console.log('Wake Lock released');
                const indicator = document.getElementById('wake-lock-indicator');
                if (indicator) indicator.remove();
            });

        } catch (err) {
            console.error('Wake Lock failed:', err);
            const statusArea = document.getElementById('status-area');
            if (statusArea) {
                statusArea.innerHTML += '<div style="color: orange; font-size: 0.8em;">⚠️ Wake Lock Failed: Screen may sleep.</div>';
            }
        }
    }

    // ---------------------------------------------------------
    // Release wake lock
    // ---------------------------------------------------------
    function releaseWakeLock() {
        if (wakeLock) {
            wakeLock.release().then(() => { wakeLock = null; });
        }
        const indicator = document.getElementById('wake-lock-indicator');
        if (indicator) indicator.remove();
    }

    // ---------------------------------------------------------
    // Re-acquire lock when tab becomes visible again
    // ---------------------------------------------------------
    document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState !== 'visible') return;

        const isRunning = sessionStorage.getItem('is_script_running') === 'true';

        if (isRunning && (wakeLock === null || wakeLock.released)) {
            console.log('Visibility restored, re-acquiring Wake Lock...');
            await requestWakeLock();
        } else if (wakeLock !== null && !wakeLock.released) {
            // Keep alive if lock exists and hasn't been released
            await requestWakeLock();
        }
    });

    // ---------------------------------------------------------
    // Expose to other modules
    // ---------------------------------------------------------
    window.requestWakeLock = requestWakeLock;
    window.releaseWakeLock = releaseWakeLock;

});
