let STREAM_STORE = {
    // one of: idle, sending, processing, streaming
    state: 'idle',

    // tracks latest sent user message
    userMsg: null,
    userMsgPending: false,

    // stores raw token data
    turn: [],
    processing: {},

    // stores the final message after the stream has finished
    finalMessage: [],

    // tracks the id of a pending (not confirmed received by backend) message
    pendingMessageId: null,

    // tracks the index of a confirmed user message
    userMessageId: null,

    async clearTokens() {
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
    }
}
