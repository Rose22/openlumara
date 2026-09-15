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
    synthLPF: null, // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15) shared lowpass for synth fallback tones, built once instead of per play() call

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
    // the lowpass used by the synth fallbacks was being created fresh on every
    // play() call (including per-token) even though its config is static, and
    // the token path never even connected it. one cached filter, pre-connected
    // to the master gain.
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

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) - (2026-09-15)
    // builds the reverb chain for the synth processing fallback exactly once.
    // generating the impulse response costs ~235KB per call and prompt_progress
    // tokens fire many times per second, so rebuilding it per call was pure churn.
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
            // Load volume from storage
            this.volume = parseFloat(localStorage.getItem('sfxVolume') || '1.0');

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

        await Promise.all([
            load('send_message'), load('response_start'), load('typewriter'),
            load('typing'), load('token'), load('completion'), load('reasoning_end'),
            load('processing')
        ]);
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
        localStorage.setItem('sfxVolume', vol);

        // Update the master gain node immediately if it exists
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = vol;
        }
    },
    setTokenVolume: function(vol) {
        this.tokenVolume = vol;
        localStorage.setItem('sfxTokenVolume', vol);

        // Update the master gain node immediately if it exists
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = vol;
        }
    },
    setTokenFreq: function(freq) {
        this.tokenFreq = freq;
        localStorage.setItem('sfxTokenFreq', freq);
    },

    // Save a file to IndexedDB
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
        return new Promise(async (resolve, reject) => {
            try {
                // Strip data URI prefix if present (e.g., "data:audio/mp3;base64,")
                const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
                const byteString = atob(base64);
                const ab = new ArrayBuffer(byteString.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < byteString.length; i++) {
                    ia[i] = byteString.charCodeAt(i);
                }
                const buffer = await this.getAudioContext().decodeAudioData(ab);
                this.buffers[id] = buffer;
                resolve(true);
            } catch (err) {
                console.error('Error decoding audio data URL:', err);
                reject(err);
            }
        });
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
        // ── Check Storage or Fallback to Built-in Defaults ──
        let isEnabled = true;
        try {
            if (typeof localStorage !== 'undefined') {
                const stored = localStorage.getItem(`${id}SoundEnabled`);
                if (stored !== null) {
                    isEnabled = stored === 'true';
                } else {
                    // If storage is empty/failed, use the built-in default
                    isEnabled = this.SOUND_DEFAULTS[id] !== false;
                }
            }
        } catch (e) {
            isEnabled = this.SOUND_DEFAULTS[id] !== false;
        }

        if (!isEnabled) return;

        // ── Critical: Resume context synchronously on user gesture ──
        this.resumeContext();

        // ── Typing suppression during reasoning chime ──
        if ((id === 'typing' || id === 'typewriter') && this.isReasoningPlaying) {
            return; // Skip typing sound while reasoning chime is active
        }

        const buffer = this.buffers[id];
        const typingFreq = Number(localStorage.getItem('typingFreq')) || 440;

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

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // lpf creation moved below the token branch (token never used it)
            // and now reuses a single cached filter via getSynthLPF().
            let lpf = null;

            // ── Helper: Schedule a single sine tone with smoother attack ──
            const playTone = (freq, startTime, attack = 0, decay = 0.01, volScale = 0.8) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'sine';
                osc.frequency.value = freq;

                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
                // the shared lpf is pre-connected to master inside getSynthLPF(),
                // so the per-call lpf.connect(master) here is removed.
                osc.connect(gain);
                gain.connect(lpf);

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

                // lpf pre-connected to master in getSynthLPF()
                osc.connect(gain);
                gain.connect(panner);
                panner.connect(lpf);

                const t2 = t + delay;
                gain.gain.setValueAtTime(0, t2);
                gain.gain.linearRampToValueAtTime(vol * volScale, t2 + 0.003); // 3ms attack
                gain.gain.exponentialRampToValueAtTime(0.001, t2 + 0.003 + 0.25);

                osc.start(t2);
                osc.stop(t2 + 0.3);
            };

            if (id === 'token') {
                const tokenFreq = Number(localStorage.getItem('sfxTokenFreq')) || 400;
                const tokenVol = parseFloat(localStorage.getItem('sfxTokenVolume')) || 0.7; // New independent volume setting
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

                osc1.start(t);
                osc2.start(t);
                osc1.stop(t + 0.085);
                osc2.stop(t + 0.085);
                return;
            }


            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // grab the shared lowpass only now that we know this isn't the
            // token path (which never uses a filter at all).
            lpf = this.getSynthLPF(ctx);

            if (id === 'typing') {
                const freq = typingFreq;

                const osc = ctx.createOscillator();
                osc.type = 'sine';
                osc.frequency.value = freq;

                const gain = ctx.createGain();
                gain.gain.value = 0;

                // Chain: osc → gain → shared LPF → master
                // (gain must come first: the shared lpf is permanently wired
                // to master, so envelope-shaped audio can't pass through it
                // on a second parallel path)
                osc.connect(gain);
                gain.connect(lpf);

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
        // Note: ctx.resume() is handled synchronously at the top of this function
        // and via global click listeners to comply with mobile browser autoplay policies.
        setTimeout(() => {
            try {
                const ctx = this.getAudioContext();
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
    },

    playProcessingSound: function() {
        if (localStorage.getItem(`processingSoundEnabled`) !== 'true') {
            return;
        }

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) - (2026-09-15)
        // if a processing sound is already running, leave it alone. this gets
        // called on every prompt_progress token, and restarting the tone chain
        // per token churned nodes and reset the elapsed timer constantly.
        if (this.processingSound) return;

        // Synchronously resume context for mobile compatibility
        this.resumeContext();

        if (this.buffers['processing']) {
            // --- PLAY SOUND FILE ---
            const ctx = this.getAudioContext();
            const source = ctx.createBufferSource();
            source.buffer = this.buffers['processing']; // Use your loaded file
            source.connect(this.masterGainNode);
            source.start();

            this.processingSound = {
                stop: () => {
                    try { source.stop(); } catch(e) {} // Stop immediately
                    this.processingSound = null;
                }
            };
        } else {
            // --- FALLBACK TO SYNTH (Optional) ---
            // Plays soft, intermittent waiting tones
            const ctx = this.getAudioContext();

            // reuse the cached reverb chain
            const chain = this.getProcessingChain(ctx);
            const masterFilter = chain.masterFilter;

            // Single frequency
            const baseFrequency = 196.00;

            // if a previous stop() muted the cached chain to kill the reverb
            // tail, reconnect it before scheduling new tones
            if (chain.muted) {
                chain.convolver.connect(this.masterGainNode);
                chain.muted = false;
            }

            // --- TRACK START TIME ---
            this.processingStartTime = ctx.currentTime;
            let isPlaying = true;
            let activeOsc = null;
            let activeGain = null;

            const playSoftTone = () => {
                if (!isPlaying) return;

                // Check if total processing time is less than 0.5s
                const elapsed = ctx.currentTime - this.processingStartTime;
                if (elapsed < 0.5) {
                    // Wait and check again (prevents playing sound for very short requests)
                    this.toneTimer = setTimeout(playSoftTone, 100);
                    return;
                }

                // --- PLAY THE TONE ---
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'sine';
                osc.frequency.value = baseFrequency;

                // Soft attack and release (shorter than delay for clean separation)
                const now = ctx.currentTime;
                gain.gain.setValueAtTime(0, now);
                gain.gain.linearRampToValueAtTime(0.12, now + 0.05);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 1.5);

                osc.connect(gain);
                gain.connect(masterFilter);

                osc.start(now);
                osc.stop(now + 1.5);

                activeOsc = osc;
                activeGain = gain;
                osc.onended = () => {
                    if (activeOsc === osc) { activeOsc = null; activeGain = null; }
                };

                // Fixed 2 second delay for the next tone
                const delay = 2000;
                this.toneTimer = setTimeout(playSoftTone, delay);
            };

            // Start the first tone (it will internally wait if < 0.2s elapsed)
            playSoftTone();

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) - (2026-09-15)
            // cleanup function: previously stop() only killed the timer chain,
            // so an already-scheduled tone rang out its full 1.5s envelope and
            // its reverb tail kept decaying. now we hard-stop the live
            // oscillator (tiny 20ms fade to avoid a click) and mute the reverb
            // chain to cut the tail.
            this.processingSound = {
                stop: () => {
                    isPlaying = false;
                    if (this.toneTimer) clearTimeout(this.toneTimer);

                    if (activeOsc) {
                        try {
                            const now = ctx.currentTime;
                            // fade out over 20ms to avoid a click, then stop
                            if (activeGain) {
                                activeGain.gain.cancelScheduledValues(now);
                                activeGain.gain.setValueAtTime(activeGain.gain.value, now);
                                activeGain.gain.linearRampToValueAtTime(0, now + 0.02);
                            }
                            activeOsc.onended = null;
                            activeOsc.stop(now + 0.02);
                        } catch(e) {}
                        activeOsc = null;
                        activeGain = null;
                    }

                    // cut the reverb tail by disconnecting the chain from output
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
