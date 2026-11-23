// Settings: background image behind the chat (or the whole page).
// The image itself lives in IndexedDB (localStorage would choke on a real
// photo); the toggles and slider values are plain localStorage keys, in the
// same spirit as AUDIO_STORE. apply() builds a #bg-layer element carrying
// the picture (see css/base/background.css for its base styles).
BACKGROUND_STORE = {
    enabled: localStorage.getItem('bgImageEnabled') === 'true',
    mode: localStorage.getItem('bgImageMode') === 'page' ? 'page' : 'chat',
    brightness: parseInt(localStorage.getItem('bgBrightness'), 10) || 100,
    blur: parseInt(localStorage.getItem('bgBlur'), 10) || 0,
    dataUrl: null,

    _db: null,

    async init() {
        try {
            this._db = await this._openDb();
            this.dataUrl = await this._idb('readonly') || null;
        } catch (e) {
            console.warn('Background image storage unavailable:', e);
        }
        this.apply();
    },

    // The image is assigned directly onto a real #bg-layer element:
    // a multi-MB data URL stuffed into an inline custom property gets
    // silently dropped by the CSS parser, but style.backgroundImage
    // assignment handles it fine (and shows up in Elements for debugging).
    apply() {
        const root = document.documentElement;
        const show = this.enabled && !!this.dataUrl;

        root.classList.toggle('has-bg', show);
        root.classList.toggle('bg-page', this.mode === 'page');
        root.classList.toggle('bg-chat', this.mode === 'chat');

        // chat mode: layer lives inside #chat-window (clipped to it).
        // page mode: layer is body-level and position:fixed (see background.css)
        // so it spans the viewport without being reparented into the app's
        // flex containers, which must stay untouched.
        let layer = document.getElementById('bg-layer');
        const host = this.mode === 'page'
            ? document.body
            : document.getElementById('chat-window');

        if (!show || !host) {
            if (layer) layer.remove();
            return;
        }

        if (!layer) {
            layer = document.createElement('div');
            layer.id = 'bg-layer';
            layer.setAttribute('aria-hidden', 'true');
        }
        // re-prepended when the mode (and with it the host) changes
        if (layer.parentElement !== host) host.prepend(layer);

        layer.style.backgroundImage = `url("${this.dataUrl}")`;
        layer.style.filter = `brightness(${this.brightness / 100}) blur(${this.blur}px)`;
        // bleed past the edges so blur never pulls in transparent borders
        layer.style.inset = (this.blur * -3) + 'px';
    },

    toggle() {
        this.enabled = !this.enabled;
        localStorage.setItem('bgImageEnabled', String(this.enabled));
        this.apply();
    },

    setMode(mode) {
        this.mode = mode;
        localStorage.setItem('bgImageMode', mode);
        this.apply();
    },

    setBrightness(val) {
        this.brightness = val;
        localStorage.setItem('bgBrightness', String(val));
        this.apply();
    },

    setBlur(val) {
        this.blur = val;
        localStorage.setItem('bgBlur', String(val));
        this.apply();
    },

    error: null,

    handleUpload(event) {
        const file = event.target.files[0];
        // reset the input so re-picking the same file fires change again
        event.target.value = '';
        this.error = null;
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            this.error = 'That is not an image file.';
            return;
        }
        // the picture lives as a base64 data URL in a CSS custom property,
        // so a giant photo would drag every style recalc down with it
        if (file.size > 15 * 1024 * 1024) {
            this.error = 'Image too large (max 15 MB) - try a smaller one.';
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            this.dataUrl = reader.result;
            // uploading implies wanting to see it
            this.enabled = true;
            localStorage.setItem('bgImageEnabled', 'true');
            this.apply();
            this._idb('readwrite', this.dataUrl)
                .catch(e => console.warn('Failed to persist background image:', e));
        };
        reader.readAsDataURL(file);
    },

    clear() {
        this.dataUrl = null;
        this.enabled = false;
        localStorage.setItem('bgImageEnabled', 'false');
        this.apply();
        this._idb('readwrite', null)
            .catch(e => console.warn('Failed to remove stored background image:', e));
    },

    _openDb() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open('lumara-background', 1);
            req.onupgradeneeded = () => { req.result.createObjectStore('images'); };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    },

    // one-shot IDB op: readonly returns the stored dataURL,
    // readwrite with a value stores it (null deletes the entry)
    _idb(mode, value) {
        return new Promise((resolve, reject) => {
            if (!this._db) { reject(new Error('database not open')); return; }
            const tx = this._db.transaction('images', mode);
            const store = tx.objectStore('images');
            const req = mode === 'readonly' ? store.get('background')
                      : value === null ? store.delete('background')
                      : store.put(value, 'background');
            tx.oncomplete = () => resolve(req.result);
            tx.onerror = () => reject(tx.error);
        });
    }
};
