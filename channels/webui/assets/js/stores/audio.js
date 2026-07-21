const SOUND_IDS = ['send_message', 'response_start', 'processing', 'typewriter', 'typing', 'token', 'completion', 'reasoning_end'];

const soundDefaults = {};
SOUND_IDS.forEach(id => {
    soundDefaults[`${id}SoundEnabled`] = false;
    soundDefaults[`${id}SoundData`] = null;
    soundDefaults[`${id}SoundName`] = null;
});

AUDIO_STORE = {
    // Master controls
    volume: parseFloat(localStorage.getItem('sfxVolume') || '1.0'),
    tokenVolume: parseFloat(localStorage.getItem('sfxTokenVolume') || '0.6'),
    tokenFreq: parseInt(localStorage.getItem('sfxTokenFreq') || '9000'),

    // Sound effect states
    sounds: { ...soundDefaults },

    init() {
        // Load sound states from localStorage
        SOUND_IDS.forEach(id => {
            const enabled = localStorage.getItem(`${id}SoundEnabled`);
            if (enabled !== null) this.sounds[`${id}SoundEnabled`] = enabled === 'true';

            const soundData = localStorage.getItem(`${id}SoundData`);
            const soundName = localStorage.getItem(`${id}SoundName`);
            if (soundData) {
                this.sounds[`${id}SoundData`] = soundData;
                this.sounds[`${id}SoundName`] = soundName;
            }
        });

        // Sync with AudioManager
        AudioManager.setVolume(this.volume);
    },

    setVolume(val) {
        this.volume = val;
        localStorage.setItem('sfxVolume', val);
        AudioManager.setVolume(val);
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
        this.sounds[`${id}SoundData`] = dataUrl;
        this.sounds[`${id}SoundName`] = name;
        localStorage.setItem(`${id}SoundData`, dataUrl);
        localStorage.setItem(`${id}SoundName`, name);
        
        // Load into AudioManager
        AudioManager.loadFromDataURL(id, dataUrl);
    },

    clearSound(id) {
        this.sounds[`${id}SoundData`] = null;
        this.sounds[`${id}SoundName`] = null;
        localStorage.removeItem(`${id}SoundData`);
        localStorage.removeItem(`${id}SoundName`);
        
        AudioManager.deleteFile(id);
    },

    handleSoundUpload(event, id) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const dataUrl = e.target.result;
            this.setSoundData(id, dataUrl, file.name);
        };
        reader.readAsDataURL(file);
    },

    previewSound(id) {
        AudioManager.play(id);
    },

    reset() {
        this.volume = 1.0;
        this.tokenVolume = 0.6;
        localStorage.setItem('sfxVolume', '1.0');
        localStorage.setItem('sfxTokenVolume', '0.6');
        AudioManager.setVolume(1.0);
    }
};
