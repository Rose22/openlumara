// =============================================================================
// Storage Editor
// =============================================================================

let storageFiles = [];
let currentStorageFile = null;
let currentStorageType = null;
let currentStorageData = null;
let currentDictKey = null;
let storageDirty = false;

// JSON drill-down state
let jsonPath = [];
let jsonRootData = null;
let jsonEditingKey = null;
let jsonTreeHidden = false;

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
    document.querySelectorAll('.storage-file-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.storage-file-name').title === filePath);
    });

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
// Dict Editor with JSON Drill-Down
// =============================================================================

function getDictContentContainer() {
    return document.querySelector('.storage-dict-content');
}

function renderDictEditor(keys, data) {
    hideAllStorageEditors();
    document.getElementById('storage-dict-editor').style.display = 'flex';

    // Reset navigation state
    jsonPath = [];
    jsonRootData = null;
    currentDictKey = null;
    jsonEditingKey = null;

    renderDictKeysList(keys, data);

    // Clear the content area
    document.getElementById('storage-current-key').textContent = 'Select a key';
    document.getElementById('storage-dict-textarea').value = '';
    document.getElementById('storage-delete-key-btn').style.display = 'none';

    // Hide textarea and navigator
    document.getElementById('storage-dict-textarea').style.display = 'none';
    const navigator = document.getElementById('storage-json-navigator');
    if (navigator) navigator.style.display = 'none';

    // Remove empty state wrapper if it exists
    const emptyWrapper = document.getElementById('storage-json-empty-wrapper');
    if (emptyWrapper) emptyWrapper.remove();
}

function renderDictKeysList(keys, data) {
    const keysList = document.getElementById('storage-dict-keys');
    keysList.innerHTML = keys.map(key => {
        const value = data[key];
        const typeInfo = getValueTypeInfo(value);

        return `
        <div class="storage-dict-key ${currentDictKey === key ? 'active' : ''}"
        onclick="selectDictKey('${escapeHtml(key)}')">
        <span class="storage-dict-key-name" title="${escapeHtml(key)}">${escapeHtml(key)}</span>
        <span class="storage-dict-key-type ${typeInfo.class}">${typeInfo.label}</span>
        </div>
        `;
    }).join('');
}

function getValueTypeInfo(value) {
    if (value === null) return { label: 'null', class: 'type-null', isPrimitive: true };
    if (value === undefined) return { label: 'undefined', class: 'type-undefined', isPrimitive: true };
    if (Array.isArray(value)) return { label: `[${value.length}]`, class: 'type-array', isPrimitive: false };
    if (typeof value === 'object') return { label: `{${Object.keys(value).length}}`, class: 'type-object', isPrimitive: false };
    if (typeof value === 'string') {
        const lines = (value.match(/\n/g) || []).length;
        const label = lines > 0 ? `string (${lines + 1} lines)` : 'string';
        return { label, class: 'type-string', isPrimitive: true };
    }
    if (typeof value === 'number') return { label: 'number', class: 'type-number', isPrimitive: true };
    if (typeof value === 'boolean') return { label: 'boolean', class: 'type-boolean', isPrimitive: true };
    return { label: typeof value, class: '', isPrimitive: true };
}

function selectDictKey(key) {
    currentDictKey = key;
    jsonPath = [];
    jsonRootData = currentStorageData[key];
    jsonEditingKey = null;

    // Update active state in list
    document.querySelectorAll('.storage-dict-key').forEach(el => {
        const keyName = el.querySelector('.storage-dict-key-name');
        el.classList.toggle('active', keyName && keyName.textContent === key);
    });

    // Update header
    document.getElementById('storage-current-key').textContent = key;
    document.getElementById('storage-delete-key-btn').style.display = 'block';

    const value = currentStorageData[key];
    const typeInfo = getValueTypeInfo(value);

    if (!typeInfo.isPrimitive) {
        // Show JSON navigator for complex types
        renderJsonNavigator();
    } else {
        // Show simple editor for primitive types
        hideJsonNavigator();
        showPrimitiveEditor(value);
    }

    storageDirty = false;
    updateDirtyIndicator();
}

// =============================================================================
// JSON Navigator (Two-Column Drill-Down)
// =============================================================================

function renderJsonNavigator() {
    const container = getDictContentContainer();
    if (!container) return;

    // Create navigator if it doesn't exist
    let navigator = document.getElementById('storage-json-navigator');
    if (!navigator) {
        navigator = document.createElement('div');
        navigator.id = 'storage-json-navigator';
        navigator.className = 'storage-json-navigator';
        container.appendChild(navigator);
    }

    navigator.style.display = 'flex';

    // Hide the textarea
    const textarea = document.getElementById('storage-dict-textarea');
    textarea.style.display = 'none';

    // Build the navigator HTML
    navigator.innerHTML = `
    <div class="storage-json-breadcrumb" id="storage-json-breadcrumb"></div>
    <div class="storage-json-columns ${jsonTreeHidden ? 'tree-hidden' : ''}" id="storage-json-columns">
    <div class="storage-json-tree" id="storage-json-tree"></div>
    <div class="storage-json-editor" id="storage-json-editor">
    <div class="storage-json-empty-state" id="storage-json-empty-state">
    Select an item to edit
    </div>
    </div>
    </div>
    `;

    // Render breadcrumb and tree
    renderBreadcrumb();
    renderJsonTree();
    clearJsonEditor();
}

function hideJsonNavigator() {
    const navigator = document.getElementById('storage-json-navigator');
    if (navigator) navigator.style.display = 'none';

    const textarea = document.getElementById('storage-dict-textarea');
    textarea.style.display = 'block';
}

function showJsonEmptyState(message) {
    hideJsonNavigator();
    const textarea = document.getElementById('storage-dict-textarea');
    textarea.style.display = 'none';

    const container = getDictContentContainer();
    if (!container) return;

    // Create or update empty state
    let emptyState = document.getElementById('storage-json-empty-wrapper');
    if (!emptyState) {
        emptyState = document.createElement('div');
        emptyState.id = 'storage-json-empty-wrapper';
        emptyState.className = 'storage-json-empty-wrapper';
        container.appendChild(emptyState);
    }
    emptyState.innerHTML = `<div class="storage-json-empty-state">${message}</div>`;
    emptyState.style.display = 'flex';
}

function renderBreadcrumb() {
    const breadcrumb = document.getElementById('storage-json-breadcrumb');
    if (!breadcrumb) return;

    let html = `<span class="storage-breadcrumb-item root" onclick="navigateToPath(-1)">
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
    </svg>
    root
    </span>`;

    jsonPath.forEach((segment, index) => {
        const isLast = index === jsonPath.length - 1;
        html += `<span class="storage-breadcrumb-sep">›</span>`;
        html += `<span class="storage-breadcrumb-item ${isLast ? 'active' : ''}"
        onclick="navigateToPath(${index})">${escapeHtml(String(segment))}</span>`;
    });

    breadcrumb.innerHTML = html;
}

function navigateToPath(index) {
    if (index === -1) {
        jsonPath = [];
        jsonEditingKey = null;
    } else {
        jsonPath = jsonPath.slice(0, index + 1);
        jsonEditingKey = null;
    }

    renderBreadcrumb();
    renderJsonTree();
    clearJsonEditor();
    markStorageDirty();
}

function getDataAtPath(path = jsonPath) {
    let data = jsonRootData;
    for (const segment of path) {
        if (data === null || data === undefined) return undefined;
        data = data[segment];
    }
    return data;
}

function setDataAtPath(value, path = jsonPath) {
    let data = jsonRootData;
    for (let i = 0; i < path.length - 1; i++) {
        data = data[path[i]];
    }
    if (path.length > 0) {
        data[path[path.length - 1]] = value;
    } else {
        jsonRootData = value;
        if (currentDictKey) {
            currentStorageData[currentDictKey] = value;
        }
    }
}

function renderJsonTree() {
    const tree = document.getElementById('storage-json-tree');
    if (!tree) return;

    const currentData = getDataAtPath();

    if (currentData === null || currentData === undefined) {
        tree.innerHTML = `<div class="storage-json-empty-state">null or undefined</div>`;
        return;
    }

    if (Array.isArray(currentData)) {
        renderArrayTree(currentData, tree);
    } else if (typeof currentData === 'object') {
        renderObjectTree(currentData, tree);
    } else {
        tree.innerHTML = `<div class="storage-json-empty-state">Primitive value</div>`;
        showInJsonEditor(currentData, null);
    }
}

function toggleJsonTree() {
    jsonTreeHidden = !jsonTreeHidden;
    const columns = document.getElementById('storage-json-columns');
    if (columns) {
        columns.classList.toggle('tree-hidden', jsonTreeHidden);
    }

    // Update button icon
    const btn = document.querySelector('.storage-json-toggle-btn');
    if (btn) {
        btn.innerHTML = jsonTreeHidden
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
        btn.title = jsonTreeHidden ? 'Show keys' : 'Hide keys';
    }
}

function renderArrayTree(arr, container) {
    if (arr.length === 0) {
        container.innerHTML = `
        <div class="storage-json-empty-state">
        Empty array
        <button class="storage-json-add-btn" onclick="addJsonItem()">+ Add Item</button>
        </div>
        `;
        return;
    }

    let html = `<div class="storage-json-tree-header">
    <span>Array (${arr.length} items)</span>
    <button class="storage-json-add-btn" onclick="addJsonItem()">+ Add</button>
    </div>`;

    html += '<div class="storage-json-tree-list">';
    arr.forEach((item, index) => {
        const typeInfo = getValueTypeInfo(item);
        const preview = getPreview(item);
        const isSelected = jsonEditingKey === index;

        html += `
        <div class="storage-json-tree-item ${isSelected ? 'selected' : ''}"
        onclick="selectJsonItem(${index}, event)">
        <span class="storage-json-tree-index">${index}</span>
        <span class="storage-json-tree-preview">${escapeHtml(preview)}</span>
        <span class="storage-json-tree-type ${typeInfo.class}">${typeInfo.label}</span>
        ${!typeInfo.isPrimitive ? `<span class="storage-json-tree-drill" onclick="event.stopPropagation(); drillInto(${index})">→</span>` : ''}
        </div>
        `;
    });
    html += '</div>';

    container.innerHTML = html;
}

function renderObjectTree(obj, container) {
    const keys = Object.keys(obj);

    if (keys.length === 0) {
        container.innerHTML = `
        <div class="storage-json-empty-state">
        Empty object
        <button class="storage-json-add-btn" onclick="addJsonItem()">+ Add Key</button>
        </div>
        `;
        return;
    }

    let html = `<div class="storage-json-tree-header">
    <span>Object (${keys.length} keys)</span>
    <button class="storage-json-add-btn" onclick="addJsonItem()">+ Add</button>
    </div>`;

    html += '<div class="storage-json-tree-list">';
    keys.forEach(key => {
        const item = obj[key];
        const typeInfo = getValueTypeInfo(item);
        const preview = getPreview(item);
        const isSelected = jsonEditingKey === key;

        html += `
        <div class="storage-json-tree-item ${isSelected ? 'selected' : ''}"
        onclick="selectJsonItem('${escapeHtml(key)}', event)">
        <span class="storage-json-tree-key">${escapeHtml(key)}</span>
        <span class="storage-json-tree-preview">${escapeHtml(preview)}</span>
        <span class="storage-json-tree-type ${typeInfo.class}">${typeInfo.label}</span>
        ${!typeInfo.isPrimitive ? `<span class="storage-json-tree-drill" onclick="event.stopPropagation(); drillInto('${escapeHtml(key)}')">→</span>` : ''}
        </div>
        `;
    });
    html += '</div>';

    container.innerHTML = html;
}

function getPreview(value, maxLength = 30) {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';

    if (typeof value === 'string') {
        let truncated = value.length > maxLength ? value.slice(0, maxLength) + '…' : value;
        truncated = truncated.replace(/\n/g, '⏎');
        return `"${truncated}"`;
    }

    if (Array.isArray(value)) {
        return `[${value.length}]`;
    }

    if (typeof value === 'object') {
        const keys = Object.keys(value);
        return `{${keys.length}}`;
    }

    return String(value);
}

function selectJsonItem(key, event) {
    jsonEditingKey = key;

    // Update selection state
    document.querySelectorAll('.storage-json-tree-item').forEach(el => {
        el.classList.remove('selected');
    });
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('selected');
    }

    // Get the value and show in editor
    const currentData = getDataAtPath();
    const value = currentData[key];
    showInJsonEditor(value, key);
}

function drillInto(key) {
    jsonPath.push(key);
    jsonEditingKey = null;

    renderBreadcrumb();
    renderJsonTree();
    clearJsonEditor();
}

function showInJsonEditor(value, key) {
    const editor = document.getElementById('storage-json-editor');
    if (!editor) return;

    const typeInfo = getValueTypeInfo(value);
    const keyLabel = key !== null ? escapeHtml(String(key)) : 'value';

    // Toggle button icon based on state
    const toggleIcon = jsonTreeHidden
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>`;

    let html = `
    <div class="storage-json-editor-header">
    <span class="storage-json-editor-key">${keyLabel}</span>
    <span class="storage-json-editor-type ${typeInfo.class}">${typeInfo.label}</span>
    <div class="storage-json-editor-actions">
    <button class="storage-json-toggle-btn" onclick="toggleJsonTree()" title="${jsonTreeHidden ? 'Show keys' : 'Hide keys'}">
    ${toggleIcon}
    </button>
    <button class="storage-json-delete-btn" onclick="deleteJsonItem('${keyLabel}')" title="Delete">
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="3 6 5 6 21 6"></polyline>
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
    </svg>
    </button>
    </div>
    </div>
    `;

    if (typeInfo.isPrimitive) {
        if (typeof value === 'string') {
            const displayValue = value.replace(/\\n/g, '\n');
            const lines = (displayValue.match(/\n/g) || []).length + 1;
            const textareaHeight = Math.max(100, Math.min(400, lines * 20));

            html += `
            <textarea class="storage-json-textarea"
            style="min-height: ${textareaHeight}px"
            oninput="updateJsonValue('${keyLabel}', this.value)"
            placeholder="Enter string value...">${escapeHtml(displayValue)}</textarea>
            <div class="storage-json-editor-hint">
            Newlines are displayed as actual line breaks
            </div>
            `;
        } else if (typeof value === 'number') {
            html += `
            <input type="number" class="storage-json-input"
            value="${value}"
            oninput="updateJsonValue('${keyLabel}', parseFloat(this.value))"
            step="any">
            `;
        } else if (typeof value === 'boolean') {
            html += `
            <div class="storage-json-boolean">
            <button class="storage-json-bool-btn ${value === true ? 'active' : ''}"
            onclick="updateJsonValue('${keyLabel}', true)">true</button>
            <button class="storage-json-bool-btn ${value === false ? 'active' : ''}"
            onclick="updateJsonValue('${keyLabel}', false)">false</button>
            </div>
            `;
        } else if (value === null) {
            html += `
            <div class="storage-json-null">
            <span>null</span>
            <button class="storage-json-bool-btn" onclick="updateJsonValue('${keyLabel}', '')">Set to empty string</button>
            </div>
            `;
        }
    } else {
        html += `
        <div class="storage-json-complex">
        <p>This ${typeInfo.label} contains nested data.</p>
        <button class="storage-json-drill-btn" onclick="drillInto('${keyLabel}')">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        Open ${typeInfo.label}
        </button>
        </div>
        `;
    }

    editor.innerHTML = html;
}

function clearJsonEditor() {
    const editor = document.getElementById('storage-json-editor');
    if (editor) {
        editor.innerHTML = `<div class="storage-json-empty-state">Select an item to edit</div>`;
    }
}

function showPrimitiveEditor(value) {
    const emptyWrapper = document.getElementById('storage-json-empty-wrapper');
    if (emptyWrapper) emptyWrapper.style.display = 'none';

    const textarea = document.getElementById('storage-dict-textarea');
    textarea.style.display = 'block';

    if (typeof value === 'string') {
        textarea.value = value.replace(/\\n/g, '\n');
    } else {
        textarea.value = value !== null && value !== undefined ? String(value) : '';
    }
}

function updateJsonValue(key, newValue) {
    if (typeof newValue === 'string') {
        newValue = newValue.replace(/\n/g, '\\n');
    }

    const currentData = getDataAtPath();
    if (currentData !== null && currentData !== undefined) {
        currentData[key] = newValue;
        markStorageDirty();

        renderJsonTree();

        // Re-select the item
        const items = document.querySelectorAll('.storage-json-tree-item');
        items.forEach(item => {
            const keyEl = item.querySelector('.storage-json-tree-key, .storage-json-tree-index');
            if (keyEl && (keyEl.textContent === String(key) || keyEl.textContent === key)) {
                item.classList.add('selected');
            }
        });
    }
}

function addJsonItem() {
    const currentData = getDataAtPath();
    if (currentData === null || currentData === undefined) return;

    if (Array.isArray(currentData)) {
        currentData.push('');
        markStorageDirty();
        renderJsonTree();
        selectJsonItem(currentData.length - 1, null);
    } else if (typeof currentData === 'object') {
        const newKey = prompt('Enter new key name:');
        if (!newKey || !newKey.trim()) return;

        const trimmedKey = newKey.trim();
        if (currentData.hasOwnProperty(trimmedKey)) {
            alert('Key already exists');
            return;
        }

        currentData[trimmedKey] = '';
        markStorageDirty();
        renderJsonTree();
        selectJsonItem(trimmedKey, null);
    }
}

function deleteJsonItem(key) {
    if (!confirm(`Delete "${key}"?`)) return;

    const currentData = getDataAtPath();
    if (currentData === null || currentData === undefined) return;

    if (Array.isArray(currentData)) {
        currentData.splice(key, 1);
    } else if (typeof currentData === 'object') {
        delete currentData[key];
    }

    jsonEditingKey = null;
    markStorageDirty();
    renderJsonTree();
    clearJsonEditor();
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

    currentStorageData[trimmedKey] = '';
    storageDirty = true;
    updateDirtyIndicator();

    const keys = Object.keys(currentStorageData).sort();
    renderDictKeysList(keys, currentStorageData);
    selectDictKey(trimmedKey);
}

function deleteCurrentKey() {
    if (!currentDictKey || currentStorageType !== 'dict') return;

    if (!confirm(`Delete key "${currentDictKey}"?`)) return;

    delete currentStorageData[currentDictKey];
    currentDictKey = null;
    jsonPath = [];
    jsonRootData = null;
    jsonEditingKey = null;
    storageDirty = true;
    updateDirtyIndicator();

    const keys = Object.keys(currentStorageData).sort();
    renderDictEditor(keys, currentStorageData);
}

// =============================================================================
// List Editor
// =============================================================================

function renderListEditor(data) {
    hideAllStorageEditors();
    document.getElementById('storage-list-editor').style.display = 'flex';

    currentStorageData = [...data];
    renderListItems();
}

function renderListItems() {
    const container = document.getElementById('storage-list-items');

    container.innerHTML = currentStorageData.map((item, index) => {
        const typeInfo = getValueTypeInfo(item);
        const displayValue = typeof item === 'string' ? item.replace(/\\n/g, '\n') :
        (typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item));

        return `
        <div class="storage-list-item" data-index="${index}">
        <div class="storage-list-item-index">${index}</div>
        <div class="storage-list-item-content">
        <textarea
        oninput="updateListItem(${index}, this.value)"
        placeholder="Enter content...">${escapeHtml(displayValue)}</textarea>
        <div class="storage-list-item-type ${typeInfo.class}">${typeInfo.label}</div>
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
        `;
    }).join('');
}

function addListItem() {
    currentStorageData.push('');
    storageDirty = true;
    updateDirtyIndicator();
    renderListItems();

    const container = document.getElementById('storage-list-items');
    container.scrollTop = container.scrollHeight;

    const textareas = container.querySelectorAll('textarea');
    if (textareas.length > 0) {
        textareas[textareas.length - 1].focus();
    }
}

function updateListItem(index, value) {
    const storedValue = value.replace(/\n/g, '\\n');

    try {
        currentStorageData[index] = JSON.parse(storedValue);
    } catch {
        currentStorageData[index] = storedValue;
    }

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
    storageDirty = true;
    updateDirtyIndicator();
}

function updateDirtyIndicator() {
    const indicator = document.getElementById('storage-dirty-indicator');
    indicator.classList.toggle('show', storageDirty);
}

function saveStorageFile() {
    if (!currentStorageFile) return;

    if (currentStorageType === 'dict') {
        const textarea = document.getElementById('storage-dict-textarea');
        if (textarea && textarea.style.display !== 'none' && currentDictKey) {
            const value = textarea.value;
            const storedValue = value.replace(/\n/g, '\\n');
            currentStorageData[currentDictKey] = storedValue;
        }
    }

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

    let type = 'text';
    if (ext === 'json' || ext === 'yml' || ext === 'yaml' || ext === 'mp') {
        const fileType = prompt('Enter type (dict or list):');
        if (fileType === 'list') type = 'list';
        else type = 'dict';
    }

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
