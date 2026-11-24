const UPLOAD_STORE = {
    files: [],

    addFile(event) {
        this.files.push(...event.target.files);
        if (this.files.length === 0) return;
        event.target.value = "";
    },

    removeFile(index) {
        this.files.splice(index, 1);
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
    // ArrayBuffer + chunked btoa instead of a data-URL: the old path held the
    // full data URL AND its split() copy alive per file (~2.7x file size of
    // transient garbage); this touches the bytes once and keeps only the
    // base64 result. now also rejects on read failure - the old promise hung
    // forever, freezing send with the draft already cleared.
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
    }
};
