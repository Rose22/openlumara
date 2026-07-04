// =============================================================================
// Drag and Drop
// =============================================================================

const SUPPORTED_FILE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'];

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
    }, false);
});

['dragenter', 'dragover'].forEach(eventName => {
    chat.addEventListener(eventName, (e) => {
        e.preventDefault();
        if (!window.isDraggingChat) {
            chat.classList.add('drag-over');
            dropOverlay.classList.add('active');
        }
    }, false);
});

['dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, (e) => {
        e.preventDefault();
        chat.classList.remove('drag-over');
        dropOverlay.classList.remove('active');
    }, false);
});

chat.addEventListener('drop', (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
}, false);

document.body.addEventListener('dragover', (e) => {
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
const MAX_PDF_SIZE = 25 * 1024 * 1024; // 25MB

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
        const iconClass = fileObj.is_pdf ? 'queue-file-icon pdf' : (fileObj.is_image ? 'queue-file-icon image' : 'queue-file-icon');
        const iconChar = fileObj.is_pdf ? '\uD83D\uDCC4' : '\uD83D\uDDBC\uFE0F';
        item.innerHTML = `
        <span class="${iconClass}">${iconChar}</span>
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

            // 4. Clear the file input so the same file can be re-selected
            const fileInput = document.getElementById('file-input');
            if (fileInput) {
                fileInput.value = '';
            }
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
            const isPdf = file.type === 'application/pdf';

            if (!isImage && !isPdf && !file.type.startsWith('text/')) {
                continue;
            }

            if (isPdf && file.size > MAX_PDF_SIZE) {
                console.warn(`PDF ${file.name} exceeds ${MAX_PDF_SIZE / 1024 / 1024}MB limit`);
                continue;
            }

            const previewWrapper = document.createElement('div');
            previewWrapper.className = 'message-wrapper user animate-in';
            previewWrapper.dataset.index = 'pending';

            const previewMsg = document.createElement('div');
            previewMsg.className = 'message user';

            let contentPart = {};
            let fileMeta = {};

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

                imgContainer.appendChild(img);
                previewMsg.appendChild(imgContainer);
                previewWrapper.appendChild(previewMsg);
                previewWrappers.push(previewWrapper);

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
                fileMeta = { is_image: true };
            } else if (isPdf) {
                // PDF processing — extract text via backend
                const pdfBase64 = await new Promise((res, rej) => {
                    const r = new FileReader();
                    r.onload = () => {
                        const parts = r.result.split(',');
                        res(parts[1] || r.result);
                    };
                    r.onerror = () => rej(new Error('Failed to read PDF file'));
                    r.readAsDataURL(file);
                });

                const pdfContainer = document.createElement('div');
                pdfContainer.className = 'uploaded-pdf-container';
                const pdfIcon = document.createElement('div');
                pdfIcon.className = 'uploaded-pdf-icon';
                pdfIcon.innerHTML = '&#128196;';
                const pdfName = document.createElement('div');
                pdfName.className = 'uploaded-image-caption';
                pdfName.textContent = file.name;
                pdfContainer.appendChild(pdfIcon);
                pdfContainer.appendChild(pdfName);
                previewMsg.appendChild(pdfContainer);
                previewWrapper.appendChild(previewMsg);
                previewWrappers.push(previewWrapper);

                let pdfText = "[PDF could not be parsed]";
                let pdfFallback = null;
                try {
                    const parseResp = await fetch('/parse-pdf', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content: pdfBase64, filename: file.name })
                    });
                    const parseData = await parseResp.json();
                    if (parseData.success) {
                        if (parseData.mode === 'pdf_image' && parseData.pdf_base64) {
                            pdfFallback = parseData.pdf_base64;
                            pdfText = `[PDF: ${file.name} (${parseData.pages} pages, sent as image for OCR)]`;
                        } else if (parseData.text) {
                            pdfText = parseData.text;
                        }
                    }
                } catch (e) {
                    console.error('Failed to parse PDF:', e);
                }

                if (pdfFallback) {
                    contentPart = [
                        { type: "text", text: pdfText },
                        { type: "image_url", image_url: { url: `data:application/pdf;base64,${pdfFallback}` } }
                    ];
                } else {
                    contentPart = {
                        type: "text",
                        text: `[PDF: ${file.name} (${pdfText.length} chars extracted)]\n${pdfText}`
                    };
                }
                fileMeta = { is_pdf: true };
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
                fileMeta = {};
            }

            window.upload_queue.files.push({
                content: contentPart,
                name: file.name,
                is_image: fileMeta.is_image || false,
                is_pdf: fileMeta.is_pdf || false
            });
            window.upload_queue.wrappers.push(previewWrapper);
        }

        window.updateUploadQueueUI();
        scrollToBottom();

        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.value = '';
        }

        inputField.focus();
    } catch (err) {
        console.error('Failed to process uploaded files:', err);
        alert('Failed to process uploaded files. Please try again.');
    }
}


// =============================================================================
// Paste Support
// =============================================================================

document.addEventListener('paste', async (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    const files = [];
    for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
            files.push(items[i].getAsFile());
        }
    }

    if (files.length > 0) {
        e.preventDefault();
        handleFileUpload({
            target: { files: files }
        });
    }
});
