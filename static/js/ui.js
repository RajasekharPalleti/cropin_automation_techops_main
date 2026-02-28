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
