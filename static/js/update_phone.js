// ── Update Phone Number Page JS ──────────────────────────────────────────────
// Uses Cloud token (same SSO flow as translation.js).
// Flow:
//   1. Login → token + appHostUrl stored in localStorage
//   2. GET /services/user/api/users/{id} → store full user object
//   3. Fetch country list from country API, match ISD code → ISO code
//   4. PUT /services/user/api/users/images (multipart) with modified user JSON
// ─────────────────────────────────────────────────────────────────────────────

const LS_TOKEN = 'update_phone_token';
const LS_APP_HOST = 'update_phone_app_host';
const LS_ENV = 'update_phone_env';
const LS_TENANT = 'update_phone_tenant';
const LS_USERNAME = 'update_phone_username';
const LS_COMPANY_ID = 'update_phone_company_id';

const SSO_CONFIG = {
    QA: 'https://v2sso-gcp.cropin.co.in',
    UAT: 'https://v2sso-uat-gcp.cropin.co.in',
    PROD: 'https://sso.sg.cropin.in'
};

// Country API path — base URL is resolved dynamically after login
const COUNTRY_API_PATH = '/services/farm/api/country?size=5000';

// ── runtime state ──
let token = null;
let appHostUrl = null;
let fetchedUser = null;   // stores the full GET response object
let resolvedIso = null;   // stores resolved ISO code string
let countryList = null;   // cached country list

let companyId = 1251;     // default to McCain companyId or auto-detected
let liveUsers = [];       // array of user objects from /services/user/api/users/list/{companyId}
let isUsersLoading = false;
let selectedUser = null;  // user selected from search
let activeDropdownIndex = -1;
let currentQuickFilter = 'all';

// ── helpers ──
function showScreen(id) {
    ['screen-login', 'screen-ops'].forEach(s => {
        const el = document.getElementById(s);
        if (el) el.classList.toggle('active', s === id);
    });
}

function updateSessionBanner() {
    const banner = document.getElementById('session-banner');
    const text = document.getElementById('session-info-text');
    const env = localStorage.getItem(LS_ENV) || '';
    const tenant = localStorage.getItem(LS_TENANT) || '';
    const username = localStorage.getItem(LS_USERNAME) || '';
    const host = localStorage.getItem(LS_APP_HOST) || '';

    if (token) {
        banner.style.display = '';
        text.textContent = `Logged in · CLOUD · ${env}${tenant ? ' · ' + tenant : ''}${username ? ' · ' + username : ''}${host ? ' · ' + host : ''}`;
        document.getElementById('logout-btn').style.display = '';
    } else {
        banner.style.display = 'none';
        document.getElementById('logout-btn').style.display = 'none';
    }
}

function handle401() {
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_APP_HOST);
    token = null; appHostUrl = null;
    alert('Your session has expired (401). Please log in again.');
    updateSessionBanner();
    showScreen('screen-login');
}

function setStatus(elId, msg, color) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!msg) { el.style.display = 'none'; el.innerHTML = ''; return; }
    el.innerHTML = msg;
    el.style.color = color || '#0369a1';
    el.style.display = 'flex';
}

function showErr(elId, msg) {
    const el = document.getElementById(elId);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function hideErr(elId) {
    const el = document.getElementById(elId);
    if (el) el.style.display = 'none';
}

// ── Page init ──
(function init() {
    const savedToken = localStorage.getItem(LS_TOKEN);
    const savedHost = localStorage.getItem(LS_APP_HOST);
    const savedTenant = localStorage.getItem(LS_TENANT);
    const savedEnv = localStorage.getItem(LS_ENV);
    const savedCompany = localStorage.getItem(LS_COMPANY_ID);

    if (savedTenant) document.getElementById('tenant').value = savedTenant;
    if (savedEnv) document.getElementById('env').value = savedEnv;
    if (savedCompany) {
        companyId = parseInt(savedCompany, 10) || 1251;
    }
    const compInput = document.getElementById('company-id-input');
    if (compInput) compInput.value = companyId;

    if (savedToken) {
        token = savedToken;
        appHostUrl = savedHost || '';
        updateSessionBanner();
        showScreen('screen-ops');
        fetchLiveUsers();
    } else {
        showScreen('screen-login');
    }

    // Auto-resolve ISO whenever ISD code input changes (debounced 600ms)
    let isdDebounceTimer = null;
    const isdInput = document.getElementById('isd-code');
    if (isdInput) {
        isdInput.addEventListener('input', function () {
            clearTimeout(isdDebounceTimer);
            resolvedIso = null;
            document.getElementById('iso-resolve-wrap').style.display = 'none';
            hideErr('iso-resolve-error');
            closePayloadPreview();   // collapse stale payload
            isdDebounceTimer = setTimeout(() => {
                if (this.value.trim()) resolveIsoCode();
            }, 600);
        });
    }

    // Close payload preview when contact number or email changes
    const contactInput = document.getElementById('contact-number');
    if (contactInput) contactInput.addEventListener('input', () => closePayloadPreview());
    const emailInput = document.getElementById('user-email');
    if (emailInput) emailInput.addEventListener('input', () => closePayloadPreview());

    // Close user search dropdown on outside click
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.user-search-wrapper')) {
            hideUserDropdown();
        }
    });

    // Listen for company ID input change
    if (compInput) {
        compInput.addEventListener('change', function () {
            const val = parseInt(this.value.trim(), 10);
            if (!isNaN(val) && val > 0 && val !== companyId) {
                companyId = val;
                localStorage.setItem(LS_COMPANY_ID, companyId);
                fetchLiveUsers(true);
            }
        });
    }
})();

// ── Collapse payload preview (used when inputs change) ──
function closePayloadPreview() {
    const wrap = document.getElementById('payload-preview-wrap');
    const btn  = document.getElementById('show-payload-btn');
    if (wrap && wrap.classList.contains('show')) {
        wrap.classList.remove('show');
        if (btn) btn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">code</span> Show Payload';
    }
}


// ── LOGIN ──
async function doLogin() {
    const env = document.getElementById('env').value;
    const tenant = document.getElementById('tenant').value.trim();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const errEl = document.getElementById('login-error');
    const btn = document.getElementById('login-btn');

    hideErr('login-error');

    if (!tenant) { showErr('login-error', 'Tenant Name is required.'); return; }
    if (!username) { showErr('login-error', 'Username is required.'); return; }
    if (!password) { showErr('login-error', 'Password is required.'); return; }

    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Authenticating…';

    try {
        const body = new URLSearchParams({
            username, password,
            grant_type: 'password',
            client_id: 'resource_server',
            client_secret: 'resource_server',
            scope: 'openid'
        });

        const loginUrl = `${SSO_CONFIG[env]}/auth/realms/${encodeURIComponent(tenant)}/protocol/openid-connect/token`;

        const res = await fetch(loginUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body
        });

        if (!res.ok) throw new Error(`Auth failed: ${res.status} ${res.statusText}`);
        const data = await res.json();
        if (!data.access_token) throw new Error('No access_token in response.');

        token = data.access_token;

        // Resolve appHostUrl from tenant config (same pattern as translation.js)
        const CONFIG_HOST = { QA: 'https://intl-v2.cropin.co.in', UAT: 'https://intl-v2uat.cropin.co.in' };
        const FALLBACK_HOST = { QA: 'https://au-v2.cropin.co.in', UAT: 'https://v2uat-gcp.cropin.co.in', PROD: 'https://cloud.cropin.in' };

        if (env === 'PROD') {
            appHostUrl = 'https://cloud.cropin.in';
        } else {
            try {
                const cfgBase = CONFIG_HOST[env];
                if (cfgBase) {
                    const cfgRes = await fetch(`${cfgBase}/${encodeURIComponent(tenant)}`, {
                        headers: { 'accept': 'application/json, text/plain, */*' }
                    });
                    if (cfgRes.ok) {
                        const cfg = await cfgRes.json();
                        if (cfg.appHost) appHostUrl = cfg.appHost.replace(/\/$/, '');
                    }
                }
            } catch (_) { /* silently ignore */ }
            if (!appHostUrl) appHostUrl = FALLBACK_HOST[env] || FALLBACK_HOST.QA;
        }

        localStorage.setItem(LS_TOKEN, token);
        localStorage.setItem(LS_ENV, env);
        localStorage.setItem(LS_TENANT, tenant);
        localStorage.setItem(LS_USERNAME, username);
        localStorage.setItem(LS_APP_HOST, appHostUrl);

        updateSessionBanner();
        showScreen('screen-ops');

        // Discover company ID and fetch live users
        await discoverCompanyId();
        fetchLiveUsers();

    } catch (err) {
        showErr('login-error', err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">lock_open</span> Authenticate &amp; Proceed';
    }
}

// ── LOGOUT ──
function doLogout() {
    [LS_TOKEN, LS_APP_HOST, LS_ENV, LS_TENANT, LS_USERNAME, LS_COMPANY_ID].forEach(k => localStorage.removeItem(k));
    token = null; appHostUrl = null; fetchedUser = null; resolvedIso = null;
    liveUsers = []; selectedUser = null; activeDropdownIndex = -1;
    currentQuickFilter = 'all';

    document.getElementById('session-banner').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    ['tenant', 'username', 'password'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    deselectUser();
    hideErr('login-error');
    showScreen('screen-login');
}

// ── DISCOVER COMPANY ID ──
async function discoverCompanyId() {
    if (!token || !appHostUrl) return;
    try {
        const res = await fetch(`${appHostUrl}/services/user/api/users/user-info`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            const data = await res.json();
            if (data && data.companyId) {
                companyId = Number(data.companyId) || 1251;
                localStorage.setItem(LS_COMPANY_ID, companyId);
                const input = document.getElementById('company-id-input');
                if (input) input.value = companyId;
            }
        }
    } catch (e) {
        console.warn('Could not auto-discover companyId:', e);
    }
}

// ── LIVE USERS: Fetch List from Cropin API ──
// Request URL: https://cloud.cropin.in/services/user/api/users/list/{companyId}?userLoginType=DEFAULT&page=0&size=1000&sort=name,asc
// Request Method: POST
async function fetchLiveUsers(force = false) {
    if (!token || !appHostUrl) return;
    if (isUsersLoading) return;
    if (liveUsers.length > 0 && !force) return;

    const compInput = document.getElementById('company-id-input');
    if (compInput && compInput.value.trim()) {
        const parsed = parseInt(compInput.value.trim(), 10);
        if (!isNaN(parsed) && parsed > 0) {
            companyId = parsed;
            localStorage.setItem(LS_COMPANY_ID, companyId);
        }
    }

    isUsersLoading = true;
    updateLiveUsersUIState('loading');

    const directUrl = `${appHostUrl}/services/user/api/users/list/${companyId}?userLoginType=DEFAULT&page=0&size=1000&sort=name,asc`;
    let usersData = null;
    let fetchError = null;

    // 1. Attempt direct fetch to Cropin API
    try {
        const res = await fetch(directUrl, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (res.status === 401) {
            handle401();
            return;
        }

        if (res.ok) {
            usersData = await res.json();
        } else {
            const errTxt = await res.text();
            throw new Error(`HTTP ${res.status}: ${errTxt.slice(0, 150)}`);
        }
    } catch (err) {
        console.warn('Direct fetch to user list failed, falling back to proxy...', err);
        fetchError = err;
    }

    // 2. Fallback to server proxy endpoint if direct fetch failed
    if (!usersData) {
        try {
            const proxyRes = await fetch('/api/cropin/users/list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    baseUrl: appHostUrl,
                    token: token,
                    companyId: companyId,
                    userLoginType: 'DEFAULT',
                    page: 0,
                    size: 1000,
                    sort: 'name,asc'
                })
            });

            if (proxyRes.status === 401) {
                handle401();
                return;
            }

            if (proxyRes.ok) {
                usersData = await proxyRes.json();
            } else {
                const proxyErr = await proxyRes.text();
                throw new Error(`Proxy ${proxyRes.status}: ${proxyErr.slice(0, 150)}`);
            }
        } catch (proxyErr) {
            console.error('Proxy fetch to user list failed:', proxyErr);
            updateLiveUsersUIState('error', fetchError?.message || proxyErr.message);
            isUsersLoading = false;
            return;
        }
    }

    // Normalize user list array
    if (Array.isArray(usersData)) {
        liveUsers = usersData;
    } else if (usersData && Array.isArray(usersData.content)) {
        liveUsers = usersData.content;
    } else if (usersData && Array.isArray(usersData.users)) {
        liveUsers = usersData.users;
    } else if (usersData && Array.isArray(usersData.data)) {
        liveUsers = usersData.data;
    } else {
        liveUsers = [];
    }

    isUsersLoading = false;
    updateLiveUsersUIState('success');

    // If dropdown currently open, re-render
    const searchInput = document.getElementById('user-search-input');
    if (searchInput && document.activeElement === searchInput) {
        renderSearchResults(searchInput.value.trim());
    }
}

function updateLiveUsersUIState(state, errorMsg) {
    const pill = document.getElementById('live-users-pill');
    const dot = document.getElementById('live-users-dot');
    const countText = document.getElementById('live-users-count-text');
    const reloadBtn = document.getElementById('reload-users-btn');
    const reloadIcon = document.getElementById('reload-users-icon');
    const searchInput = document.getElementById('user-search-input');

    if (state === 'loading') {
        if (pill) pill.className = 'live-status-pill';
        if (dot) dot.className = 'dot-pulse orange';
        if (countText) countText.textContent = `Loading live users…`;
        if (reloadIcon) reloadIcon.classList.add('spin');
        if (reloadBtn) reloadBtn.disabled = true;
        if (searchInput && !searchInput.value) {
            searchInput.placeholder = 'Loading users from cloud…';
        }
    } else if (state === 'success') {
        if (pill) pill.className = 'live-status-pill success';
        if (dot) dot.className = 'dot-pulse';
        if (countText) countText.textContent = `${liveUsers.length.toLocaleString()} live users`;
        if (reloadIcon) reloadIcon.classList.remove('spin');
        if (reloadBtn) reloadBtn.disabled = false;
        if (searchInput && searchInput.placeholder === 'Loading users from cloud…') {
            searchInput.placeholder = 'Type contact number (e.g. 8954646816) or name (e.g. Rana)...';
        }
    } else if (state === 'error') {
        if (pill) pill.className = 'live-status-pill error';
        if (dot) dot.className = 'dot-pulse red';
        if (countText) countText.textContent = 'Error loading users (click Reload)';
        if (reloadIcon) reloadIcon.classList.remove('spin');
        if (reloadBtn) reloadBtn.disabled = false;
        if (searchInput && searchInput.placeholder === 'Loading users from cloud…') {
            searchInput.placeholder = 'Enter search query or User ID manually...';
        }
    }
}

// ── STRING & SEARCH HELPERS ──
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightMatch(text, query) {
    if (!text) return '';
    if (!query) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const q = escapeRegex(query.trim());
    if (!q) return escaped;
    const re = new RegExp(`(${q})`, 'gi');
    return escaped.replace(re, '<mark class="search-highlight">$1</mark>');
}

function highlightPhone(phone, query) {
    if (!phone) return '<span style="color:#94a3b8;font-weight:400;">No contact number</span>';
    const digits = query ? query.replace(/\D/g, '') : '';
    if (digits && digits.length >= 2) {
        const phoneStr = String(phone);
        const idx = phoneStr.indexOf(digits);
        if (idx !== -1) {
            const before = escapeHtml(phoneStr.slice(0, idx));
            const match = escapeHtml(phoneStr.slice(idx, idx + digits.length));
            const after = escapeHtml(phoneStr.slice(idx + digits.length));
            return `${before}<mark class="search-highlight">${match}</mark>${after}`;
        }
    }
    return highlightMatch(String(phone), query);
}

function getInitials(name) {
    if (!name) return 'U';
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
}

const AVATAR_GRADIENTS = [
    'linear-gradient(135deg, #0284c7, #0369a1)',
    'linear-gradient(135deg, #059669, #047857)',
    'linear-gradient(135deg, #7c3aed, #6d28d9)',
    'linear-gradient(135deg, #d97706, #b45309)',
    'linear-gradient(135deg, #db2777, #be185d)',
    'linear-gradient(135deg, #0891b2, #0e7490)',
    'linear-gradient(135deg, #4f46e5, #4338ca)'
];

function getAvatarColor(name) {
    if (!name) return AVATAR_GRADIENTS[0];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const idx = Math.abs(hash) % AVATAR_GRADIENTS.length;
    return AVATAR_GRADIENTS[idx];
}

// ── SEARCH INTERACTION & DROPDOWN ──
function onUserSearchInput() {
    const input = document.getElementById('user-search-input');
    const clearBtn = document.getElementById('clear-search-btn');
    const query = input.value;

    if (clearBtn) clearBtn.style.display = query ? 'flex' : 'none';

    if (!query.trim()) {
        if (liveUsers.length > 0) {
            renderSearchResults('');
        } else {
            hideUserDropdown();
        }
        return;
    }

    renderSearchResults(query.trim());
}

function onUserSearchFocus() {
    const input = document.getElementById('user-search-input');
    const query = input.value.trim();
    if (query) {
        renderSearchResults(query);
    } else if (liveUsers.length > 0) {
        renderSearchResults('');
    }
}

function hideUserDropdown() {
    const dropdown = document.getElementById('user-search-dropdown');
    if (dropdown) dropdown.style.display = 'none';
    activeDropdownIndex = -1;
}

function clearUserSearch() {
    const input = document.getElementById('user-search-input');
    const clearBtn = document.getElementById('clear-search-btn');
    if (input) {
        input.value = '';
        input.focus();
    }
    if (clearBtn) clearBtn.style.display = 'none';
    if (liveUsers.length > 0) {
        renderSearchResults('');
    } else {
        hideUserDropdown();
    }
}

function setQuickFilter(filterKey) {
    currentQuickFilter = filterKey;
    const chips = document.querySelectorAll('#quick-filter-chips .filter-chip');
    chips.forEach(chip => {
        const key = chip.getAttribute('data-filter');
        chip.classList.toggle('active', key === filterKey);
    });

    const searchInput = document.getElementById('user-search-input');
    const query = searchInput ? searchInput.value.trim() : '';
    renderSearchResults(query);
    const dropdown = document.getElementById('user-search-dropdown');
    if (dropdown) dropdown.style.display = 'block';
}

function filterLiveUsers(query) {
    if (!liveUsers || !liveUsers.length) return [];

    let pool = liveUsers;
    if (currentQuickFilter === 'active') {
        pool = pool.filter(u => u.userStatus === 'ACTIVE' || u.enabled === true);
    } else if (currentQuickFilter === 'phone') {
        pool = pool.filter(u => u.contactNumber && String(u.contactNumber).replace(/\D/g, '').length > 0);
    } else if (currentQuickFilter && currentQuickFilter !== 'all') {
        const qf = currentQuickFilter.toLowerCase();
        pool = pool.filter(u => (u.userRoleName || '').toLowerCase().includes(qf));
    }

    if (!query) {
        return pool.slice(0, 30);
    }

    const rawQuery = query.toLowerCase();
    const digitsQuery = query.replace(/\D/g, '');

    const filtered = pool.filter(u => {
        const name = (u.name || '').toLowerCase();
        const phone = (u.contactNumber || '').toString();
        const phoneDigits = phone.replace(/\D/g, '');
        const idStr = String(u.id || '');
        const email = (u.email || '').toLowerCase();

        if (name.includes(rawQuery)) return true;
        if (digitsQuery.length > 0 && phoneDigits.includes(digitsQuery)) return true;
        if (phone.toLowerCase().includes(rawQuery)) return true;
        if (idStr.includes(rawQuery)) return true;
        if (email.includes(rawQuery)) return true;
        return false;
    });

    // Rank results by relevance
    filtered.sort((a, b) => {
        const aName = (a.name || '').toLowerCase();
        const bName = (b.name || '').toLowerCase();
        const aPhoneDigits = (a.contactNumber || '').replace(/\D/g, '');
        const bPhoneDigits = (b.contactNumber || '').replace(/\D/g, '');

        if (digitsQuery) {
            if (aPhoneDigits === digitsQuery && bPhoneDigits !== digitsQuery) return -1;
            if (bPhoneDigits === digitsQuery && aPhoneDigits !== digitsQuery) return 1;
            if (aPhoneDigits.startsWith(digitsQuery) && !bPhoneDigits.startsWith(digitsQuery)) return -1;
            if (bPhoneDigits.startsWith(digitsQuery) && !aPhoneDigits.startsWith(digitsQuery)) return 1;
        }

        if (aName === rawQuery && bName !== rawQuery) return -1;
        if (bName === rawQuery && aName !== rawQuery) return 1;
        if (aName.startsWith(rawQuery) && !bName.startsWith(rawQuery)) return -1;
        if (bName.startsWith(rawQuery) && !aName.startsWith(rawQuery)) return 1;

        return aName.localeCompare(bName);
    });

    return filtered;
}

function renderSearchResults(query) {
    const dropdown = document.getElementById('user-search-dropdown');
    if (!dropdown) return;

    if (isUsersLoading) {
        dropdown.innerHTML = `
            <div class="dropdown-empty-state">
                <span class="material-icons spin" style="font-size:1.4rem;color:var(--blue);margin-bottom:6px;">refresh</span>
                <div>Loading live users from cloud…</div>
            </div>`;
        dropdown.style.display = 'block';
        return;
    }

    if (!liveUsers.length) {
        dropdown.innerHTML = `
            <div class="dropdown-empty-state">
                <span class="material-icons" style="font-size:1.4rem;color:#f59e0b;margin-bottom:6px;">warning</span>
                <div>No users loaded for Company ID ${companyId}.</div>
                <button type="button" class="btn btn-blue" style="margin-top:10px;padding:6px 12px;font-size:0.78rem;" onclick="fetchLiveUsers(true)">
                    Reload Users
                </button>
            </div>`;
        dropdown.style.display = 'block';
        return;
    }

    const matches = filterLiveUsers(query);
    activeDropdownIndex = -1;

    if (!matches.length) {
        dropdown.innerHTML = `
            <div class="dropdown-empty-state">
                <span class="material-icons" style="font-size:1.4rem;color:#94a3b8;margin-bottom:6px;">search_off</span>
                <div>No matching users found for "<strong>${escapeHtml(query)}</strong>"</div>
                <div style="font-size:0.76rem;margin-top:4px;">Try searching by numeric phone number, full name, or User ID.</div>
            </div>`;
        dropdown.style.display = 'block';
        return;
    }

    const displayCount = Math.min(matches.length, 60);
    const items = matches.slice(0, displayCount);

    const matchLabel = query
        ? (matches.length > displayCount ? `Matches (${matches.length}) · Showing ${displayCount}` : `Matches (${matches.length})`)
        : (currentQuickFilter !== 'all' ? `Filtered (${matches.length})` : `All Users (${liveUsers.length})`);

    let html = `
        <div class="dropdown-header-bar">
            <span>${matchLabel}</span>
            <span style="font-size:0.7rem;font-weight:500;color:#94a3b8;">Click to select &amp; fetch details</span>
        </div>`;

    items.forEach((user, index) => {
        const locationStr = user.locations?.name || user.locations?.administrativeAreaLevel1 || user.location || '';
        const role = user.userRoleName || (user.userRoleId ? `Role #${user.userRoleId}` : '');
        const isActive = (user.userStatus === 'ACTIVE' || user.enabled === true);

        html += `
            <div class="user-suggestion-item" data-index="${index}" data-user-id="${user.id}" onclick="selectUserFromSearch(${user.id})">
                <div class="user-avatar-sm" style="background: ${getAvatarColor(user.name)};">
                    ${getInitials(user.name)}
                </div>
                <div class="user-sugg-content">
                    <div class="user-sugg-top">
                        <span class="user-sugg-name">
                            ${highlightMatch(user.name || 'Unnamed User', query)}
                            <span class="user-sugg-contact">(${user.contactNumber ? highlightPhone(user.contactNumber, query) : '<span style="color:#94a3b8;font-weight:400;">No contact number</span>'})</span>
                        </span>
                        ${role ? `<span class="badge-role">${escapeHtml(role)}</span>` : ''}
                        <span class="badge-status ${isActive ? 'active' : 'inactive'}">
                            <span class="status-dot"></span> ${escapeHtml(user.userStatus || (isActive ? 'ACTIVE' : 'INACTIVE'))}
                        </span>
                    </div>
                    <div class="user-sugg-meta">
                        <span class="user-sugg-id">ID: <strong>${highlightMatch(String(user.id), query)}</strong></span>
                        ${user.email ? `<span class="user-sugg-email"><span class="material-icons" style="font-size:0.8rem;">email</span> ${highlightMatch(user.email, query)}</span>` : ''}
                        ${locationStr ? `
                            <span class="user-sugg-loc">
                                <span class="material-icons" style="font-size:0.8rem;">place</span>
                                ${escapeHtml(locationStr)}
                            </span>` : ''}
                    </div>
                </div>
                <div class="btn-select-indicator">
                    <span>Select</span>
                    <span class="material-icons" style="font-size:0.9rem;">arrow_forward</span>
                </div>
            </div>`;
    });

    dropdown.innerHTML = html;
    dropdown.style.display = 'block';
}

function onUserSearchKeydown(e) {
    const dropdown = document.getElementById('user-search-dropdown');
    if (!dropdown || dropdown.style.display === 'none') {
        if (e.key === 'ArrowDown' || e.key === 'Enter') {
            onUserSearchFocus();
        }
        return;
    }

    const items = dropdown.querySelectorAll('.user-suggestion-item');
    if (!items.length) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeDropdownIndex = (activeDropdownIndex + 1) % items.length;
        updateDropdownHighlight(items);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeDropdownIndex = (activeDropdownIndex - 1 + items.length) % items.length;
        updateDropdownHighlight(items);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (activeDropdownIndex >= 0 && activeDropdownIndex < items.length) {
            items[activeDropdownIndex].click();
        } else if (items.length > 0) {
            items[0].click();
        }
    } else if (e.key === 'Escape') {
        hideUserDropdown();
    }
}

function updateDropdownHighlight(items) {
    items.forEach((item, idx) => {
        const isSelected = idx === activeDropdownIndex;
        item.classList.toggle('highlighted', isSelected);
        if (isSelected) {
            item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    });
}

// ── SINGLE SELECT USER: Picks user ID and auto-fetches details ──
async function selectUserFromSearch(userId) {
    const user = liveUsers.find(u => u.id === userId);
    hideUserDropdown();

    if (!user) return;

    selectedUser = user;

    // 1. Single-Select switch: Hide search directory, show active user card
    const searchView = document.getElementById('user-picker-search-view');
    const card = document.getElementById('active-selected-card');
    if (searchView) searchView.style.display = 'none';
    if (card) card.style.display = 'block';

    // 2. Set #user-id input
    const userIdInput = document.getElementById('user-id');
    if (userIdInput) userIdInput.value = user.id;

    // 3. Fill search input in case user switches back later
    const searchInput = document.getElementById('user-search-input');
    const clearBtn = document.getElementById('clear-search-btn');
    if (searchInput) {
        searchInput.value = `${user.name || 'User'} (${user.contactNumber || 'No contact number'})`;
    }
    if (clearBtn) clearBtn.style.display = 'flex';

    // 4. Render active selected card immediately in initial loading state
    renderActiveSelectedCard(user, false);

    // 5. Automatically trigger Fetch User to get full object from Cropin API and populate Step 2
    await doFetchUser(user.id);
}

// ── DESELECT USER: Return to search view ──
function deselectUser() {
    selectedUser = null;
    const searchView = document.getElementById('user-picker-search-view');
    const card = document.getElementById('active-selected-card');
    const searchInput = document.getElementById('user-search-input');
    const clearBtn = document.getElementById('clear-search-btn');

    if (card) card.style.display = 'none';
    if (searchView) searchView.style.display = 'block';

    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
    }
    if (clearBtn) clearBtn.style.display = 'none';

    hideUserDropdown();
}

// ── RENDER ACTIVE SINGLE-SELECTED USER CARD ──
function renderActiveSelectedCard(user, isFullyLoaded = false) {
    const card = document.getElementById('active-selected-card');
    if (!card || !user) return;

    const avatarEl = document.getElementById('sel-avatar');
    const nameEl = document.getElementById('sel-name');
    const roleEl = document.getElementById('sel-role');
    const statusWrapEl = document.getElementById('sel-status');
    const statusTextEl = document.getElementById('sel-status-text');
    const phoneEl = document.getElementById('sel-phone');
    const idEl = document.getElementById('sel-id');
    const emailEl = document.getElementById('sel-email');
    const locEl = document.getElementById('sel-loc');
    const emailBlock = document.getElementById('sel-email-block');
    const locBlock = document.getElementById('sel-loc-block');
    const readyBadge = document.getElementById('sel-ready-badge');

    if (avatarEl) {
        avatarEl.textContent = getInitials(user.name);
        avatarEl.style.background = getAvatarColor(user.name);
    }
    if (nameEl) nameEl.textContent = user.name || `User #${user.id}`;

    const nameContactEl = document.getElementById('sel-name-contact');
    if (nameContactEl) {
        const phone = user.contactNumber ? String(user.contactNumber).trim() : '';
        nameContactEl.textContent = phone ? `(${phone})` : '(No contact number)';
        nameContactEl.style.display = 'inline-block';
    }

    const role = user.userRoleName || (user.userRoleId ? `Role #${user.userRoleId}` : '');
    if (roleEl) {
        roleEl.textContent = role;
        roleEl.style.display = role ? 'inline-block' : 'none';
    }

    const isActive = (user.userStatus === 'ACTIVE' || user.enabled === true);
    if (statusWrapEl) {
        statusWrapEl.className = `badge-status ${isActive ? 'active' : 'inactive'}`;
    }
    if (statusTextEl) {
        statusTextEl.textContent = user.userStatus || (isActive ? 'ACTIVE' : 'INACTIVE');
    }

    if (idEl) idEl.textContent = user.id;

    const formattedPhone = (user.countryCode ? `${user.countryCode} ` : '') + (user.contactNumber || 'None');
    if (phoneEl) phoneEl.textContent = formattedPhone;

    if (user.email) {
        if (emailEl) emailEl.textContent = user.email;
        if (emailBlock) emailBlock.style.display = 'flex';
    } else {
        if (emailBlock) emailBlock.style.display = 'none';
    }

    const locStr = user.locations?.name || user.locations?.administrativeAreaLevel1 || user.location || '';
    if (locStr) {
        if (locEl) locEl.textContent = locStr;
        if (locBlock) locBlock.style.display = 'flex';
    } else {
        if (locBlock) locBlock.style.display = 'none';
    }

    if (readyBadge) {
        if (isFullyLoaded) {
            readyBadge.className = 'active-synced-banner';
            readyBadge.innerHTML = '<span class="material-icons" style="font-size:1.05rem;color:var(--green-dark);">task_alt</span> <span>Details fetched from Live API &amp; synchronized into Step 2</span>';
        } else {
            readyBadge.className = 'active-synced-banner';
            readyBadge.innerHTML = '<span class="material-icons spin" style="font-size:1.05rem;color:var(--blue);">refresh</span> <span>Fetching full details from Cropin API…</span>';
        }
    }

    card.style.display = 'block';
}

function updateSelectedUserCard(user, isFullyLoaded = false) {
    renderActiveSelectedCard(user, isFullyLoaded);
}

function copyUserId() {
    const idVal = selectedUser?.id || document.getElementById('user-id')?.value;
    if (!idVal) return;
    navigator.clipboard.writeText(String(idVal));
    const idEl = document.getElementById('sel-id');
    if (idEl) {
        const orig = idEl.textContent;
        idEl.textContent = '✓ Copied!';
        setTimeout(() => { idEl.textContent = orig; }, 1200);
    }
}

function copyContactNumber() {
    const phoneVal = selectedUser?.contactNumber || document.getElementById('contact-number')?.value;
    if (!phoneVal) return;
    navigator.clipboard.writeText(String(phoneVal));
    const phoneEl = document.getElementById('sel-phone');
    if (phoneEl) {
        const orig = phoneEl.textContent;
        phoneEl.textContent = '✓ Copied!';
        setTimeout(() => { phoneEl.textContent = orig; }, 1200);
    }
}

function toggleManualIdSection() {
    const content = document.getElementById('manual-id-content');
    const icon = document.getElementById('manual-toggle-icon');
    if (!content) return;
    const isHidden = content.style.display === 'none';
    content.style.display = isHidden ? 'block' : 'none';
    if (icon) icon.textContent = isHidden ? 'expand_less' : 'expand_more';
}

// ── STEP 1: Fetch User Details ──
async function doFetchUser(targetUserId) {
    const userIdInput = document.getElementById('user-id');
    if (targetUserId) {
        userIdInput.value = targetUserId;
    }
    const userId = userIdInput.value.trim();

    const btn = document.getElementById('fetch-user-btn');
    const statusEl = document.getElementById('fetch-user-status');
    const resultWrap = document.getElementById('fetch-user-result-wrap');
    const responseEl = document.getElementById('fetch-user-response');

    hideErr('fetch-user-error');
    if (resultWrap) resultWrap.classList.remove('show');
    setStatus('fetch-user-status', '');

    if (!userId) { showErr('fetch-user-error', 'User ID is required.'); return; }
    if (!token) { showErr('fetch-user-error', 'Please log in first.'); return; }

    btn.disabled = true;
    setStatus('fetch-user-status',
        '<span class="material-icons spinner" style="font-size:1rem;">refresh</span> Fetching user…',
        '#1565c0');

    try {
        const url = `${appHostUrl}/services/user/api/users/${encodeURIComponent(userId)}`;
        const res = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (res.status === 401) { handle401(); return; }
        if (!res.ok) {
            const errText = await res.text();
            throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
        }

        const data = await res.json();
        fetchedUser = data;

        // Pre-fill ISD and contact from current user data
        if (data.countryCode)    document.getElementById('isd-code').value       = data.countryCode;
        if (data.contactNumber)  document.getElementById('contact-number').value  = data.contactNumber;
        if (data.email)          document.getElementById('user-email').value       = data.email;

        // Single-select card synchronization
        selectedUser = data;
        const searchView = document.getElementById('user-picker-search-view');
        if (searchView) searchView.style.display = 'none';
        renderActiveSelectedCard(data, true);

        // Pulse Step 2 card to cleanly guide user
        const step2Card = document.getElementById('step2-card');
        if (step2Card) {
            step2Card.classList.remove('step-highlight');
            void step2Card.offsetWidth; // trigger reflow
            step2Card.classList.add('step-highlight');
        }

        // Display formatted JSON
        responseEl.textContent = JSON.stringify(data, null, 2);
        if (resultWrap) resultWrap.classList.add('show');

        setStatus('fetch-user-status',
            `<span class="material-icons" style="font-size:1rem;color:#2e7d32;">check_circle</span> User fetched successfully — ${data.name || data.id}`,
            '#2e7d32');

        // Auto-resolve ISO from the pre-filled ISD code
        await resolveIsoCode();

    } catch (err) {
        showErr('fetch-user-error', `Error: ${err.message}`);
        setStatus('fetch-user-status', '');
    } finally {
        btn.disabled = false;
    }
}


// ── Fetch and cache country list ──
async function getCountryList() {
    if (countryList) return countryList;
    if (!appHostUrl) throw new Error('Base URL not resolved. Please log in again.');
    const url = `${appHostUrl}${COUNTRY_API_PATH}`;
    const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.status === 401) { handle401(); throw new Error('401'); }
    if (!res.ok) throw new Error(`Country API failed: ${res.status}`);
    countryList = await res.json();
    return countryList;
}

// ── Resolve ISO from ISD code ──
async function resolveIsoCode() {
    const isdCode = document.getElementById('isd-code').value.trim();
    const wrapEl = document.getElementById('iso-resolve-wrap');
    const isoEl = document.getElementById('resolved-iso');
    const nameEl = document.getElementById('resolved-country-name');

    wrapEl.style.display = 'none';
    hideErr('iso-resolve-error');
    resolvedIso = null;

    if (!isdCode) { showErr('iso-resolve-error', 'ISD Code is required.'); return; }
    if (!token) { showErr('iso-resolve-error', 'Please log in first.'); return; }

    // Normalize: ensure starts with '+'
    const normalizedIsd = isdCode.startsWith('+') ? isdCode : '+' + isdCode;


    try {
        const countries = await getCountryList();
        // Find country by dialCode (case-insensitive)
        const match = countries.find(c =>
            c.dialCode && c.dialCode.trim().toLowerCase() === normalizedIsd.toLowerCase()
        );

        if (!match) {
            throw new Error(`No country found with dial code "${normalizedIsd}". Please check and try again.`);
        }

        resolvedIso = match.code;
        isoEl.textContent = match.code;
        nameEl.textContent = `(${match.name})`;
        wrapEl.style.display = 'flex';

    } catch (err) {
        showErr('iso-resolve-error', err.message);
    } finally {
    }
}

// ── Show / Hide Payload preview ──
function togglePayload() {
    const wrap    = document.getElementById('payload-preview-wrap');
    const box     = document.getElementById('payload-preview-box');
    const btn     = document.getElementById('show-payload-btn');
    const isOpen  = wrap.classList.contains('show');

    if (isOpen) {
        wrap.classList.remove('show');
        btn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">code</span> Show Payload';
        return;
    }

    // Build the payload using current state
    if (!fetchedUser) {
        box.textContent = '// Fetch user first (Step 1) to preview the payload.';
        wrap.classList.add('show');
        btn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">code</span> Hide Payload';
        return;
    }

    const isdCode       = document.getElementById('isd-code').value.trim();
    const contactNumber = document.getElementById('contact-number').value.trim();
    const normalizedIsd = isdCode.startsWith('+') ? isdCode : '+' + isdCode;

    const email         = document.getElementById('user-email').value.trim();
    const payload = JSON.parse(JSON.stringify(fetchedUser));
    payload.contactNumber = contactNumber || payload.contactNumber;
    payload.countryCode   = normalizedIsd  || payload.countryCode;
    if (email) payload.email = email;
    if (!payload.data) payload.data = {};
    payload.data.countryIsoCode = resolvedIso || (payload.data && payload.data.countryIsoCode) || '';

    box.textContent = JSON.stringify(payload, null, 2);
    wrap.classList.add('show');
    btn.innerHTML = '<span class="material-icons" style="font-size:0.95rem;">code</span> Hide Payload';
}

// ── STEP 2: Update Phone ──
async function doUpdatePhone() {
    const isdCode = document.getElementById('isd-code').value.trim();
    const contactNumber = document.getElementById('contact-number').value.trim();
    const btn = document.getElementById('update-phone-btn');
    const resultWrap = document.getElementById('update-phone-result-wrap');
    const responseEl = document.getElementById('update-phone-response');
    const summaryEl = document.getElementById('update-summary');

    hideErr('update-phone-error');
    setStatus('update-phone-status', '');
    if (resultWrap) resultWrap.classList.remove('show');
    summaryEl.style.display = 'none';

    if (!token) { showErr('update-phone-error', 'Please log in first.'); return; }
    if (!fetchedUser) { showErr('update-phone-error', 'Please fetch the user first (Step 1).'); return; }
    if (!contactNumber) { showErr('update-phone-error', 'Contact Number is required.'); return; }
    if (!isdCode) { showErr('update-phone-error', 'ISD Code is required.'); return; }

    // Auto-resolve ISO if not already done
    if (!resolvedIso) {
        showErr('update-phone-error', 'Please click "Resolve ISO from ISD" before updating.');
        return;
    }

    // Build modified user payload from GET response
    const normalizedIsd = isdCode.startsWith('+') ? isdCode : '+' + isdCode;
    const email         = document.getElementById('user-email').value.trim();

    const payload = JSON.parse(JSON.stringify(fetchedUser)); // deep clone

    // Apply modifications
    payload.contactNumber = contactNumber;
    payload.countryCode   = normalizedIsd;
    payload.email         = email;   // always patch from input (pre-filled or edited)
    if (!payload.data) payload.data = {};
    payload.data.countryIsoCode = resolvedIso;

    // Prepare multipart form data
    const formData = new FormData();
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    formData.append('dto', blob, 'dto.json');

    btn.disabled = true;
    setStatus('update-phone-status',
        '<span class="material-icons spinner" style="font-size:1rem;">refresh</span> Updating user details…',
        '#e65100');

    try {
        const url = `${appHostUrl}/services/user/api/users/images`;
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        if (res.status === 401) { handle401(); return; }

        const text = await res.text();
        let data;
        try { data = JSON.parse(text); } catch (_) { data = text; }

        const prettyJson = typeof data === 'object'
            ? JSON.stringify(data, null, 2)
            : String(data);

        responseEl.textContent = prettyJson;
        if (resultWrap) resultWrap.classList.add('show');

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}: ${String(text).slice(0, 300)}`);
        }

        // Show success summary
        const responseData = typeof data === 'object' ? data : {};
        document.getElementById('sum-contact').textContent = responseData.contactNumber || contactNumber;
        document.getElementById('sum-isd').textContent     = responseData.countryCode   || normalizedIsd;
        document.getElementById('sum-iso').textContent     =
            (responseData.data && responseData.data.countryIsoCode)
                ? responseData.data.countryIsoCode : resolvedIso;
        document.getElementById('sum-email').textContent   = responseData.email         || email;
        summaryEl.style.display = 'block';

        // Update in-memory user objects & liveUsers array
        if (fetchedUser) {
            fetchedUser.contactNumber = contactNumber;
            fetchedUser.countryCode   = normalizedIsd;
            fetchedUser.email         = email;
        }
        if (selectedUser) {
            selectedUser.contactNumber = contactNumber;
            selectedUser.countryCode   = normalizedIsd;
            selectedUser.email         = email;
            renderActiveSelectedCard(selectedUser, true);
            const readyBadge = document.getElementById('sel-ready-badge');
            if (readyBadge) {
                readyBadge.innerHTML = `<span class="material-icons" style="font-size:1.05rem;color:var(--green-dark);">verified</span> <span>Phone successfully updated to ${normalizedIsd} ${contactNumber}</span>`;
            }
        }
        const matchedLiveUser = liveUsers.find(u => String(u.id) === String(fetchedUser?.id || selectedUser?.id));
        if (matchedLiveUser) {
            matchedLiveUser.contactNumber = contactNumber;
            matchedLiveUser.countryCode   = normalizedIsd;
            matchedLiveUser.email         = email;
        }

        setStatus('update-phone-status',
            '<span class="material-icons" style="font-size:1rem;color:#2e7d32;">check_circle</span> User details updated successfully!',
            '#2e7d32');

    } catch (err) {
        showErr('update-phone-error', `Error: ${err.message}`);
        setStatus('update-phone-status', '');
    } finally {
        btn.disabled = false;
    }
}


function togglePasswordVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (input.type === 'password') {
        input.type = 'text';
        icon.textContent = 'visibility_off';
    } else {
        input.type = 'password';
        icon.textContent = 'visibility';
    }
}

// ── STEP 3: Change Password via Automation ──
async function doUpdatePassword() {
    const adminUsername = document.getElementById('admin-username').value.trim();
    const adminPassword = document.getElementById('admin-password').value.trim();
    const newPassword   = document.getElementById('new-password').value.trim();
    const tenant        = document.getElementById('tenant').value.trim().toLowerCase();
    const contactNumber = document.getElementById('contact-number').value.trim();

    hideErr('update-password-error');
    setStatus('update-password-status', '');

    if (!adminUsername || !adminPassword || !newPassword) {
        showErr('update-password-error', 'Admin Username, Admin Password, and New Password are required.');
        return;
    }
    if (!tenant) {
        showErr('update-password-error', 'Tenant is required. Please fill it in Step 1.');
        return;
    }
    if (!contactNumber) {
        showErr('update-password-error', 'Contact Number is required. Please fill it in Step 2.');
        return;
    }

    const btn = document.getElementById('update-password-btn');
    btn.disabled = true;
    setStatus('update-password-status',
        '<span class="material-icons spinner" style="font-size:1rem;">refresh</span> Automating browser to change password. This may take 15-30 seconds...',
        '#6b21a8');

    try {
        const res = await fetch('/api/change-password-automation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                admin_username: adminUsername,
                admin_password: adminPassword,
                new_password: newPassword,
                tenant: tenant,
                contact_number: contactNumber
            })
        });

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            
            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.substring(6));
                    
                    if (data.status === 'progress') {
                        setStatus('update-password-status',
                            `<span class="material-icons spinner" style="font-size:1rem;">refresh</span> ${data.message}`,
                            '#1976d2');
                    } else if (data.status === 'success') {
                        setStatus('update-password-status',
                            `<span class="material-icons" style="font-size:1rem;color:#2e7d32;">check_circle</span> ${data.message}`,
                            '#2e7d32');
                    } else if (data.status === 'error') {
                        showErr('update-password-error', `Automation Error: ${data.message}`);
                        setStatus('update-password-status', '');
                    }
                }
            }
        }

    } catch (err) {
        showErr('update-password-error', `Automation Error: ${err.message}`);
        setStatus('update-password-status', '');
    } finally {
        btn.disabled = false;
    }
}
