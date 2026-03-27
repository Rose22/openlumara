// =============================================================================
// Storage Editor
// =============================================================================

let storageFiles = [];
let currentStorageFile = null;
let currentStorageType = null;
let currentStorageData = null;
let currentDictKey = null;
let storageDirty = false;

function showStorageEditor() {
    toggleModal('storage');
    loadStorageFiles();
}

function loadStorageFiles() {
    const fileList = document.getElementById('storage-file-list');
    fileList.innerHTML = '<div class="storage-loading"><div class="storage-spinner"></div></div>';

    fetch('/storage/list')
        .then(r => r.json())
        .then(data => {
            storageFiles = data.files || [];
            renderStorageFiles(storageFiles);
        })
        .catch(err => {
            fileList.innerHTML = `<div class="storage-error"><p>Failed to load files</p></div>`;
            console.error('Error loading storage files:', err);
        });
}

function renderStorageFiles(files) {
    const fileList = document.getElementById('storage-file-list');

    if (files.length === 0) {
        fileList.innerHTML = '<div class="storage-placeholder"><p>No storage files found</p></div>';
        return;
    }

    fileList.innerHTML = files.map(file => {
        let icon = '📄';
        if (file.type === 'dict') icon = '📁';
        else if (file.type === 'list') icon = '📋';
        else if (file.type === 'text') icon = '📝';

        return `
            <div class="storage-file-item ${currentStorageFile === file.path ? 'active' : ''}"
                 onclick="loadStorageFile('${file.path}')"
                 data-type="${file.type}">
                <span class="storage-file-icon">${icon}</span>
                <span class="storage-file-name" title="${file.path}">${file.path}</span>
            </div>
        `;
    }).join('');
}

function filterStorageFiles(query) {
    const q = query.toLowerCase();
    const filtered = storageFiles.filter(f => f.path.toLowerCase().includes(q));
    renderStorageFiles(filtered);
}

function loadStorageFile(filePath) {
    // Update active state
    document.querySelectorAll('.storage-file-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.storage-file-name').title === filePath);
    });

    // Show loading
    hideAllStorageEditors();
    document.getElementById('storage-loading').style.display = 'flex';

    fetch(`/storage/load?file=${encodeURIComponent(filePath)}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('storage-loading').style.display = 'none';

            if (!data.success) {
                showStorageError(data.error || 'Failed to load file');
                return;
            }

            currentStorageFile = filePath;
            currentStorageType = data.type;
            currentStorageData = data.data;
            storageDirty = false;
            updateDirtyIndicator();

            if (data.type === 'dict') {
                renderDictEditor(data.keys, data.data);
            } else if (data.type === 'list') {
                renderListEditor(data.data);
            } else if (data.type === 'text') {
                renderTextEditor(data.data);
            }

            document.getElementById('storage-footer').style.display = 'flex';
        })
        .catch(err => {
            document.getElementById('storage-loading').style.display = 'none';
            showStorageError('Error loading file');
            console.error('Error:', err);
        });
}

function hideAllStorageEditors() {
    document.getElementById('storage-placeholder').style.display = 'none';
    document.getElementById('storage-loading').style.display = 'none';
    document.getElementById('storage-error').style.display = 'none';
    document.getElementById('storage-dict-editor').style.display = 'none';
    document.getElementById('storage-list-editor').style.display = 'none';
    document.getElementById('storage-text-editor').style.display = 'none';
}

function showStorageError(msg) {
    hideAllStorageEditors();
    document.getElementById('storage-error').style.display = 'flex';
    document.getElementById('storage-error-msg').textContent = msg;
}

// =============================================================================
// Dict Editor
// =============================================================================

function renderDictEditor(keys, data) {
    hideAllStorageEditors();
    document.getElementById('storage-dict-editor').style.display = 'flex';

    const keysList = document.getElementById('storage-dict-keys');
    keysList.innerHTML = keys.map(key => `
        <div class="storage-dict-key ${currentDictKey === key ? 'active' : ''}"
             onclick="selectDictKey('${escapeHtml(key)}')"
             title="${escapeHtml(key)}">
            ${escapeHtml(key)}
        </div>
    `).join('');

    // Select first key if none selected
    if (keys.length > 0 && !currentDictKey) {
        selectDictKey(keys[0]);
    } else if (keys.length === 0) {
        document.getElementById('storage-current-key').textContent = 'No keys';
        document.getElementById('storage-dict-textarea').value = '';
        document.getElementById('storage-delete-key-btn').style.display = 'none';
    }
}

function selectDictKey(key) {
    currentDictKey = key;

    // Update active state in list
    document.querySelectorAll('.storage-dict-key').forEach(el => {
        el.classList.toggle('active', el.textContent.trim() === key);
    });

    // Update header
    document.getElementById('storage-current-key').textContent = key;
    document.getElementById('storage-delete-key-btn').style.display = 'block';

    // Load content
    const content = currentStorageData[key];
    const textarea = document.getElementById('storage-dict-textarea');

    if (typeof content === 'object') {
        textarea.value = JSON.stringify(content, null, 2);
    } else {
        textarea.value = content !== undefined ? String(content) : '';
    }

    storageDirty = false;
    updateDirtyIndicator();
}

function addDictKey() {
    if (currentStorageType !== 'dict') return;

    const newKey = prompt('Enter new key name:');
    if (!newKey || !newKey.trim()) return;

    const trimmedKey = newKey.trim();

    if (currentStorageData.hasOwnProperty(trimmedKey)) {
        alert('Key already exists');
        return;
    }

    // Add key locally
    currentStorageData[trimmedKey] = '';
    storageDirty = true;
    updateDirtyIndicator();

    // Re-render keys
    const keys = Object.keys(currentStorageData).sort();
    renderDictEditor(keys, currentStorageData);

    // Select the new key
    selectDictKey(trimmedKey);
}

function deleteCurrentKey() {
    if (!currentDictKey || currentStorageType !== 'dict') return;

    if (!confirm(`Delete key "${currentDictKey}"?`)) return;

    delete currentStorageData[currentDictKey];
    currentDictKey = null;
    storageDirty = true;
    updateDirtyIndicator();

    // Re-render keys
    const keys = Object.keys(currentStorageData).sort();
    renderDictEditor(keys, currentStorageData);
}

// =============================================================================
// List Editor
// =============================================================================

function renderListEditor(data) {
    hideAllStorageEditors();
    document.getElementById('storage-list-editor').style.display = 'flex';

    currentStorageData = [...data]; // Clone array

    renderListItems();
}

function renderListItems() {
    const container = document.getElementById('storage-list-items');

    container.innerHTML = currentStorageData.map((item, index) => `
        <div class="storage-list-item" data-index="${index}">
            <div class="storage-list-item-index">${index}</div>
            <div class="storage-list-item-content">
                <textarea
                    oninput="updateListItem(${index}, this.value)"
                    placeholder="Enter content...">${escapeHtml(typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item))}</textarea>
                <div class="storage-list-item-actions">
                    <button class="storage-list-item-btn" onclick="moveListItem(${index}, -1)" ${index === 0 ? 'disabled' : ''}>
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="18 15 12 9 6 15"></polyline>
                        </svg>
                        Up
                    </button>
                    <button class="storage-list-item-btn" onclick="moveListItem(${index}, 1)" ${index === currentStorageData.length - 1 ? 'disabled' : ''}>
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                        Down
                    </button>
                    <button class="storage-list-item-btn delete" onclick="deleteListItem(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        Delete
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

function addListItem() {
    currentStorageData.push('');
    storageDirty = true;
    updateDirtyIndicator();
    renderListItems();

    // Scroll to bottom
    const container = document.getElementById('storage-list-items');
    container.scrollTop = container.scrollHeight;

    // Focus the new textarea
    const textareas = container.querySelectorAll('textarea');
    if (textareas.length > 0) {
        textareas[textareas.length - 1].focus();
    }
}

function updateListItem(index, value) {
    currentStorageData[index] = value;
    storageDirty = true;
    updateDirtyIndicator();
}

function deleteListItem(index) {
    if (!confirm('Delete this item?')) return;

    currentStorageData.splice(index, 1);
    storageDirty = true;
    updateDirtyIndicator();
    renderListItems();
}

function moveListItem(index, direction) {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= currentStorageData.length) return;

    [currentStorageData[index], currentStorageData[newIndex]] =
    [currentStorageData[newIndex], currentStorageData[index]];

    storageDirty = true;
    updateDirtyIndicator();
    renderListItems();
}

// =============================================================================
// Text Editor
// =============================================================================

function renderTextEditor(data) {
    hideAllStorageEditors();
    document.getElementById('storage-text-editor').style.display = 'flex';

    document.getElementById('storage-text-textarea').value = data || '';
    storageDirty = false;
    updateDirtyIndicator();
}

// =============================================================================
// Save / Discard
// =============================================================================

function markStorageDirty() {
    // For dict editor, update the current key's value
    if (currentStorageType === 'dict' && currentDictKey) {
        const value = document.getElementById('storage-dict-textarea').value;

        // Try to parse as JSON, fall back to string
        try {
            currentStorageData[currentDictKey] = JSON.parse(value);
        } catch {
            currentStorageData[currentDictKey] = value;
        }
    }

    storageDirty = true;
    updateDirtyIndicator();
}

function updateDirtyIndicator() {
    const indicator = document.getElementById('storage-dirty-indicator');
    indicator.classList.toggle('show', storageDirty);
}

function saveStorageFile() {
    if (!currentStorageFile) return;

    // For text editor, get value from textarea
    let dataToSave = currentStorageData;
    if (currentStorageType === 'text') {
        dataToSave = document.getElementById('storage-text-textarea').value;
    }

    const btn = document.getElementById('storage-save-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-loading"><div class="storage-spinner" style="width:14px;height:14px;"></div>Saving...</span>';

    fetch('/storage/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file: currentStorageFile,
            type: currentStorageType,
            data: dataToSave
        })
    })
    .then(r => r.json())
    .then(result => {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-text">Save</span>';

        if (result.success) {
            storageDirty = false;
            updateDirtyIndicator();

            // Brief flash to indicate success
            btn.style.background = '#28a745';
            setTimeout(() => {
                btn.style.background = '';
            }, 500);
        } else {
            alert('Error saving: ' + (result.error || 'Unknown error'));
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-text">Save</span>';
        alert('Error saving file');
        console.error('Error:', err);
    });
}

function discardStorageChanges() {
    if (!storageDirty) return;

    if (!confirm('Discard all unsaved changes?')) return;

    // Reload the current file
    if (currentStorageFile) {
        loadStorageFile(currentStorageFile);
    }
}

// =============================================================================
// New File Creation
// =============================================================================

function showNewFilePrompt() {
    const fileName = prompt('Enter new file name (e.g., mydata.json):');
    if (!fileName || !fileName.trim()) return;

    const trimmedName = fileName.trim();
    const ext = trimmedName.split('.').pop().toLowerCase();

    // Determine type from extension
    let type = 'text';
    if (ext === 'json' || ext === 'yml' || ext === 'yaml' || ext === 'mp') {
        const fileType = prompt('Enter type (dict or list):');
        if (fileType === 'list') type = 'list';
        else type = 'dict';
    }

    // Create empty file
    let initialData = type === 'dict' ? {} : (type === 'list' ? [] : '');

    fetch('/storage/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file: trimmedName,
            type: type,
            data: initialData
        })
    })
    .then(r => r.json())
    .then(result => {
        if (result.success) {
            loadStorageFiles();
            setTimeout(() => loadStorageFile(trimmedName), 100);
        } else {
            alert('Error creating file: ' + (result.error || 'Unknown error'));
        }
    })
    .catch(err => {
        alert('Error creating file');
        console.error('Error:', err);
    });
}

// =============================================================================
// Utilities
// =============================================================================

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}
