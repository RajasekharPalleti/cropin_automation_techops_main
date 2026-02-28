/**
 * backup.js — Backup Modal & File List
 *
 * Manages the Google Drive backup viewer:
 *   - Opens/closes the backup modal
 *   - Fetches paginated file list from /api/backups
 *   - Renders uploaded / downloaded file lists with infinite scroll
 *   - Provides window.openTab() used by onclick attributes in index.html
 *
 * No cross-module dependencies.
 */

document.addEventListener('DOMContentLoaded', () => {

    const backupBtn = document.getElementById('backup-btn');
    const backupModal = document.getElementById('backup-modal');
    const closeModal = document.getElementById('close-modal');
    const uploadedList = document.getElementById('uploaded-list');
    const downloadedList = document.getElementById('downloaded-list');

    let nextPageToken = null;
    let isLoadingBackups = false;

    // ----------------------------------------------------------------
    // Tab switcher (called via onclick in HTML)
    // ----------------------------------------------------------------
    window.openTab = function (evt, tabName) {
        var i, tabcontent, tablinks;

        tabcontent = document.getElementsByClassName('tab-content');
        for (i = 0; i < tabcontent.length; i++) {
            tabcontent[i].style.display = 'none';
            tabcontent[i].classList.remove('active');
        }

        tablinks = document.getElementsByClassName('tab-link');
        for (i = 0; i < tablinks.length; i++) {
            tablinks[i].className = tablinks[i].className.replace(' active', '');
        }

        const tab = document.getElementById(tabName);
        if (tab) {
            tab.style.display = 'block';
            tab.classList.add('active');
        }
        if (evt) evt.currentTarget.className += ' active';
    };

    // ----------------------------------------------------------------
    // Open / close modal
    // ----------------------------------------------------------------
    if (backupBtn) {
        backupBtn.addEventListener('click', () => {
            if (backupModal) backupModal.style.display = 'block';
            fetchBackups(true);
        });
    }

    if (closeModal) {
        closeModal.addEventListener('click', () => {
            if (backupModal) backupModal.style.display = 'none';
        });
    }

    // ----------------------------------------------------------------
    // Infinite scroll — load more when near the bottom of a tab
    // ----------------------------------------------------------------
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.addEventListener('scroll', () => {
            if (tab.scrollTop + tab.clientHeight >= tab.scrollHeight - 50) {
                if (nextPageToken && !isLoadingBackups) {
                    fetchBackups(false);
                }
            }
        });
    });

    // ----------------------------------------------------------------
    // Fetch backups from /api/backups (paginated)
    // ----------------------------------------------------------------
    function fetchBackups(reset = false) {
        if (isLoadingBackups) return;
        isLoadingBackups = true;

        if (reset) {
            nextPageToken = null;
            if (uploadedList) uploadedList.innerHTML = '';
            if (downloadedList) downloadedList.innerHTML = '';

            const loadingLi = document.createElement('li');
            loadingLi.className = 'loading-indicator';
            loadingLi.textContent = 'Loading...';
            if (uploadedList) uploadedList.appendChild(loadingLi.cloneNode(true));
            if (downloadedList) downloadedList.appendChild(loadingLi);
        }

        let url = '/api/backups?page_size=100';
        if (nextPageToken && !reset) url += '&page_token=' + encodeURIComponent(nextPageToken);

        fetch(url)
            .then(r => r.json())
            .then(data => {
                document.querySelectorAll('.loading-indicator').forEach(el => el.remove());
                nextPageToken = data.nextPageToken || null;
                renderFileList(data.uploaded, uploadedList);
                renderFileList(data.downloaded, downloadedList);
            })
            .catch(err => {
                console.error('Failed to fetch backups:', err);
                document.querySelectorAll('.loading-indicator').forEach(el => el.remove());
                window.showToast('Failed to load Google Drive backups. Check console.', 'error');
                if (reset) {
                    if (uploadedList) uploadedList.innerHTML = '<li class="empty-state">Failed to load backups. Error: ' + err.message + '</li>';
                    if (downloadedList) downloadedList.innerHTML = '<li class="empty-state">Failed to load backups.</li>';
                }
            })
            .finally(() => { isLoadingBackups = false; });
    }

    // ----------------------------------------------------------------
    // Render a list of Drive file objects into a <ul>
    // ----------------------------------------------------------------
    function renderFileList(files, listElement) {
        if (!listElement) return;

        if ((!files || files.length === 0) && listElement.children.length === 0) {
            listElement.innerHTML = '<li class="empty-state">No files found.</li>';
            return;
        }
        if (!files) return;

        files.forEach(file => {
            const li = document.createElement('li');
            li.className = 'file-item';

            const date = new Date(file.createdTime).toLocaleString();
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

});
