// =============================================================================
// Drag and Drop
// =============================================================================

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    chat.addEventListener(eventName, () => {
        chat.classList.add('drag-over');
        dropOverlay.classList.add('active');
    }, false);
});

['dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, () => {
        chat.classList.remove('drag-over');
        dropOverlay.classList.remove('active');
    }, false);
});

chat.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
}, false);

document.body.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropOverlay.classList.add('active');
});

document.body.addEventListener('dragleave', (e) => {
    if (e.target === document.body || !e.relatedTarget) {
        dropOverlay.classList.remove('active');
    }
});

document.body.addEventListener('drop', (e) => {
    e.preventDefault();
    dropOverlay.classList.remove('active');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
});

// =============================================================================
// File Upload
// =============================================================================
const SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_IMAGE_SIZE = 20 * 1024 * 1024; // 20MB

async function handleFileUpload(event) {
    const filesList = event.target.files || event.dataTransfer.files;
    if (!filesList || filesList.length === 0) return;
    const rawFiles = Array.from(filesList);

    // 1. Create previews for all files in the batch
    const previewWrappers = [];
    for (const file of rawFiles) {
        const isImage = SUPPORTED_IMAGE_TYPES.includes(file.type);
        const previewWrapper = document.createElement('div');
        previewWrapper.className = 'message-wrapper user animate-in';
        previewWrapper.dataset.index = 'pending';

        const previewMsg = document.createElement('div');
        previewMsg.className = 'message user';

        if (isImage) {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'uploaded-image-container';
            const img = document.createElement('img');
            img.src = await new Promise((res, rej) => {
                const r = new FileReader();
                r.onload = () => res(r.result);
                r.onerror = rej;
                r.readAsDataURL(file);
            });
            img.className = 'uploaded-image-preview';
            const caption = document.createElement('div');
            caption.className = 'uploaded-image-caption';
            caption.textContent = file.name;
            imgContainer.appendChild(img);
            imgContainer.appendChild(caption);
            previewMsg.appendChild(imgContainer);
        } else {
            // Create preview in chat immediately
            const previewWrapper = document.createElement('div');
            previewWrapper.className = 'message-wrapper user animate-in';
            previewWrapper.dataset.index = 'pending';

            const previewMsg = document.createElement('div');
            previewMsg.className = 'message user';

            // NEW: Consistent preview style for the pending state
            const fileContainer = document.createElement('div');
            fileContainer.className = 'file-preview-container';
            fileContainer.innerHTML = `
            <div class="file-preview">
            <span class="file-icon">📄</span>
            <span class="file-name">${escapeHtml(file.name)}</span>
            </div>
            `;
            previewMsg.appendChild(fileContainer);
        }

        const userTs = document.createElement('span');
        userTs.className = 'timestamp timestamp-right';
        userTs.textContent = formatTime();
        previewMsg.appendChild(userTs);

        const actions = createActionButtons('user', 'pending', file.name, true);
        previewWrapper.appendChild(previewMsg);
        previewWrapper.appendChild(actions);

        chat.insertBefore(previewWrapper, typing);
        previewWrappers.push(previewWrapper);
    }

    scrollToBottom();

    // 2. Prepare data and send all files to backend
    try {
        const filePromises = rawFiles.map(async (file) => {
            const isImage = SUPPORTED_IMAGE_TYPES.includes(file.type);
            const reader = new FileReader();
            const base64 = await new Promise((resolve, reject) => {
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            return {
                filename: file.name,
                content: base64.split(',')[1],
                                          mimetype: file.type,
                                          is_image: isImage
            };
        });

        const filesData = await Promise.all(filePromises);

        const response = await fetch('/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: filesData })
        });

        if (response.ok) {
            previewWrappers.forEach(w => w.remove());
            await syncMessages();
        } else {
            const error = await response.json();
            showNotification(error.error || 'Failed to upload files', 'error');
            previewWrappers.forEach(w => w.remove());
        }
    } catch (err) {
        console.error('Upload failed:', err);
        showNotification('Failed to upload files', 'error');
        previewWrappers.forEach(w => w.remove());
    }

    inputField.focus();
}
