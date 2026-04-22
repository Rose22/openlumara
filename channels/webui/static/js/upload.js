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
    // Prevent file upload overlay when dragging a chat item
    if (window.isDraggingChat) {
        e.preventDefault();
        return;
    }
    e.preventDefault();
    dropOverlay.classList.add('active');
});

document.body.addEventListener('dragleave', (e) => {
    if (e.target === document.body || !e.relatedTarget) {
        dropOverlay.classList.remove('active');
    }
});

document.body.addEventListener('drop', (e) => {
    // Prevent file upload when dropping a chat item
    if (window.isDraggingChat) {
        e.preventDefault();
        return;
    }
    e.preventDefault();
    dropOverlay.classList.remove('active');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
});

// =============================================================================
// File Upload (Modified for Queuing)
// =============================================================================
const SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_IMAGE_SIZE = 20 * 1024 * 1024; // 20MB

// Global queue to hold files and their UI wrappers until 'send' is clicked
window.upload_queue = {
    files: [],      // Stores the content objects for the API payload
    wrappers: []    // Stores the DOM elements to remove them later
};

/**
 * Updates the visual queue near the input bar
 */
window.updateUploadQueueUI = function() {
    const container = document.getElementById('upload-queue-container');
    if (!container) return;

    if (window.upload_queue.files.length === 0) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }

    container.classList.remove('hidden');
    container.innerHTML = ''; // Clear current view

    const queueList = document.createElement('div');
    queueList.className = 'upload-queue-list';

    window.upload_queue.files.forEach((fileObj, index) => {
        const item = document.createElement('div');
        item.className = 'upload-queue-item';
        item.innerHTML = `
        <span class="queue-file-icon">📄</span>
        <span class="queue-file-name">${escapeHtml(fileObj.name)}</span>
        <button class="delete-queue-item" aria-label="Remove file">&times;</button>
        `;

        // Add event listener for the delete button
        const deleteBtn = item.querySelector('.delete-queue-item');
        deleteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();

            // 1. Remove the pending message wrapper from the chat DOM if it exists
            const wrapper = window.upload_queue.wrappers[index];
            if (wrapper && wrapper.parentNode) {
                wrapper.remove();
            }

            // 2. Remove from the data arrays
            window.upload_queue.files.splice(index, 1);
            window.upload_queue.wrappers.splice(index, 1);

            // 3. Re-render the queue UI
            window.updateUploadQueueUI();
        });

        queueList.appendChild(item);
    });

    container.appendChild(queueList);
};

async function handleFileUpload(event) {
    try {
        const filesList = event.target.files || event.dataTransfer.files;
        if (!filesList || filesList.length === 0) return;
        const rawFiles = Array.from(filesList);

        const previewWrappers = [];

        for (const file of rawFiles) {
            const isImage = SUPPORTED_IMAGE_TYPES.includes(file.type);
            const previewWrapper = document.createElement('div');
            previewWrapper.className = 'message-wrapper user animate-in';
            previewWrapper.dataset.index = 'pending';

            const previewMsg = document.createElement('div');
            previewMsg.className = 'message user';

            let contentPart = {};

            if (isImage) {
                // Image processing
                const imgContainer = document.createElement('div');
                imgContainer.className = 'uploaded-image-container';
                const img = document.createElement('img');
                const imageDataUrl = await new Promise((res, rej) => {
                    const r = new FileReader();
                    r.onload = () => res(r.result);
                    r.onerror = () => rej(new Error('Failed to read image file'));
                    r.readAsDataURL(file);
                });

                img.src = imageDataUrl;
                img.className = 'uploaded-image-preview';

                // Resize/Compress logic for the preview
                const imgObj = new Image();
                imgObj.src = imageDataUrl;
                await new Promise(r => imgObj.onload = r);

                const maxDimension = 512;
                let width = imgObj.width;
                let height = imgObj.height;

                if (width > maxDimension || height > maxDimension) {
                    if (width > height) {
                        height = (maxDimension / width) * height;
                        width = maxDimension;
                    } else {
                        width = (maxDimension / height) * width;
                        height = maxDimension;
                    }
                }
                img.style.width = `${width}px`;
                img.style.height = `${height}px`;

                // Prepare the parts for the final payload
                contentPart = [
                    {
                        type: "text",
                        text: `[Image: ${file.name}]`
                    },
                    {
                        type: "image_url",
                        image_url: { url: imageDataUrl }
                    }
                ];
            } else {
                // Text file processing
                const content = await new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result);
                    reader.onerror = () => resolve('');
                    reader.readAsText(file);
                });

                contentPart = {
                    type: "text",
                    text: `[File: ${file.name}]\n${content}`
                };
            }

            window.upload_queue.files.push({
                content: contentPart,
                name: file.name
            });
            window.upload_queue.wrappers.push(previewWrapper);
        }

        window.updateUploadQueueUI();
        scrollToBottom();
        inputField.focus();
    } catch (err) {
        console.error('Failed to process uploaded files:', err);
        alert('Failed to process uploaded files. Please try again.');
    }
}
