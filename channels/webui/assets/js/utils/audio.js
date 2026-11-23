const AudioManager = {
    db: null,
    audioContext: null,
    masterGainNode: null, // Reusable gain node for performance
    buffers: {
        send_message: null,
        response_start: null,
        processing: null,
        typewriter: null,
        typing: null,
        token: null,
        completion: null,
        reasoning_end: null
    },
    volume: 1.0, // Default volume (0.0 to 1.0)
    tokenVolume: 0.7,
    isReasoningPlaying: false, // Track reasoning chime state
    processingSound: null, // Track processing sound state
    processingStartTime: 0, // Track when processing started
    toneTimer: null, // Timer for processing tones
    processingChain: null,
    synthLPF: null,

    typingFreq: null,
    tokenFreq: null,

    isSoundEnabled: function(id) {
        // the audio store owns the enabled-flags (loaded from localStorage at
        // boot, live-updated by the settings UI); this fallback only answers
        // before Alpine registers the store
        const store = typeof Alpine !== 'undefined' ? Alpine.store('audio') : null;
        if (store && store.sounds) return Boolean(store.sounds[`${id}SoundEnabled`]);
        return this.SOUND_DEFAULTS[id] !== false;
    },

    getSynthLPF: function(ctx) {
        if (this.synthLPF) return this.synthLPF;

        const lpf = ctx.createBiquadFilter();
        lpf.type = 'lowpass';
        lpf.frequency.value = 1800;
        lpf.Q.value = 0.8;
        lpf.connect(this.masterGainNode);

        this.synthLPF = lpf;
        return lpf;
    },

    getProcessingChain: function(ctx) {
        if (this.processingChain) return this.processingChain;

        const convolver = ctx.createConvolver();
        const masterFilter = ctx.createBiquadFilter();

        // Create atmospheric reverb
        const rate = ctx.sampleRate;
        const length = rate * 1.2;
        const impulse = ctx.createBuffer(2, length, rate);
        const dataL = impulse.getChannelData(0);
        const dataR = impulse.getChannelData(1);
        for (let i = 0; i < length; i++) {
            const decay = Math.pow(1 - i / length, 2.5) * Math.sin((i / length) * Math.PI);
            dataL[i] = (Math.random() * 2 - 1) * decay;
            dataR[i] = (Math.random() * 2 - 1) * decay;
        }
        convolver.buffer = impulse;

        // Filter to soften the tones
        masterFilter.type = 'lowpass';
        masterFilter.frequency.value = 1200;
        masterFilter.Q.value = 0.5;

        masterFilter.connect(convolver);
        convolver.connect(this.masterGainNode);

        this.processingChain = { convolver, masterFilter };
        return this.processingChain;
    },

    SOUND_DEFAULTS: {
        send_message: true,
        response_start: true,
        processing: false,
        token: false,
        typing: true,
        reasoning_end: false,
        completion: true,
        typewriter: false
    },

    // Initialize IndexedDB and AudioContext
    init: function() {
        return new Promise((resolve, reject) => {
            // Load volume from storage (skip once the audio store has pushed
            // a fresher value in, so a boot-time race can't clobber it)
            if (localStorage.getItem('sfxVolume') !== null) {
                this.volume = parseFloat(localStorage.getItem('sfxVolume'));
            }
            this.tokenVolume = parseFloat(localStorage.getItem('sfxTokenVolume') || '0.6');

            // 1. Open IndexedDB
            const request = indexedDB.open('TypewriterSoundsDB', 1);

            request.onerror = (event) => {
                console.error('IndexedDB error:', event.target.error);
                reject(event.target.error);
            };

            request.onsuccess = async (event) => {
                this.db = event.target.result;

                // 2. Pre-load uploaded sounds into memory buffers
                await this.loadFromStorage();
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

    // Decode a base64 data URL into a raw ArrayBuffer
    dataUrlToArrayBuffer: function(dataUrl) {
        const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
        const byteString = atob(base64);
        const ab = new ArrayBuffer(byteString.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < byteString.length; i++) {
            ia[i] = byteString.charCodeAt(i);
        }
        return ab;
    },

    // Load uploaded sound buffers into memory: IndexedDB first (uploads
    // live there, quota-safe), falling back to old localStorage data-URL
    // entries and migrating those into the DB
    loadFromStorage: async function() {
        const ids = ['send_message', 'response_start', 'processing', 'typewriter',
                     'typing', 'token', 'completion', 'reasoning_end'];

        const decodeInto = async (id, arrayBuffer) => {
            try {
                this.buffers[id] = await this.getAudioContext().decodeAudioData(arrayBuffer);
                return true;
            } catch (e) {
                console.warn(`Failed to decode audio buffer for ${id}:`, e);
                return false;
            }
        };

        const loadFromDB = (id) => {
            return new Promise((resolve) => {
                if (!this.db) { resolve(false); return; }
                const transaction = this.db.transaction(['sounds'], 'readonly');
                const store = transaction.objectStore('sounds');
                const request = store.get(id);

                request.onsuccess = async (event) => {
                    if (event.target.result && event.target.result.data) {
                        resolve(await decodeInto(id, event.target.result.data));
                        return;
                    }
                    resolve(false);
                };
                request.onerror = () => resolve(false);
            });
        };

        // migrate uploads stored as data URLs by older builds (these could
        // silently fail the localStorage quota; the DB cannot)
        const migrateFromLocalStorage = async (id) => {
            let stored = null;
            try { stored = localStorage.getItem(`${id}SoundData`); } catch (e) {}
            if (!stored) return;

            const ok = await decodeInto(id, this.dataUrlToArrayBuffer(stored));
            if (ok && this.db) {
                try {
                    const transaction = this.db.transaction(['sounds'], 'readwrite');
                    transaction.objectStore('sounds').put({ id, data: this.dataUrlToArrayBuffer(stored) });
                } catch (e) {}
            }
            try { localStorage.removeItem(`${id}SoundData`); } catch (e) {}
        };

        await Promise.all(ids.map(async (id) => {
            const found = await loadFromDB(id);
            if (!found) await migrateFromLocalStorage(id);
        }));
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

    // Sound-state setters: persistence belongs to the audio store (the sole
    // localStorage writer), these only update the live audio state
    // Set volume (0.0 to 1.0)
    setVolume: function(vol) {
        this.volume = vol;

        // Update the master gain node immediately if it exists
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = vol;
        }
    },
    setTokenVolume: function(vol) {
        this.tokenVolume = vol;
    },
    setTokenFreq: function(freq) {
        this.tokenFreq = freq;
    },

    // Save an uploaded sound file to IndexedDB (and remember its name in
    // localStorage so the settings UI can show it after a reload)
    saveFile: async function(id, file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
                try {
                    const arrayBuffer = e.target.result;

                    // Wait for the indexeddb save to actually complete
                    const putPromise = new Promise((innerResolve, innerReject) => {
                        const tx = this.db.transaction(['sounds'], 'readwrite');
                        const store = tx.objectStore('sounds');
                        const req = store.put({ id, data: arrayBuffer });
                        req.onsuccess = () => innerResolve();
                        req.onerror = () => innerReject(req.error);
                    });
                    await putPromise;

                    // decodeAudioData returns a Promise, must be awaited
                    this.buffers[id] = await this.getAudioContext().decodeAudioData(arrayBuffer);

                    try { localStorage.setItem(`${id}SoundName`, file.name); } catch (e) {}
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

    // Load and cache audio from a Data URL (base64), persisting it to the DB.
    // Kept as a compatibility door for modules; the settings UI uploads
    // straight through saveFile instead.
    loadFromDataURL: async function(id, dataUrl) {
        const ab = this.dataUrlToArrayBuffer(dataUrl);
        this.buffers[id] = await this.getAudioContext().decodeAudioData(ab);

        if (this.db) {
            try {
                const transaction = this.db.transaction(['sounds'], 'readwrite');
                transaction.objectStore('sounds').put({ id, data: ab });
            } catch (e) {}
        }
        return true;
    },

    // Settings-page audition of a built-in sound: ignores the enabled flags
    // and plays a short reference tone
    previewSynth: function(id) {
        const ctx = this.getAudioContext();
        const t = ctx.currentTime;

        const note = (freq, start, dur, volScale) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            osc.connect(gain);
            gain.connect(this.masterGainNode);
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.25 * volScale, start + 0.004);
            gain.gain.exponentialRampToValueAtTime(0.001, start + dur);
            osc.onended = () => { try { osc.disconnect(); gain.disconnect(); } catch (e) {} };
            osc.start(start);
            osc.stop(start + dur + 0.05);
        };

        if (id === 'token') {
            note((this.tokenFreq || 9000) * 0.83, t, 0.09, Math.max(this.tokenVolume, 0.25));
        } else if (id === 'typing') {
            note(this.typingFreq || Number(localStorage.getItem('typingFreq')) || 440, t, 0.1, 1);
        } else if (id === 'send_message') {
            note(440, t, 0.22, 1);
            note(330, t + 0.09, 0.22, 0.85);
        } else if (id === 'response_start') {
            note(330, t, 0.22, 1);
            note(440, t + 0.09, 0.22, 0.85);
        } else if (id === 'completion' || id === 'reasoning_end') {
            note(220, t, 0.25, 1);
            note(330, t + 0.11, 0.28, 0.9);
            note(440, t + 0.22, 0.35, 0.8);
        } else if (id === 'processing') {
            note(196, t, 0.6, 1);
        } else {
            note(440, t, 0.2, 1);
        }
    },

    // Resume the AudioContext immediately (fixes mobile autoplay policies)
    resumeContext: function() {
        const ctx = this.getAudioContext();
        if (ctx && ctx.state === 'suspended') {
            ctx.resume().catch(() => {});
        }
    },

    // Play the sound asynchronously to avoid UI blocking
    play: function(id) {
        if (!this.isSoundEnabled(id)) return;

        // ── Critical: Resume context synchronously on user gesture ──
        this.resumeContext();

        // ── Typing suppression during reasoning chime ──
        if ((id === 'typing' || id === 'typewriter') && this.isReasoningPlaying) {
            return; // Skip typing sound while reasoning chime is active
        }

        const buffer = this.buffers[id];
        // cached instead of a synchronous localStorage read per play() call
        if (this.typingFreq === null) {
            this.typingFreq = Number(localStorage.getItem('typingFreq')) || 440;
        }
        const typingFreq = this.typingFreq;

        if (!buffer) {
            const ctx = this.getAudioContext();

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

            // lpf creation moved below the token branch (token never used it)
            // and now reuses a single cached filter via getSynthLPF().
            let lpf = null;

            // ── Helper: Schedule a single sine tone with smoother attack ──
            const playTone = (freq, startTime, attack = 0, decay = 0.01, volScale = 0.8) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'sine';
                osc.frequency.value = freq;

                osc.connect(gain);
                gain.connect(lpf);

                gain.gain.setValueAtTime(0, startTime);
                gain.gain.linearRampToValueAtTime(vol * volScale, startTime + 0.003);
                gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.003 + decay);

                osc.onended = () => {
                    try { osc.disconnect(); gain.disconnect(); } catch (e) {}
                };

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

                const t2 = t + delay;
                gain.gain.setValueAtTime(0, t2);
                gain.gain.linearRampToValueAtTime(vol * volScale, t2 + 0.003);
                gain.gain.exponentialRampToValueAtTime(0.001, t2 + 0.003 + 0.25);

                osc.onended = () => {
                    try { osc.disconnect(); gain.disconnect(); panner.disconnect(); } catch (e) {}
                };

                osc.start(t2);
                osc.stop(t2 + 0.3);
            };

            if (id === 'token') {
                // per-token localStorage reads replaced with in-memory values
                // (kept in sync by setTokenFreq/setTokenVolume below)
                if (this.tokenFreq === null) {
                    this.tokenFreq = Number(localStorage.getItem('sfxTokenFreq')) || 400;
                }
                const tokenFreq = this.tokenFreq;
                const tokenVol = this.tokenVolume;
                ctx.resume();

                const osc1 = ctx.createOscillator();
                const osc2 = ctx.createOscillator();
                const gain = ctx.createGain();

                osc1.type = 'triangle';
                osc2.type = 'triangle';
                osc1.frequency.value = tokenFreq * 0.83; // ~7500hz base
                osc2.frequency.value = (tokenFreq * 0.83) * 1.02; // slightly detuned chime

                // smooth exponential envelope with safe UI volume scaled by tokenVolume
                const peakVol = 0.025 * tokenVol;
                gain.gain.setValueAtTime(0, t);
                gain.gain.exponentialRampToValueAtTime(0.0005, t + 0.003);
                gain.gain.exponentialRampToValueAtTime(peakVol, t + 0.005);   // peak volume scaled by independent setting
                gain.gain.exponentialRampToValueAtTime(0.0005, t + 0.080);  // smooth fade out


                osc1.connect(gain);
                osc2.connect(gain);
                gain.connect(master);

                const cleanupToken = () => {
                    try { osc1.disconnect(); osc2.disconnect(); gain.disconnect(); } catch (e) {}
                };
                osc1.onended = cleanupToken;
                osc2.onended = cleanupToken;

                osc1.start(t);
                osc2.start(t);
                osc1.stop(t + 0.085);
                osc2.stop(t + 0.085);
                return;
            }


            lpf = this.getSynthLPF(ctx);

            if (id === 'typing') {
                const freq = typingFreq;

                const osc = ctx.createOscillator();
                osc.type = 'sine';
                osc.frequency.value = freq;

                const gain = ctx.createGain();
                gain.gain.value = 0;

                osc.connect(gain);
                gain.connect(lpf);

                osc.onended = () => {
                    try { osc.disconnect(); gain.disconnect(); } catch (e) {}
                };

                osc.start(t);

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
        // Note: ctx.resume() is handled synchronously at the top of this function
        // and via global click listeners to comply with mobile browser autoplay policies.
        setTimeout(() => {
            try {
                const ctx = this.getAudioContext();
                const source = ctx.createBufferSource();
                source.buffer = buffer;

                // the token sound keeps its own volume setting even when
                // it is a custom file, so route it through a scaled gain
                let gain = null;
                if (id === 'token') {
                    this.resumeContext();
                    gain = ctx.createGain();
                    gain.gain.value = this.tokenVolume;
                    gain.connect(this.masterGainNode);
                    source.connect(gain);
                } else {
                    // plain sounds connect straight to the cached master
                    // gain node, avoiding a new GainNode per keystroke
                    source.connect(this.masterGainNode);
                }

                source.onended = () => {
                    try {
                        source.disconnect();
                        if (gain) gain.disconnect();
                    } catch (e) {}
                };

                source.start(0);
            } catch (e) {
                console.warn('Error playing sound:', e);
            }
        }, 0);
    },

    playProcessingSound: function() {
        if (!this.isSoundEnabled('processing')) {
            return;
        }

        if (this.processingSound) return;

        // Synchronously resume context for mobile compatibility
        this.resumeContext();

        if (this.buffers['processing']) {
            const ctx = this.getAudioContext();
            const source = ctx.createBufferSource();
            source.buffer = this.buffers['processing'];
            source.connect(this.masterGainNode);

            const finish = () => {
                try { source.disconnect(); } catch (e) {}
                if (this.processingSound && this.processingSound.source === source) {
                    this.processingSound = null;
                }
            };

            source.onended = finish;
            source.start();

            this.processingSound = {
                source,
                stop: () => {
                    try { source.stop(); } catch (e) {}
                    finish();
                }
            };
        } else {
            if (this.toneTimer) clearTimeout(this.toneTimer);
            this.toneTimer = null;

            const ctx = this.getAudioContext();
            const chain = this.getProcessingChain(ctx);
            const masterFilter = chain.masterFilter;
            const baseFrequency = 196.00;

            if (chain.muted) {
                chain.convolver.connect(this.masterGainNode);
                chain.muted = false;
            }

            this.processingStartTime = ctx.currentTime;
            let isPlaying = true;
            let activeOsc = null;
            let activeGain = null;

            const playSoftTone = () => {
                this.toneTimer = null;
                if (!isPlaying) return;

                const elapsed = ctx.currentTime - this.processingStartTime;
                if (elapsed < 0.5) {
                    this.toneTimer = setTimeout(playSoftTone, 100);
                    return;
                }

                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'sine';
                osc.frequency.value = baseFrequency;

                const now = ctx.currentTime;
                gain.gain.setValueAtTime(0, now);
                gain.gain.linearRampToValueAtTime(0.12, now + 0.05);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 1.5);

                osc.connect(gain);
                gain.connect(masterFilter);

                osc.onended = () => {
                    try { osc.disconnect(); gain.disconnect(); } catch (e) {}
                    if (activeOsc === osc) {
                        activeOsc = null;
                        activeGain = null;
                    }
                };

                activeOsc = osc;
                activeGain = gain;

                osc.start(now);
                osc.stop(now + 1.5);

                this.toneTimer = setTimeout(playSoftTone, 2000);
            };

            playSoftTone();

            this.processingSound = {
                stop: () => {
                    isPlaying = false;
                    if (this.toneTimer) clearTimeout(this.toneTimer);
                    this.toneTimer = null;

                    if (activeOsc) {
                        const node = activeOsc;
                        const gain = activeGain;
                        activeOsc = null;
                        activeGain = null;

                        try {
                            const now = ctx.currentTime;
                            if (gain) {
                                gain.gain.cancelScheduledValues(now);
                                gain.gain.setValueAtTime(gain.gain.value, now);
                                gain.gain.linearRampToValueAtTime(0, now + 0.02);
                            }
                            node.onended = () => {
                                try { node.disconnect(); gain.disconnect(); } catch (e) {}
                            };
                            node.stop(now + 0.02);
                        } catch (e) {
                            try { node.disconnect(); gain.disconnect(); } catch (e2) {}
                        }
                    }

                    if (!chain.muted) {
                        try { chain.convolver.disconnect(); } catch(e) {}
                        chain.muted = true;
                    }

                    this.processingSound = null;
                }
            };
        }
    },

    stopProcessingSound: function() {
        if (this.toneTimer) {
            clearTimeout(this.toneTimer);
            this.toneTimer = null;
        }
        if (this.processingSound) {
            this.processingSound.stop();
        }
    },
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    AudioManager.init().catch(e => console.warn('AudioManager failed to init', e));
});

// Global listeners to resume AudioContext on any user interaction (fixes mobile autoplay policies)
// Attaching to window ensures they work even if user interacts before DOMContentLoaded
(function attachGlobalListeners() {
    const resumeAudio = () => {
        if (window.AudioManager) {
            window.AudioManager.resumeContext();
        }
    };
    document.addEventListener('click', resumeAudio, true);
    document.addEventListener('touchstart', resumeAudio, true);
})();
