let STREAM_STORE = {
    state: 'idle',
    turn: [],
    processing: {},

    // llama.cpp router model-load progress ({status, stage, percent}), null when idle
    modelLoad: null,

    // stores the final message after the stream has finished
    finalMessage: [],

    // steering message queue
    queued: [],

    async clear(preserveQueued = false) {
        if (typeof AudioManager !== 'undefined') AudioManager.stopProcessingSound();
        this.state = 'idle';
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
        if (!preserveQueued) this.queued = [];
    }
}
