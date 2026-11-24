const SOUND_IDS = ['send_message', 'response_start', 'processing', 'typewriter', 'typing', 'token', 'completion', 'reasoning_end'];

AUDIO_STORE = {
    // Master controls
    volume: 1.0,
    tokenVolume: 0.6,
    tokenFreq: 9000,

    sounds: {},

    init() {
        SOUND_IDS.forEach(id => {
            this.sounds[`${id}SoundEnabled`] = AudioManager.SOUND_DEFAULTS[id] !== false;
            this.sounds[`${id}SoundUploaded`] = false;
            this.sounds[`${id}SoundName`] = null;
        });

        try {
            const vol = localStorage.getItem('sfxVolume');
            if (vol !== null) {
                this.volume = parseFloat(vol);
                this._lastVolume = this.volume > 0 ? this.volume : null;
            }

            const tokVol = localStorage.getItem('sfxTokenVolume');
            if (tokVol !== null) this.tokenVolume = parseFloat(tokVol);

            const tokFreq = localStorage.getItem('sfxTokenFreq');
            if (tokFreq !== null) this.tokenFreq = parseInt(tokFreq);

            SOUND_IDS.forEach(id => {
                const enabled = localStorage.getItem(`${id}SoundEnabled`);
                if (enabled !== null) this.sounds[`${id}SoundEnabled`] = enabled === 'true';

                const name = localStorage.getItem(`${id}SoundName`);
                if (name !== null) {
                    this.sounds[`${id}SoundName`] = name;
                    this.sounds[`${id}SoundUploaded`] = true;
                }
            });
        } catch (e) {}

        AudioManager.setVolume(this.volume);
        AudioManager.setTokenVolume(this.tokenVolume);
        AudioManager.setTokenFreq(this.tokenFreq);
    },

    _lastVolume: null,

    soundLabel(id) {
        return id.charAt(0).toUpperCase() + id.slice(1).replaceAll('_', ' ');
    },

    setVolume(val) {
        this.volume = val;
        if (val > 0) this._lastVolume = val;
        localStorage.setItem('sfxVolume', val);
        AudioManager.setVolume(val);
    },

    toggleMute() {
        if (this.volume > 0) {
            this._lastVolume = this.volume;
            this.setVolume(0);
        } else {
            this.setVolume(this._lastVolume ?? 1.0);
        }
    },
    setTokenVolume(val) {
        this.tokenVolume = val;
        localStorage.setItem('sfxTokenVolume', val);
        AudioManager.setTokenVolume(val);
    },
    setTokenFreq(val) {
        this.tokenFreq = val;
        localStorage.setItem('sfxTokenFreq', val);
        AudioManager.setTokenFreq(val);
    },

    setSoundEnabled(id, enabled) {
        this.sounds[`${id}SoundEnabled`] = enabled;
        localStorage.setItem(`${id}SoundEnabled`, String(enabled));
    },

    setSoundData(id, dataUrl, name) {
        AudioManager.loadFromDataURL(id, dataUrl)
            .then(() => {
                this.sounds[`${id}SoundUploaded`] = true;
                this.sounds[`${id}SoundName`] = name || null;
                try { localStorage.setItem(`${id}SoundName`, name || ''); } catch (e) {}
            })
            .catch(() => {});
    },

    clearSound(id) {
        this.sounds[`${id}SoundUploaded`] = false;
        this.sounds[`${id}SoundName`] = null;
        localStorage.removeItem(`${id}SoundName`);
        localStorage.removeItem(`${id}SoundData`);   

        AudioManager.deleteFile(id);
    },

    handleSoundUpload(event, id) {
        const file = event.target.files[0];
        event.target.value = '';
        if (!file) return;

        if (!AudioManager.db) {
            console.warn('Sound storage (IndexedDB) unavailable; upload ignored');
            return;
        }

        AudioManager.saveFile(id, file)
            .then(() => {
                this.sounds[`${id}SoundUploaded`] = true;
                this.sounds[`${id}SoundName`] = file.name;
            })
            .catch((err) => console.warn(`Failed to save sound for ${id}:`, err));
    },

    previewSound(id) {
        const vol = Math.max(this.volume, 0.5);

        if (AudioManager.buffers[id]) {
            const ctx = AudioManager.getAudioContext();
            AudioManager.resumeContext();
            const src = ctx.createBufferSource();
            const gain = ctx.createGain();
            src.buffer = AudioManager.buffers[id];
            gain.gain.value = vol;
            src.connect(gain);
            gain.connect(ctx.destination);
            src.onended = () => {
                try { src.disconnect(); gain.disconnect(); } catch (e) {}
            };
            src.start(0);
        } else {
            AudioManager.resumeContext();
            AudioManager.previewSynth(id);
        }
    },

    reset() {
        this.volume = 1.0;
        this._lastVolume = null;
        this.tokenVolume = 0.6;
        this.tokenFreq = 9000;
        localStorage.setItem('sfxVolume', '1.0');
        localStorage.setItem('sfxTokenVolume', '0.6');
        localStorage.setItem('sfxTokenFreq', '9000');

        SOUND_IDS.forEach(id => {
            this.sounds[`${id}SoundEnabled`] = false;
            localStorage.setItem(`${id}SoundEnabled`, 'false');
            this.clearSound(id);
        });

        AudioManager.setVolume(this.volume);
        AudioManager.setTokenVolume(this.tokenVolume);
        AudioManager.setTokenFreq(this.tokenFreq);
    }
};
