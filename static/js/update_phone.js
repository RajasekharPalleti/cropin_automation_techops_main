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

    if (savedTenant) document.getElementById('tenant').value = savedTenant;
    if (savedEnv) document.getElementById('env').value = savedEnv;

    if (savedToken) {
        token = savedToken;
        appHostUrl = savedHost || '';
        updateSessionBanner();
        showScreen('screen-ops');
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

    } catch (err) {
        showErr('login-error', err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">lock_open</span> Authenticate &amp; Proceed';
    }
}

// ── LOGOUT ──
function doLogout() {
    [LS_TOKEN, LS_APP_HOST, LS_ENV, LS_TENANT, LS_USERNAME].forEach(k => localStorage.removeItem(k));
    token = null; appHostUrl = null; fetchedUser = null; resolvedIso = null;

    document.getElementById('session-banner').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    ['tenant', 'username', 'password'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    hideErr('login-error');
    showScreen('screen-login');
}

// ── STEP 1: Fetch User ──
async function doFetchUser() {
    const userId = document.getElementById('user-id').value.trim();
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
