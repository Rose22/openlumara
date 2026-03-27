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

// =============================================================================
// File Upload
// =============================================================================

const SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_IMAGE_SIZE = 20 * 1024 * 1024; // 20MB

async function handleFileUpload(event) {
    const file = event.target.files ? event.target.files[0] : event.dataTransfer.files[0];
    if (!file) return;

    if (event.target) {
        event.target.value = '';
    }

    // Check if it's an image
    const isImage = SUPPORTED_IMAGE_TYPES.includes(file.type);

    if (isImage) {
        // Handle image upload
        if (file.size > MAX_IMAGE_SIZE) {
            showNotification('Image too large. Maximum size is 20MB.', 'error');
            return;
        }

        try {
            const reader = new FileReader();
            const base64 = await new Promise((resolve, reject) => {
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            // Extract just the base64 data (remove data:image/xxx;base64, prefix)
            const base64Data = base64.split(',')[1];

            // Create preview in chat immediately
            const previewWrapper = document.createElement('div');
            previewWrapper.className = 'message-wrapper user animate-in';
            previewWrapper.setAttribute('role', 'article');
            previewWrapper.dataset.index = 'pending';

            const previewMsg = document.createElement('div');
            previewMsg.className = 'message user';

            const imgContainer = document.createElement('div');
            imgContainer.className = 'uploaded-image-container';

            const img = document.createElement('img');
            img.src = base64;
            img.className = 'uploaded-image-preview';
            img.alt = file.name;

            const caption = document.createElement('div');
            caption.className = 'uploaded-image-caption';
            caption.textContent = file.name;

            imgContainer.appendChild(img);
            imgContainer.appendChild(caption);
            previewMsg.appendChild(imgContainer);

            const userTs = document.createElement('span');
            userTs.className = 'timestamp timestamp-right';
            userTs.textContent = formatTime();
            previewMsg.appendChild(userTs);

            const actions = createActionButtons('user', 'pending', `[Image: ${file.name}]`, true);
            previewWrapper.appendChild(previewMsg);
            previewWrapper.appendChild(actions);

            chat.insertBefore(previewWrapper, typing);
            scrollToBottom();

            // Send to backend
            const response = await fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    content: base64Data,
                    mimetype: file.type,
                    is_image: true
                })
            });

            if (response.ok) {
                // Remove preview and sync with backend
                previewWrapper.remove();
                await syncMessages();
            } else {
                const error = await response.json();
                showNotification(error.error || 'Failed to upload image', 'error');
                previewWrapper.remove();
            }
        } catch (err) {
            console.error('Image upload failed:', err);
            showNotification('Failed to upload image', 'error');
        }
    } else {
        // Handle text/binary files (existing logic)
        try {
            const reader = new FileReader();
            const base64 = await new Promise((resolve, reject) => {
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            const response = await fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    content: base64,
                    mimetype: file.type,
                    is_image: false
                })
            });

            if (response.ok) {
                await syncMessages();
            }
        } catch (err) {
            console.error('Upload failed:', err);
        }
    }

    inputField.focus();
}
