let STREAM_STORE = {
    // one of: idle, sending, processing, streaming
    state: 'idle',

    // stores raw token data
    tokens: [],
    processing: {},

    // stores the final message after the stream has finished
    finalMessage: [],

    // tracks the id of a pending (not confirmed received by backend) message
    pendingMessageId: null,

    // tracks the index of a confirmed user message
    userMessageId: null,

    async clearTokens() {
        this.tokens = [];
        this.processing = {};
    }
}
