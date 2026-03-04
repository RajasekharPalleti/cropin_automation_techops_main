/**
 * ui.js — Pure DOM utilities
 * Converts native <select> elements into custom dropdowns,
 * manages the mobile sidebar toggle, and handles sidebar resize.
 * No API calls. No cross-module dependencies.
 */

document.addEventListener('DOMContentLoaded', () => {

    // =========================================================
    // GENERIC CUSTOM SELECT
    // Converts a native <select> into a styled custom dropdown.
    // The original <select> is hidden so existing JS still works.
    // =========================================================
    function initCustomSelect(selectEl) {
        if (!selectEl || selectEl.dataset.customized) return;
        selectEl.dataset.customized = 'true';
        selectEl.style.display = 'none';

        const wrapper = document.createElement('div');
        wrapper.className = 'custom-dropdown custom-select-wrapper';

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
                selectEl.dispatchEvent(new Event('change'));
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

        selected.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            document.querySelectorAll('.custom-select-wrapper .dropdown-menu.show').forEach(m => {
                m.classList.remove('show');
                m.previousElementSibling.classList.remove('active');
            });
            if (!isOpen) {
                menu.classList.add('show');
                selected.classList.add('active');
            }
        });

        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                menu.classList.remove('show');
                selected.classList.remove('active');
            }
        });

        selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
    }

    // Expose so app.js can call it after dynamic options are added if needed
    window.initCustomSelect = initCustomSelect;

    // Initialize all config-area selects on load
    [
        'use-farmer-id',
        'attr-count-select',
        'addr-count-select',
        'removal-count-select',
        'force-crop-audited',
        'worker-count',
        'ca-action-select'
    ].forEach(id => initCustomSelect(document.getElementById(id)));


    // =========================================================
    // MOBILE SIDEBAR TOGGLE
    // =========================================================
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


    // =========================================================
    // DRAGGABLE SIDEBAR RESIZER
    // =========================================================
    const resizer = document.getElementById('sidebar-resizer');
    const authSection = document.querySelector('.auth-section');
    const sidebar = document.querySelector('.sidebar');

    if (resizer && authSection && sidebar) {
        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            e.preventDefault();
            resizer.classList.add('active');
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const authRect = authSection.getBoundingClientRect();
            let newHeight = e.clientY - authRect.top;
            const minHeight = 150;
            const maxHeight = sidebar.clientHeight - 150;
            newHeight = Math.max(minHeight, Math.min(maxHeight, newHeight));
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

// =========================================================
// TOAST NOTIFICATIONS
// Replaces standard blocking alert() with modern sliding toasts
// =========================================================
window.showToast = function (message, type = 'info', title = null) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    const defaultTitle = title || (type.charAt(0).toUpperCase() + type.slice(1));

    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-content">
            <div class="toast-title">${defaultTitle}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    // Trigger reflow to ensure the transition fires
    toast.offsetHeight;
    toast.classList.add('show');

    // Auto remove after 10 seconds
    const hideTimeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 400); // match css transition time
    }, 10000);

    // Dismiss early on click
    toast.onclick = () => {
        clearTimeout(hideTimeout);
        toast.classList.remove('show');
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 400);
    };
};

// =========================================================
// Custom Async Confirm Modal
// Replaces standard blocking confirm() with a modern async modal
// Returns a Promise that resolves to true (proceed) or false (cancel)
// =========================================================
window.showConfirm = function (title, message) {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.display = 'block';
        modal.style.zIndex = '3000'; // Make sure it sits above other modals

        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px; text-align: center; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div class="modal-header" style="border-bottom: none; justify-content: center; padding-top: 25px;">
                    <h2 style="font-size: 1.4em; color: #333; margin: 0;">${title}</h2>
                </div>
                <div class="modal-body" style="padding: 10px 25px 25px 25px;">
                    <p style="margin-bottom: 25px; font-size: 1.05em; color: #555; line-height: 1.4;">${message}</p>
                    <div style="display: flex; justify-content: center; gap: 12px;">
                        <button class="btn-secondary" id="dynamic-confirm-cancel" style="flex: 1; padding: 10px 0;">Cancel</button>
                        <button class="btn-primary" id="dynamic-confirm-ok" style="flex: 1; padding: 10px 0;">Yes, Proceed</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const cleanup = (result) => {
            modal.style.opacity = '0';
            setTimeout(() => {
                modal.remove();
                resolve(result);
            }, 200);
        };

        modal.querySelector('#dynamic-confirm-cancel').onclick = () => cleanup(false);
        modal.querySelector('#dynamic-confirm-ok').onclick = () => cleanup(true);
    });
};

// =========================================================
window.saveFormState = function () {
    const state = {
        tenant: document.getElementById('tenant-code')?.value || '',
        username: document.getElementById('username')?.value || '',
        env: document.getElementById('environment')?.value || 'prod1',
        apiUrl: document.getElementById('base-api-url')?.value || '',
        dataset: document.getElementById('dataset')?.value || '',
        loadType: document.getElementById('load-type')?.value || '',
        delayTime: document.getElementById('delay-time-input')?.value || '1',
        caBatchSize: document.getElementById('ca-batch-size')?.value || '50',
        caXApiKey: document.getElementById('ca-x-api-key')?.value || 'SEF5qQ6RTDGFWUc36SNuCKGYW1tVuGgGrX1iApUs5DGOc7MS',
    };
    localStorage.setItem('cropin_automation_state', JSON.stringify(state));
};

window.loadFormState = function () {
    const saved = localStorage.getItem('cropin_automation_state');
    if (!saved) return;

    try {
        const state = JSON.parse(saved);
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el && val) el.value = val;
        };

        setVal('tenant-code', state.tenant);
        setVal('username', state.username);
        setVal('environment', state.env);
        setVal('base-api-url', state.apiUrl);
        setVal('dataset', state.dataset);
        setVal('load-type', state.loadType);
        setVal('delay-time-input', state.delayTime);
        setVal('ca-batch-size', state.caBatchSize);
        setVal('ca-x-api-key', state.caXApiKey);

        // Update generic custom dropdowns if they exist
        const envSelect = document.getElementById('environment');

        // Handle specifically our hardcoded Environment dropdown from app.js
        if (envSelect && state.env) {
            const envSelectedText = document.getElementById('env-selected-text');
            const envList = document.getElementById('env-list');

            if (envSelectedText && envList) {
                const listItems = envList.querySelectorAll('li');
                const matchingItem = Array.from(listItems).find(li => li.getAttribute('data-value') === state.env);

                if (matchingItem) {
                    envSelectedText.textContent = matchingItem.textContent;
                }
            }
        }
    } catch (e) {
        console.error("Failed to parse saved form state:", e);
    }
};
