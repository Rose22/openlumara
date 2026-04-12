// =============================================================================
// Typewriter Audio Manager (IndexedDB + Web Audio API)
// =============================================================================

const TypewriterAudioManager = {
    db: null,
    audioContext: null,
    buffers: {
        typewriter: null,
        completion: null
    },
    volume: 1.0, // Default volume (0.0 to 1.0)

    // Initialize IndexedDB and AudioContext
    init: function() {
        return new Promise((resolve, reject) => {
            // Load volume from storage
            this.volume = parseFloat(localStorage.getItem('typewriterVolume') || '1.0');

            // 1. Open IndexedDB
            const request = indexedDB.open('TypewriterSoundsDB', 1);

            request.onerror = (event) => {
                console.error('IndexedDB error:', event.target.error);
                reject(event.target.error);
            };

            request.onsuccess = async (event) => {
                this.db = event.target.result;

                // 2. Pre-load sounds from DB into memory
                await this.loadSoundsFromDB();
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('sounds')) {
                    db.createObjectStore('sounds', { keyPath: 'id' });
                }
            };
        });
    },

    // Load buffers from IndexedDB into memory
    loadSoundsFromDB: async function() {
        if (!this.db) return;

        const load = (id) => {
            return new Promise((resolve) => {
                const transaction = this.db.transaction(['sounds'], 'readonly');
                const store = transaction.objectStore('sounds');
                const request = store.get(id);

                request.onsuccess = async (event) => {
                    if (event.target.result && event.target.result.data) {
                        const arrayBuffer = event.target.result.data;
                        try {
                            const buffer = await this.getAudioContext().decodeAudioData(arrayBuffer);
                            this.buffers[id] = buffer;
                        } catch (e) {
                            console.warn(`Failed to decode audio buffer for ${id}:`, e);
                        }
                    }
                    resolve();
                };
                request.onerror = () => resolve();
            });
        };

        await Promise.all([load('typewriter'), load('completion')]);
    },

    getAudioContext: function() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        return this.audioContext;
    },

    // Set volume (0.0 to 1.0)
    setVolume: function(vol) {
        this.volume = vol;
        localStorage.setItem('typewriterVolume', vol);
    },

    // Save a file to IndexedDB
    saveFile: async function(id, file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
                try {
                    const arrayBuffer = e.target.result;

                    // 1. Save to IndexedDB
                    const transaction = this.db.transaction(['sounds'], 'readwrite');
                    const store = transaction.objectStore('sounds');
                    store.put({ id: id, data: arrayBuffer });

                    // 2. Decode and cache in memory immediately
                    const buffer = await this.getAudioContext().decodeAudioData(arrayBuffer);
                    this.buffers[id] = buffer;

                    resolve(true);
                } catch (err) {
                    console.error('Error saving audio file:', err);
                    reject(err);
                }
            };
            reader.readAsArrayBuffer(file);
        });
    },

    // Delete a file from IndexedDB
    deleteFile: function(id) {
        this.buffers[id] = null;
        if (this.db) {
            const transaction = this.db.transaction(['sounds'], 'readwrite');
            const store = transaction.objectStore('sounds');
            store.delete(id);
        }
    },

    // Play the sound with volume control
    play: function(id) {
        const buffer = this.buffers[id];
        if (!buffer) return;

        try {
            const ctx = this.getAudioContext();
            // Resume context if suspended (browser autoplay policy)
            if (ctx.state === 'suspended') {
                ctx.resume();
            }

            const source = ctx.createBufferSource();
            source.buffer = buffer;

            // Create GainNode to control volume
            const gainNode = ctx.createGain();
            gainNode.gain.value = this.volume; // Apply current volume
            gainNode.connect(ctx.destination);

            source.connect(gainNode);
            source.start(0);
        } catch (e) {
            console.warn('Error playing sound:', e);
        }
    }
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    TypewriterAudioManager.init().catch(e => console.warn('AudioManager failed to init', e));
});
