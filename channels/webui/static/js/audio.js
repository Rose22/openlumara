// =============================================================================
// Typewriter Audio Manager (IndexedDB + Web Audio API)
// =============================================================================

const TypewriterAudioManager = {
    db: null,
    audioContext: null,
    masterGainNode: null, // Reusable gain node for performance
    buffers: {
        send_message: null,
        response_start: null,
        typewriter: null,
        typing: null,
        token: null,
        completion: null,
        reasoning_end: null
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

        await Promise.all([load('send_message'), load('response_start'), load('typewriter'), load('typing'), load('token'), load('completion'), load('reasoning_end')]);
    },

    getAudioContext: function() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

            // Create a single master gain node once to avoid creating
            // new nodes for every sound play event
            this.masterGainNode = this.audioContext.createGain();
            this.masterGainNode.gain.value = this.volume;
            this.masterGainNode.connect(this.audioContext.destination);
        }
        return this.audioContext;
    },

    // Set volume (0.0 to 1.0)
    setVolume: function(vol) {
        this.volume = vol;
        localStorage.setItem('typewriterVolume', vol);

        // Update the master gain node immediately if it exists
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = vol;
        }
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

    // Load and cache audio from a Data URL (base64)
    loadFromDataURL: function(id, dataUrl) {
        return new Promise((resolve, reject) => {
            try {
                // Strip data URI prefix if present (e.g., "data:audio/mp3;base64,")
                const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
                const byteString = atob(base64);
                const ab = new ArrayBuffer(byteString.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < byteString.length; i++) {
                    ia[i] = byteString.charCodeAt(i);
                }
                const buffer = this.getAudioContext().decodeAudioData(ab);
                this.buffers[id] = buffer;
                resolve(true);
            } catch (err) {
                console.error('Error decoding audio data URL:', err);
                reject(err);
            }
        });
    },

    // Play the sound asynchronously to avoid UI blocking
    play: function(id) {
        // Check if the specific sound type is NOT explicitly enabled
        if (localStorage.getItem(`${id}Enabled`) !== 'true') {
            return;
        }

        // ── Typing suppression during reasoning chime ──
        if ((id === 'typing' || id === 'typewriter') && this.isReasoningPlaying) {
            return; // Skip typing sound while reasoning chime is active
        }

        const buffer = this.buffers[id];
        const typingFreq = Number(localStorage.getItem('typingFreq')) || 440;

        if (!buffer) {
            const ctx = this.getAudioContext();
            if (ctx.state === 'suspended') ctx.resume().catch(() => {});

            const configs = {
                send_message:    { freq: 220,  dur: 0.25 },
                response_start:  { freq: 220,  dur: 0.25 },
                reasoning_end:   { freq: 220,  dur: 0.25 },
                completion:      { freq: 440,  dur: 0.25 }
            };

            const cfg = configs[id] || { freq: 440, dur: 0.2 };
            const t = ctx.currentTime;
            const vol = this.volume;
            const master = this.masterGainNode;

            // ── Warmer: Lower cutoff + smoother roll-off ──
            const lpf = ctx.createBiquadFilter();
            lpf.type = 'lowpass';
            lpf.frequency.value = 1800; // Reduced from 2kHz for more warmth
            lpf.Q.value = 0.8; // Gentler slope, less harsh transition

            // ── Helper: Schedule a single sine tone with smoother attack ──
            const playTone = (freq, startTime, attack = 0, decay = 0.01, volScale = 0.8) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'sine';
                osc.frequency.value = freq;

                osc.connect(gain);
                gain.connect(lpf);
                lpf.connect(master);

                // 3ms attack for a rounder, less clicky onset
                gain.gain.setValueAtTime(0, startTime);
                gain.gain.linearRampToValueAtTime(vol * volScale, startTime + 0.003);
                gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.003 + decay);

                osc.start(startTime);
                osc.stop(startTime + 0.003 + decay + 0.05);
            };

            // ── Helper: Schedule a panned harmonic tone ──
            const playHarmonic = (freqMultiplier, delay, volScale = 0.7, pan = -0.2) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                const panner = ctx.createStereoPanner();

                osc.type = 'sine';
                osc.frequency.value = cfg.freq * freqMultiplier;
                panner.pan.value = pan;

                osc.connect(gain);
                gain.connect(panner);
                panner.connect(lpf);
                lpf.connect(master);

                const t2 = t + delay;
                gain.gain.setValueAtTime(0, t2);
                gain.gain.linearRampToValueAtTime(vol * volScale, t2 + 0.003); // 3ms attack
                gain.gain.exponentialRampToValueAtTime(0.001, t2 + 0.003 + 0.25);

                osc.start(t2);
                osc.stop(t2 + 0.3);
            };

            if (id === 'token') {
                const tokenFreq = Number(localStorage.getItem('tokenFreq')) || 9000;
                ctx.resume();

                const osc1 = ctx.createOscillator();
                const osc2 = ctx.createOscillator();
                const gain = ctx.createGain();

                osc1.type = 'triangle';
                osc2.type = 'triangle';
                osc1.frequency.value = tokenFreq * 0.83; // ~7500hz base
                osc2.frequency.value = (tokenFreq * 0.83) * 1.02; // slightly detuned chime

                // smooth exponential envelope with safe UI volume
                gain.gain.setValueAtTime(0, t);
                gain.gain.exponentialRampToValueAtTime(0.001, t + 0.003);
                gain.gain.exponentialRampToValueAtTime(0.15, t + 0.005);   // peak volume
                gain.gain.exponentialRampToValueAtTime(0.001, t + 0.080);  // smooth fade out


                osc1.connect(gain);
                osc2.connect(gain);
                gain.connect(master);

                osc1.start(t);
                osc2.start(t);
                osc1.stop(t + 0.085);
                osc2.stop(t + 0.085);
                return;
            }


            if (id === 'typing') {
                const freq = typingFreq;

                const osc = ctx.createOscillator();
                osc.type = 'sine';
                osc.frequency.value = freq;

                const gain = ctx.createGain();
                gain.gain.value = 0;

                // Chain: osc → LPF → gain → master
                osc.connect(lpf);
                lpf.connect(gain);
                gain.connect(master);

                osc.start(t);

                // Envelope: 10ms attack, 100ms decay
                // Adjusted volume to match token sound (~25%)
                gain.gain.linearRampToValueAtTime(vol * 0.7, t + 0.01);
                gain.gain.exponentialRampToValueAtTime(0.00001, t + 0.1);
                osc.stop(t + 0.1);

                return;
            }

            if (id === 'send_message') {
                // First note (warm base, smooth attack)
                playTone(440, t, 0.008, 0.20, 0.7);

                // Second note (slightly higher, softer, clear spacing)
                playTone(330, t + 0.08, 0.008, 0.20, 0.6);

                return; // ⚠️ CRITICAL
            }

            if (id === 'response_start') {
                // inverse of send_message

                // Second note (slightly higher, softer, clear spacing)
                playTone(330, t, 0.008, 0.20, 0.7);

                // First note (warm base, smooth attack)
                playTone(440, t + 0.08, 0.008, 0.20, 0.6);
                return; // ⚠️ CRITICAL
            }

            if (id === 'reasoning_end') {
                // Warm base tone (smoother attack, resolving decay)
                this.isReasoningPlaying = true;

                // Soft fifth harmonic (wider spacing)
                playHarmonic(1.5, 0.10, 0.7, -0.3);

                // Gentle octave harmonic (clear resolution)
                playHarmonic(2.0, 0.20, 0.6, 0.3);

                setTimeout(() => {
                    this.isReasoningPlaying = false;
                }, 250);
            }

            // === GENERIC FALLBACK (other sounds) ===
            playTone(cfg.freq, t, 0, cfg.dur, 0.8);

            if (id === 'completion') {
                // First harmonic (softer, lower interval)
                playHarmonic(1.5, 0.10, 0.7, -0.3);

                // Second harmonic (gentle resolution)
                playHarmonic(2.0, 0.22, 0.6, 0.3);
            }

        }

        // Use setTimeout(..., 0) to push execution to the next event loop tick.
        // This ensures the audio logic does not block the typewriter animation frame.
        setTimeout(() => {
            try {
                const ctx = this.getAudioContext();

                // Resume context if suspended (browser autoplay policy)
                if (ctx.state === 'suspended') {
                    ctx.resume().catch(() => {});
                }

                const source = ctx.createBufferSource();
                source.buffer = buffer;

                // Connect source directly to the cached master gain node.
                // This avoids creating a new GainNode on every keystroke.
                source.connect(this.masterGainNode);

                source.start(0);
            } catch (e) {
                console.warn('Error playing sound:', e);
            }
        }, 0);
    }
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    TypewriterAudioManager.init().catch(e => console.warn('AudioManager failed to init', e));
});
