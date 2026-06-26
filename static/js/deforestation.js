// ── Deforestation page JS ──────────────────────────────────────────────────
// Persists token + baseUrl in localStorage so page refresh keeps the session.
// 401 from any API call forces re-login.

const LS_TOKEN    = 'deforest_token';
const LS_BASEURL  = 'deforest_baseurl';
const LS_ENV      = 'deforest_env';
const LS_TENANT     = 'deforest_tenant';
const LS_USERNAME   = 'deforest_username';
const LS_PROJECT_ID = 'deforest_project_id';

const SSO_CONFIG = {
    QA:   'https://v2sso-gcp.cropin.co.in',
    UAT:  'https://v2sso-uat-gcp.cropin.co.in',
    PROD: 'https://sso.sg.cropin.in'
};

// ── runtime state ──
let token        = null;
let baseUrl      = null;
let templateId   = null;
let templateName = null;
let uploadId     = null;

let publishExcelData = null;
let publishStopped   = false;
let caBatchIds       = null;
let caBatchStopped   = false;

let projectPage      = 0;
let projectLastPage  = false;
let projectAllItems  = [];
let projectFiltered  = [];
let projectDropOpen  = false;

// ── screen helpers ──
function showScreen(id) {
    ['screen-login', 'screen-ops'].forEach(s => {
        document.getElementById(s).classList.toggle('active', s === id);
    });
}

function updateSessionBanner() {
    const banner = document.getElementById('session-banner');
    const text   = document.getElementById('session-info-text');
    const env      = localStorage.getItem(LS_ENV)      || '';
    const tenant   = localStorage.getItem(LS_TENANT)   || '';
    const username = localStorage.getItem(LS_USERNAME)  || '';
    const bu       = localStorage.getItem(LS_BASEURL)   || '';
    if (token && baseUrl) {
        banner.style.display = '';
        text.textContent = `Logged in · ${env}${tenant ? ' · ' + tenant : ''}${username ? ' · ' + username : ''} · ${bu}`;
        document.getElementById('logout-btn').style.display = '';
    } else {
        banner.style.display = 'none';
        document.getElementById('logout-btn').style.display = 'none';
    }
}

// ── on page load: restore session ──
(function init() {
    const savedToken   = localStorage.getItem(LS_TOKEN);
    const savedBaseUrl = localStorage.getItem(LS_BASEURL);
    const savedTenant  = localStorage.getItem(LS_TENANT);
    const savedEnv     = localStorage.getItem(LS_ENV);

    // Pre-fill login fields from cache
    if (savedTenant) document.getElementById('tenant').value = savedTenant;
    if (savedEnv)    document.getElementById('env').value    = savedEnv;
    const savedProjectId = localStorage.getItem(LS_PROJECT_ID);
    if (savedProjectId) {
        document.getElementById('project-id').value = savedProjectId;
        document.getElementById('project-display-text').textContent = `${savedProjectId} — (cached)`;
        document.getElementById('project-display-text').style.color = '#1a1a2e';
        document.getElementById('project-display').style.borderColor = '#2e7d32';
    }

    // Restore session if token exists — only a 401 from an API should force re-login
    if (savedToken) {
        token   = savedToken;
        baseUrl = savedBaseUrl || '';
        updateSessionBanner();
        showScreen('screen-ops');
    } else {
        showScreen('screen-login');
    }

    // wire manual-id inputs to enable their buttons independently
    wire('manual-template-id',      'dl-btn');
    wire('manual-upload-id-process','process-btn');
    wire('manual-upload-id-status', 'status-btn');
    wire('manual-upload-id-fallback','fallback-btn');

    // sustainability checkbox
    document.getElementById('sustainability').addEventListener('change', function () {
        const d = this.checked ? 'inline' : 'none';
        document.getElementById('start-req').style.display = d;
        document.getElementById('end-req').style.display   = d;
    });

    // file pickers
    document.getElementById('publish-file').addEventListener('change', onPublishFileChange);
    document.getElementById('ca-file').addEventListener('change', onCaFileChange);
})();

function wire(inputId, btnId) {
    document.getElementById(inputId).addEventListener('input', () => {
        if (document.getElementById(inputId).value.trim())
            document.getElementById(btnId).disabled = false;
    });
}

// ── 401 handler ──
function handle401() {
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_BASEURL);
    token = null; baseUrl = null;
    alert('Your session has expired (401). Please log in again.');
    updateSessionBanner();
    showScreen('screen-login');
}

// ── LOGIN ──
async function doLogin() {
    const env      = document.getElementById('env').value;
    const tenant   = document.getElementById('tenant').value.trim();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const errEl    = document.getElementById('login-error');
    const btn      = document.getElementById('login-btn');

    errEl.style.display = 'none';
    if (!tenant || !username || !password) {
        errEl.textContent = 'Tenant Name, Username and Password are required.';
        errEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Authenticating…';

    try {
        const body = new URLSearchParams({
            username, password,
            grant_type: 'password',
            client_id: 'resource_server',
            client_secret: 'resource_server'
        });
        const res = await fetch(
            `${SSO_CONFIG[env]}/auth/realms/${encodeURIComponent(tenant)}/protocol/openid-connect/token`,
            { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body }
        );
        if (!res.ok) throw new Error(`Auth failed: ${res.status} ${res.statusText}`);
        const data = await res.json();
        if (!data.access_token) throw new Error('No access_token in response.');
        token = data.access_token;
        localStorage.setItem(LS_TOKEN,    token);
        localStorage.setItem(LS_ENV,      env);
        localStorage.setItem(LS_TENANT,   tenant);
        localStorage.setItem(LS_USERNAME, username);

        // Auto-fetch/set appHost from tenant config
        const CONFIG_HOST = { QA: 'https://intl-v2.cropin.co.in', UAT: 'https://intl-v2uat.cropin.co.in' };
        const FALLBACK_HOST = { QA: 'https://au-v2-gcp.cropin.co.in', UAT: 'https://au-v2uat-gcp.cropin.co.in', PROD: 'https://cloud.cropin.in' };
        try {
            if (env === 'PROD') {
                baseUrl = 'https://cloud.cropin.in';
            } else {
                const cfgBase = CONFIG_HOST[env];
                if (!cfgBase) throw new Error('no config host for env');
                const cfgRes = await fetch(`${cfgBase}/${encodeURIComponent(tenant)}`, {
                    headers: { 'accept': 'application/json, text/plain, */*', 'accept-language': 'en-GB,en;q=0.5' }
                });
                if (cfgRes.ok) {
                    const cfg = await cfgRes.json();
                    if (cfg.appHost) {
                        baseUrl = cfg.appHost.replace(/\/$/, '');
                    }
                }
            }
        } catch (_) {
            // silently ignore
        }
        // Always ensure baseUrl is set — fall back to a sensible default if auto-fetch failed
        if (!baseUrl) baseUrl = FALLBACK_HOST[env] || FALLBACK_HOST.QA;
        localStorage.setItem(LS_BASEURL, baseUrl);

        updateSessionBanner();
        showScreen('screen-ops');
    } catch (err) {
        errEl.textContent = err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">lock_open</span> Authenticate & Proceed';
    }
}


// ── LOGOUT ──
function doLogout() {
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_BASEURL);
    localStorage.removeItem(LS_ENV);
    localStorage.removeItem(LS_TENANT);
    localStorage.removeItem(LS_USERNAME);
    localStorage.removeItem(LS_PROJECT_ID);
    token = null; baseUrl = null; templateId = null; templateName = null; uploadId = null;
    projectAllItems = []; projectFiltered = []; projectPage = 0; projectLastPage = false; projectDropOpen = false;
    document.getElementById('session-banner').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    // clear login fields
    ['tenant','username','password'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('login-error').style.display = 'none';
    showScreen('screen-login');
}

// ── API 1: Generate Template ──
async function doGenerate() {
    const btn    = document.getElementById('gen-btn');
    const status = document.getElementById('gen-status');
    const errEl  = document.getElementById('gen-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Generating…';
    status.textContent = 'Generating…';
    try {
        const res = await fetch(
            `${baseUrl}/services/fileupload-service/api/bulk-downloads/template?feature=ONBOARD_FARMER_ASSET_FORM`,
            { headers: { 'Authorization': `Bearer ${token}` } }
        );
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        const data = await res.json();
        templateId   = data.id   ?? data.templateId   ?? data.data?.id;
        templateName = data.name ?? data.templateName ?? data.data?.name;
        if (!templateId || !templateName) throw new Error('Could not find id or name in the response.');
        document.getElementById('manual-template-id').value = templateId;
        document.getElementById('dl-btn').disabled = false;
        status.innerHTML = `<span style="color:#2e7d32;">&#10003; ID: <strong>${templateId}</strong> &nbsp;|&nbsp; Name: <strong>${templateName}</strong></span>`;
    } catch (err) {
        status.textContent = '';
        errEl.textContent = 'Generate Template: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">description</span> Generate Template';
    }
}

// ── API 2: Download Template ──
async function doDownloadTemplate() {
    const tid    = document.getElementById('manual-template-id').value.trim() || templateId;
    const tname  = templateName || tid || 'template';
    const btn    = document.getElementById('dl-btn');
    const status = document.getElementById('dl-status');
    const errEl  = document.getElementById('dl-error');
    errEl.style.display = 'none';
    if (!tid) { errEl.textContent = 'No Template ID. Run Generate Template or enter one manually.'; errEl.style.display = 'block'; return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Downloading…';
    status.textContent = 'Downloading…';
    try {
        const res = await fetch(
            `${baseUrl}/services/fileupload-service/api/bulk-downloads/mass-upload-template/${tid}`,
            { headers: { 'Authorization': `Bearer ${token}` } }
        );
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        const blob = await res.blob();
        triggerDownload(blob, `${tname}.xlsx`);
        status.innerHTML = `<span style="color:#2e7d32;">&#10003; Downloaded as <strong>${tname}.xlsx</strong></span>`;
    } catch (err) {
        status.textContent = '';
        errEl.textContent = 'Download Template: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">cloud_download</span> Download Template';
    }
}

// ── Project dropdown ──────────────────────────────────────────────────────
async function fetchProjects(page) {
    const list    = document.getElementById('project-list');
    const pageInfo= document.getElementById('proj-page-info');
    list.innerHTML = '<div style="padding:16px;text-align:center;color:#888;font-size:0.83rem;">Loading…</div>';
    try {
        const url = `${baseUrl}/services/farm/api/projects/filter?sort=projectStatus,asc&sort=lastModifiedDate,desc&projectExecutionStatus=TO_BE_STARTED&projectExecutionStatus=STARTED&projectStatus=UPCOMING&page=${page}&size=100`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ statusList: ['LIVE', 'PAST', 'UPCOMING'], projectStatusList: ['TO_BE_STARTED', 'STARTED'] })
        });
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data = await res.json();
        // response may be array or { content: [] }
        const items = Array.isArray(data) ? data : (data.content || []);
        projectAllItems = items.map(p => ({ id: p.id, name: p.name }));
        projectLastPage = Array.isArray(data) ? items.length < 100 : (data.last ?? items.length < 100);
        projectPage = page;
        pageInfo.textContent = `Page ${page + 1}`;
        document.getElementById('proj-prev-btn').disabled = page === 0;
        document.getElementById('proj-next-btn').disabled = projectLastPage;
        // reset search and render
        document.getElementById('project-search').value = '';
        projectFiltered = projectAllItems;
        renderProjectList(projectFiltered);
    } catch (err) {
        list.innerHTML = `<div style="padding:12px 14px;color:#c0392b;font-size:0.83rem;">Failed to load projects: ${err.message}</div>`;
    }
}

function renderProjectList(items) {
    const list = document.getElementById('project-list');
    list.innerHTML = '';
    if (!items.length) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px 14px;color:#888;font-size:0.83rem;';
        empty.textContent = 'No projects found.';
        list.appendChild(empty);
        return;
    }
    items.forEach(p => {
        const row = document.createElement('div');
        row.style.cssText = 'padding:9px 14px;cursor:pointer;font-size:0.85rem;border-bottom:1px solid #f3f3f3;transition:background .1s;';
        const idSpan = document.createElement('span');
        idSpan.style.cssText = 'font-weight:600;color:#2e7d32;';
        idSpan.textContent = p.id;
        const nameSpan = document.createElement('span');
        nameSpan.style.cssText = 'color:#555;margin-left:8px;';
        nameSpan.textContent = p.name;
        row.appendChild(idSpan);
        row.appendChild(nameSpan);
        row.addEventListener('mouseover', () => { row.style.background = '#f0faf0'; });
        row.addEventListener('mouseout',  () => { row.style.background = ''; });
        row.addEventListener('mousedown', e => {
            e.preventDefault();
            e.stopPropagation();
            selectProject(p.id, p.name);
        });
        list.appendChild(row);
    });
}

function selectProjectByIndex(el) {
    const idx = parseInt(el.dataset.pidx, 10);
    const p = projectFiltered[idx];
    if (p) selectProject(p.id, p.name);
}

function filterProjects(query) {
    const q = query.trim().toLowerCase();
    projectFiltered = q ? projectAllItems.filter(p => p.name.toLowerCase().includes(q)) : projectAllItems;
    renderProjectList(projectFiltered);
}

function selectProject(id, name) {
    document.getElementById('project-id').value           = id;
    document.getElementById('project-display-text').textContent = `${id} — ${name}`;
    document.getElementById('project-display-text').style.color = '#1a1a2e';
    document.getElementById('project-display').style.borderColor = '#2e7d32';
    localStorage.setItem(LS_PROJECT_ID, id);
    closeProjectDropdown();
}

function toggleProjectDropdown() {
    if (projectDropOpen) { closeProjectDropdown(); return; }
    projectDropOpen = true;
    const panel   = document.getElementById('project-dropdown-panel');
    const chevron = document.getElementById('project-chevron');
    const display = document.getElementById('project-display');
    panel.style.display  = 'block';
    chevron.textContent  = 'expand_less';
    display.style.borderColor = '#2e7d32';
    if (!projectAllItems.length) fetchProjects(0);
}

function closeProjectDropdown() {
    projectDropOpen = false;
    document.getElementById('project-dropdown-panel').style.display = 'none';
    document.getElementById('project-chevron').textContent = 'expand_more';
    const selId = document.getElementById('project-id').value;
    document.getElementById('project-display').style.borderColor = selId ? '#2e7d32' : '#ccc';
}

function projectNextPage() { if (!projectLastPage) fetchProjects(projectPage + 1); }
function projectPrevPage() { if (projectPage > 0)  fetchProjects(projectPage - 1); }

// close on outside click
document.addEventListener('click', e => {
    if (projectDropOpen && !document.getElementById('project-dropdown-wrapper').contains(e.target))
        closeProjectDropdown();
});

// ── API 3: Upload Template ──
async function doUpload() {
    const file           = document.getElementById('upload-file').files[0];
    const projectId      = document.getElementById('project-id').value.trim();
    const startDate      = document.getElementById('start-date').value;
    const endDate        = document.getElementById('end-date').value;
    const sustainability = document.getElementById('sustainability').checked;
    const btn    = document.getElementById('upload-btn');
    const status = document.getElementById('upload-status');
    const errEl  = document.getElementById('upload-error');

    errEl.style.display = 'none';
    if (!file)      { errEl.textContent = 'Please select a file.';   errEl.style.display = 'block'; return; }
    if (!projectId) { errEl.textContent = 'Project ID is required.'; errEl.style.display = 'block'; return; }
    if (sustainability && !startDate) { errEl.textContent = 'Start Date is required when SUSTAINABILITY is enabled.'; errEl.style.display = 'block'; return; }
    if (sustainability && !endDate)   { errEl.textContent = 'End Date is required when SUSTAINABILITY is enabled.';   errEl.style.display = 'block'; return; }

    const requestDto = {
        projectId,
        ...(sustainability && startDate && { startDate }),
        ...(sustainability && endDate   && { endDate }),
        ...(sustainability && { enableFeatures: ['SUSTAINABILITY'] })
    };
    const formData = new FormData();
    formData.append('feature', 'ONBOARD_FARMER_ASSET_FORM');
    formData.append('file', file);
    formData.append('bulkUploadRequestDto', new Blob([JSON.stringify(requestDto)], { type: 'application/json' }));

    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Uploading…';
    status.textContent = 'Uploading…';
    try {
        const res = await fetch(
            `${baseUrl}/services/fileupload-service/api/bulk-uploads/template`,
            { method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData }
        );
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        const data = await res.json();
        uploadId = data.id ?? data.uploadId ?? data.data?.id;
        if (!uploadId) throw new Error('Could not find id in the upload response.');
        // populate all upload-id fields
        document.getElementById('manual-upload-id-process').value  = uploadId;
        document.getElementById('manual-upload-id-status').value   = uploadId;
        document.getElementById('manual-upload-id-fallback').value = uploadId;
        document.getElementById('process-btn').disabled = false;
        status.innerHTML = `<span style="color:#2e7d32;">&#10003; Upload ID: <strong>${uploadId}</strong> saved.</span>`;
    } catch (err) {
        status.textContent = '';
        errEl.textContent = 'Upload Template: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">upload_file</span> Upload Template';
    }
}

// ── API 4: Process Template ──
async function doProcess() {
    const uid   = document.getElementById('manual-upload-id-process').value.trim() || uploadId;
    const btn   = document.getElementById('process-btn');
    const status= document.getElementById('process-status');
    const errEl = document.getElementById('process-error');
    errEl.style.display = 'none';
    if (!uid) { errEl.textContent = 'No Upload ID. Run Upload Template or enter one manually.'; errEl.style.display = 'block'; return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Processing…';
    status.textContent = 'Processing…';
    try {
        const res = await fetch(
            `${baseUrl}/services/fileupload-service/api/process-uploads/${uid}`,
            { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } }
        );
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        document.getElementById('status-btn').disabled = false;
        status.innerHTML = `<span style="color:#2e7d32;">&#10003; Process started for Upload ID: <strong>${uid}</strong></span>`;
    } catch (err) {
        status.textContent = '';
        errEl.textContent = 'Process Template: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">play_circle</span> Proceed';
    }
}

// ── API 5: Upload Template Status ──
async function doStatus() {
    const uid    = document.getElementById('manual-upload-id-status').value.trim() || uploadId;
    const btn    = document.getElementById('status-btn');
    const errEl  = document.getElementById('status-error');
    const respEl = document.getElementById('status-response');
    const jsonEl = document.getElementById('status-json');
    errEl.style.display = 'none';
    respEl.style.display = 'none';
    if (!uid) { errEl.textContent = 'No Upload ID. Run Upload Template or enter one manually.'; errEl.style.display = 'block'; return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Checking…';
    try {
        const res = await fetch(
            `${baseUrl}/services/fileupload-service/api/bulk-uploads/${uid}`,
            { headers: { 'Authorization': `Bearer ${token}` } }
        );
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        const data = await res.json();
        jsonEl.textContent = JSON.stringify(data, null, 2);
        respEl.style.display = 'block';
        document.getElementById('fallback-btn').disabled = false;
    } catch (err) {
        errEl.textContent = 'Upload Template Status: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">refresh</span> Check Status';
    }
}

// ── API 5b: Download Fallback Template ──
async function doFallback() {
    const uid   = document.getElementById('manual-upload-id-fallback').value.trim() || uploadId;
    const btn   = document.getElementById('fallback-btn');
    const errEl = document.getElementById('fallback-error');
    errEl.style.display = 'none';
    if (!uid) { errEl.textContent = 'No Upload ID. Run Upload Template or enter one manually.'; errEl.style.display = 'block'; return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Downloading…';
    try {
        const res = await fetch('/api/deforestation/download-fallback-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ baseUrl, token, uploadId: uid })
        });
        if (res.status === 401) { handle401(); return; }
        if (!res.ok) { const t = await res.text(); throw new Error(`API error: ${res.status} — ${t}`); }
        const blob = await res.blob();
        triggerDownload(blob, `fallback_OnboardFarmerAssetTemplate${uid}.xlsx`);
    } catch (err) {
        errEl.textContent = 'Download Fallback Template: ' + err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">download</span> Download Fallback Template';
    }
}

// ── API 6: Publish Deforestation ──
async function onPublishFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('publish-filename').textContent = file.name;
    document.getElementById('publish-btn').disabled = true;
    const terminal = document.getElementById('publish-terminal');
    terminal.style.display = 'block';
    terminal.innerHTML = '';
    termLog(terminal, `📂 Reading file: ${file.name}`, '#9cdcfe');
    try {
        publishExcelData = await readExcelColumn(file, /sr\s*plot\s*id/i, 1, terminal);
        termLog(terminal, `📋 Found ${publishExcelData.length} SR Plot ID(s) to process`, '#ce9178');
        document.getElementById('publish-btn').disabled = false;
    } catch (err) {
        termLog(terminal, `❌ Error reading file: ${err.message}`, '#f44747');
        publishExcelData = null;
    }
}

async function doPublish() {
    if (!publishExcelData?.length) return;
    const btn      = document.getElementById('publish-btn');
    const stopBtn  = document.getElementById('publish-stop-btn');
    const terminal = document.getElementById('publish-terminal');
    publishStopped = false;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Publishing…';
    stopBtn.style.display = '';
    stopBtn.disabled = false;
    termLog(terminal, `\n🚀 Starting publish for ${publishExcelData.length} record(s)…`, '#569cd6');
    termLog(terminal, '─'.repeat(50), '#555');

    let success = 0, failed = 0;
    for (let i = 0; i < publishExcelData.length; i++) {
        if (publishStopped) { termLog(terminal, `⛔ Stopped by user after ${i} record(s).`, '#f4a742'); break; }
        const srPlotId = publishExcelData[i];
        termLog(terminal, `[${i+1}/${publishExcelData.length}] Publishing SR Plot ID: ${srPlotId} …`, '#d4d4d4');
        try {
            const res = await fetch(
                `${baseUrl}/services/farm/api/deforestation/publish-status?srPlotId=${encodeURIComponent(srPlotId)}`,
                { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: '{}' }
            );
            if (res.status === 401) { handle401(); return; }
            if (res.status === 200) { termLog(terminal, `   ✅ Success (200)`, '#4ec9b0'); success++; }
            else { termLog(terminal, `   ❌ Failed (${res.status}: ${res.statusText})`, '#f44747'); failed++; }
        } catch (err) {
            termLog(terminal, `   ❌ Error: ${err.message}`, '#f44747'); failed++;
        }
        if (i < publishExcelData.length - 1) {
            termLog(terminal, `   ⏳ Waiting 2 seconds…`, '#808080');
            await sleep(2000);
        }
    }
    termLog(terminal, '─'.repeat(50), '#555');
    termLog(terminal, `✔ Done — ${success} succeeded, ${failed} failed`, success > 0 && failed === 0 ? '#4ec9b0' : '#ce9178');
    btn.disabled = false;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">publish</span> Publish Deforestation';
    stopBtn.style.display = 'none';
}

function publishStop() {
    publishStopped = true;
    document.getElementById('publish-stop-btn').disabled = true;
}

// ── API 7: Croppable Areas Sustainability Batch ──
async function onCaFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('ca-filename').textContent = file.name;
    document.getElementById('ca-run-btn').disabled = true;
    const terminal = document.getElementById('ca-terminal');
    terminal.style.display = 'block';
    terminal.innerHTML = '';
    termLog(terminal, `📂 Reading file: ${file.name}`, '#9cdcfe');
    try {
        caBatchIds = await readExcelColumn(file, /ca\s*id/i, 0, terminal);
        termLog(terminal, `📋 Found ${caBatchIds.length} CA ID(s)`, '#ce9178');
        document.getElementById('ca-run-btn').disabled = false;
    } catch (err) {
        termLog(terminal, `❌ Error reading file: ${err.message}`, '#f44747');
        caBatchIds = null;
    }
}

async function doCaBatch() {
    if (!caBatchIds?.length) return;
    const startDate  = document.getElementById('ca-start-date').value;
    const endDate    = document.getElementById('ca-end-date').value;
    const batchSize  = Math.max(1, parseInt(document.getElementById('ca-batch-size').value) || 10);
    const sleepSecs  = Math.max(0, parseFloat(document.getElementById('ca-sleep-secs').value) || 0);
    const terminal   = document.getElementById('ca-terminal');
    if (!startDate || !endDate) {
        terminal.style.display = 'block';
        termLog(terminal, '❌ Please select both Start Date and End Date.', '#f44747');
        return;
    }
    const btn     = document.getElementById('ca-run-btn');
    const stopBtn = document.getElementById('ca-stop-btn');
    caBatchStopped = false;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">hourglass_top</span> Running…';
    stopBtn.style.display = '';
    stopBtn.disabled = false;
    terminal.style.display = 'block';
    terminal.innerHTML = '';
    termLog(terminal, `🚀 Sending batch of ${caBatchIds.length} CA ID(s)…`, '#569cd6');
    termLog(terminal, `   Start Date  : ${startDate}`, '#9cdcfe');
    termLog(terminal, `   End Date    : ${endDate}`, '#9cdcfe');
    termLog(terminal, `   Batch Size  : ${batchSize}`, '#9cdcfe');
    termLog(terminal, `   Sleep       : ${sleepSecs}s between batches`, '#9cdcfe');
    termLog(terminal, '─'.repeat(50), '#555');

    const CHUNK = batchSize;
    let success = 0, failed = 0;
    for (let i = 0; i < caBatchIds.length; i += CHUNK) {
        if (caBatchStopped) { termLog(terminal, `⛔ Stopped by user after ${i} record(s).`, '#f4a742'); break; }
        const chunk = caBatchIds.slice(i, i + CHUNK);
        termLog(terminal, `[${i+1}–${Math.min(i+CHUNK, caBatchIds.length)}/${caBatchIds.length}] Posting chunk of ${chunk.length} ID(s)…`, '#d4d4d4');
        try {
            const payload = chunk.map(id => ({
                croppableAreaId: id,
                startDate,
                endDate,
                sustainabilityEnabled: true
            }));
            const res = await fetch(
                `${baseUrl}/services/farm/api/croppable-areas/sustainability/v2/batch?features=SUSTAINABILITY`,
                { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(payload) }
            );
            if (res.status === 401) { handle401(); return; }
            if (res.ok) { termLog(terminal, `   ✅ Success (${res.status})`, '#4ec9b0'); success += chunk.length; }
            else { termLog(terminal, `   ❌ Failed (${res.status}: ${res.statusText})`, '#f44747'); failed += chunk.length; }
        } catch (err) {
            termLog(terminal, `   ❌ Error: ${err.message}`, '#f44747'); failed += chunk.length;
        }
        if (i + CHUNK < caBatchIds.length && sleepSecs > 0) {
            termLog(terminal, `   ⏳ Waiting ${sleepSecs}s…`, '#808080');
            await sleep(sleepSecs * 1000);
        }
    }
    termLog(terminal, '─'.repeat(50), '#555');
    termLog(terminal, `✔ Done — ${success} succeeded, ${failed} failed`, success > 0 && failed === 0 ? '#4ec9b0' : '#ce9178');
    btn.disabled = false;
    btn.innerHTML = '<span class="material-icons" style="font-size:1rem;">eco</span> Run Batch';
    stopBtn.style.display = 'none';
}

function caStop() {
    caBatchStopped = true;
    document.getElementById('ca-stop-btn').disabled = true;
}

// ── utilities ──
function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a   = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
}

function termLog(terminal, msg, color) {
    const span = document.createElement('span');
    span.style.color = color || '#d4d4d4';
    span.textContent = msg + '\n';
    terminal.appendChild(span);
    terminal.scrollTop = terminal.scrollHeight;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function readExcelColumn(file, headerRegex, fallbackColIdx, terminal) {
    const data = await file.arrayBuffer();
    let rows = [];
    if (window.XLSX) {
        const wb  = XLSX.read(data, { type: 'array' });
        const ws  = wb.Sheets[wb.SheetNames[0]];
        const json = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
        if (json.length < 2) throw new Error('Excel has no data rows');
        const headers = json[0].map(h => String(h).trim());
        const idx = headers.findIndex(h => headerRegex.test(h));
        const col = idx >= 0 ? idx : fallbackColIdx;
        termLog(terminal, `✅ Detected column: "${headers[col] || 'column ' + (col+1)}" (index ${col})`, '#4ec9b0');
        rows = json.slice(1).map(r => String(r[col] || '').trim()).filter(v => v);
    } else {
        const text  = new TextDecoder().decode(data);
        const lines = text.split(/\r?\n/).filter(l => l.trim());
        if (lines.length < 2) throw new Error('File has no data rows');
        const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
        const idx = headers.findIndex(h => headerRegex.test(h));
        const col = idx >= 0 ? idx : fallbackColIdx;
        termLog(terminal, `✅ Detected column: "${headers[col] || 'column ' + (col+1)}" (index ${col})`, '#4ec9b0');
        rows = lines.slice(1).map(l => {
            const parts = l.split(',');
            return String(parts[col] || '').trim().replace(/^"|"$/g, '');
        }).filter(v => v);
    }
    return rows;
}
