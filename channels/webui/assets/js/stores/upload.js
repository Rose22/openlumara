const UPLOAD_STORE = {
    files: [],

    // drag & drop state: dragging drives the chat-window overlay,
    // _dragDepth counters child enter/leave so moving over inner elements
    // never flickers the overlay away
    dragging: false,
    _dragDepth: 0,

    init() {
        // an accidental file drop that misses the chat window must never
        // navigate the browser away from a live chat: swallow file drags
        // app-wide (the chat-window's own handlers run first via bubbling)
        window.addEventListener('dragover', (e) => {
            if (this.isFileDrag(e)) e.preventDefault();
        });
        window.addEventListener('drop', (e) => {
            if (this.isFileDrag(e)) e.preventDefault();
        });
    },

    isFileDrag(event) {
        return event.dataTransfer?.types?.includes('Files') ?? false;
    },

    onDragEnter(event) {
        if (!this.isFileDrag(event)) return;
        this._dragDepth += 1;
        this.dragging = true;
    },

    onDragOver(event) {
        if (!this.isFileDrag(event)) return;
        event.preventDefault(); // marks the window as an accepted drop target
    },

    onDragLeave(event) {
        if (!this.isFileDrag(event)) return;
        this._dragDepth = Math.max(0, this._dragDepth - 1);
        if (this._dragDepth === 0) this.dragging = false;
    },

    onDrop(event) {
        this._dragDepth = 0;
        this.dragging = false;
        if (!this.isFileDrag(event)) return; // let text drops keep native behavior (e.g. into the textarea)
        event.preventDefault();

        const files = event.dataTransfer?.files;
        if (files?.length) this.files.push(...files);
    },

    addFile(event) {
        this.files.push(...event.target.files);
        if (this.files.length === 0) return;
        event.target.value = "";
    },

    removeFile(index) {
        this.files.splice(index, 1);
    },

    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const bytes = new Uint8Array(reader.result);
                const CHUNK = 0x8000;
                let binary = '';
                for (let i = 0; i < bytes.length; i += CHUNK) {
                    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
                }
                resolve(btoa(binary));
            };
            reader.onerror = () => reject(reader.error);
            reader.readAsArrayBuffer(file);
        });
    },

    /**
     * Handle pasted images from clipboard
     * @param {ClipboardEvent} event - The paste event
     */
    async pasteImage(event) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (const item of items) {
            // Only handle image types
            if (item.type.startsWith('image/')) {
                const blob = item.getAsFile();
                if (blob) {
                    // Create a File object with a generated name
                    const timestamp = Date.now();
                    const ext = blob.type.split('/')[1] || 'png';
                    const file = new File([blob], `pasted-image-${timestamp}.${ext}`, {
                        type: blob.type
                    });
                    this.files.push(file);
                }
            }
        }
    },

    clear() {
        this.files = [];
        this.processed = [];
        this.dragging = false;
        this._dragDepth = 0;
    }
};
