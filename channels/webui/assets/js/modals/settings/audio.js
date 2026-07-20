const SOUND_IDS = ['error', 'warning', 'success', 'info', 'message', 'reply'];

const soundDefaults = {};
SOUND_IDS.forEach(id => {
    soundDefaults[`${id}Enabled`] = true;
    soundDefaults[`${id}SoundData`] = null;
    soundDefaults[`${id}SoundName`] = null;
});

AUDIO_STORE = {
    // Master controls
    volume: parseFloat(localStorage.getItem('typewriterVolume') || '0.7'),
    tokenVolume: parseFloat(localStorage.getItem('tokenVolume') || '0.6'),

    // Sound effect states
    sounds: { ...soundDefaults },

    init() {
        // Load sound states from localStorage
        SOUND_IDS.forEach(id => {
            const enabled = localStorage.getItem(`${id}Enabled`);
            if (enabled !== null) this.sounds[`${id}Enabled`] = enabled === 'true';
        });

        // Sync with AudioManager if available
        if (typeof AudioManager !== 'undefined') {
            AudioManager.setVolume(this.volume);
            // AudioManager.setTokenVolume(this.tokenVolume);
        }
    },

    setVolume(val) {
        this.volume = val;
        localStorage.setItem('typewriterVolume', val);
        if (typeof AudioManager !== 'undefined') {
            AudioManager.setVolume(val);
        }
    },

    // setTokenVolume(val) {
    //     this.tokenVolume = val;
    //     localStorage.setItem('tokenVolume', val);
    //     if (typeof AudioManager !== 'undefined' && AudioManager.setTokenVolume) {
    //         AudioManager.setTokenVolume(val);
    //     }
    // },

    setSoundEnabled(id, enabled) {
        this.sounds[`${id}Enabled`] = enabled;
        localStorage.setItem(`${id}Enabled`, String(enabled));
    },

    setSoundData(id, dataUrl, name) {
        this.sounds[`${id}SoundData`] = dataUrl;
        this.sounds[`${id}SoundName`] = name;
        localStorage.setItem(`${id}SoundData`, dataUrl);
        localStorage.setItem(`${id}SoundName`, name);
        
        // Load into AudioManager
        AudioManager.loadSound(id, dataUrl, name);
    },

    clearSound(id) {
        this.sounds[`${id}SoundData`] = null;
        this.sounds[`${id}SoundName`] = null;
        localStorage.removeItem(`${id}SoundData`);
        localStorage.removeItem(`${id}SoundName`);
        
        if (typeof AudioManager !== 'undefined') {
            AudioManager.clearSound(id);
        }
    },

    hasAudio(id) {
        return !!this.sounds[`${id}SoundData`];
    },

    reset() {
        this.volume = 0.7;
        this.tokenVolume = 0.6;
        localStorage.setItem('typewriterVolume', '0.7');
        localStorage.setItem('tokenVolume', '0.6');
        if (typeof AudioManager !== 'undefined') {
            AudioManager.setVolume(0.7);
            // AudioManager.setTokenVolume(0.6);
        }
    }
};
