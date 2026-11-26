let STREAM_STORE = {
    state: 'idle',
    turn: [],
    processing: {},

    // nested agentchains (context compaction, foreground subagents) keyed by
    // stream id; each renders inline under the parent step that spawned it
    nestedChains: {},

    // children of a given parent lane attached to a given parent step
    // (attach_step 0 == spawned before the parent's first step, e.g. a
    // compaction that fired while processing the user message)
    nestedChildren(parentStreamId, attachStep) {
        if (parentStreamId == null) return [];
        return Object.values(this.nestedChains).filter(
            c => c.parent_id === parentStreamId && c.attach_step === attachStep
        );
    },

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
        this.nestedChains = {};
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
        if (!preserveQueued) this.queued = [];
    }
}
