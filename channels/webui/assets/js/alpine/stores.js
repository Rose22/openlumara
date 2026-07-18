let STREAM_STORE = {
    // one of: idle, sending, processing, streaming
    state: 'idle',

    // stores raw token data
    tokens: [],
    processing: {},

    async clearTokens() {
        this.tokens = [];
        this.processing = [];
    }
}
