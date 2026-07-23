CHAT_STORE = {
    /*
     * alpine.js store for chat state
     */

    chats: [],
    categories: [],
    chat: {},
    selectedChat: null,
    selectedCategory: 'general',

    messages: [],
    editingMessageIndex: null,
    editContent: '',


    _turnsVersion: 0,
    _historyTurns: null,
    _historyTurnsHash: null,

    _streamingTurn: null,
    _streamingTurnHash: null,


    user_input: '',
    last_user_input: '',

    async load() {
        // called by Alpine.init
        await this.reloadChats();
        await this.reloadCategories();

        const result = await simpleApiFetch(`/api/chat/current`);
        if (!result) { return }

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.messages = result.messages;
    },

    /* ----------------------
     * chat manipulation
     * ----------------------- */
    async loadChat(chatId) {
        if (this.selectedChat === chatId) { return; }

        // don't allow chat switching if a stream is ongoing
        if (Alpine.store("stream").state != 'idle') { return; }

        const result = await simpleApiFetch(`/api/chat/load/${chatId}`);
        if (!result) { return; }

        this.chat = result;
        this.selectedChat = chatId;
        this.selectedCategory = result.category;
        this.messages = result.messages;

        ui = Alpine.store('ui');

        // make sure it always shows the bottom of the chat
        await ui.forceScrollToBottom();
    },

    async newChat() {
        await simpleApiPost('/api/chat/new');

        this.chat = await simpleApiFetch('/api/chat/current');
        this.selectedChat = this.chat.id;

        await this.reloadChats();
        await this.reloadChat();
    },

    async reloadChat() {
        stream = Alpine.store("stream");

        if (!this.selectedChat) {
            console.log("tried to reload the chat, but no chat is loaded!");
            return;
        }

        const result = await simpleApiFetch(`/api/chat/current`);
        if (!result) { return }

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;

        this.messages = result.messages;

        /*
         * since the AI can move chats to different categories,
         * the category might have changed
         * or a new one might have been created
         */
        await this.reloadCategories();
        await this.reloadChats();
    },

    async reloadChats() {
        this.chats = await simpleApiFetch('/api/chats');

        // sort it in descending order
        this.chats.reverse();
    },

    async reloadCategories() {
        this.categories = await simpleApiFetch('/api/chats/categories');
    },

    async selectCategory(category) {
        this.selectedCategory = category;
    },

    async clearInput() {
        // store the last user input for use in things like placeholder message bubbles
        this.last_user_input = this.user_input;
        this.user_input = '';
    },


    async send(text) {
        const uploadStore = Alpine.store("upload");

        let files = null;

        if (uploadStore.files.length > 0) {
            files = await Promise.all(
                uploadStore.files.map(async (file) => ({
                    name: file.name,
                    data: await uploadStore.readFileAsBase64(file)
                }))
            );
        }

        AudioManager.play("send_message");

        const success = await simpleSocketSend({
            type: "user_message",
            content: text,
            files: files
        });

        if (success) {
            Alpine.store("stream").state = "sending";
        }

        uploadStore.clear();
    },

    /* ----------------------
     * message actions
     * ----------------------- */
    async deleteMessage(index) {
        await simpleSocketSend({
            "type": "message_delete",
            "index": index
        });
    },

    async regenerateMessage(index) {
        await simpleSocketSend({
            "type": "message_regenerate",
            "index": index
        });
    },

    async startEdit(index) {
        const msg = this.messages[index]
        if (msg) {
            this.editingMessageIndex = index;
            this.editContent = msg.content || msg.reasoning_content || '';
        }
    },

    async cancelEdit() {
        this.editingMessageIndex = null;
        this.editContent = '';
    },

    async saveEdit(index) {
        await simpleSocketSend({
            "type": "message_edit",
            "index": index,
            "content": this.editContent
        });
        this.editingMessageIndex = null;
        this.editContent = '';
    },

    /* ----------------------
     * chat-specific getters
     * ----------------------- */
    get promptprogress() {
        // does the math for the prompt processing indicator over in components/promptprocess.html
        // the math was ported straight over from the old webUI because, well, it works, and it's clean code
        const progressData = Alpine.store("stream").processing;

        const cache = progressData.cache || 0;
        const processed = progressData.processed - cache;
        const total = progressData.total - cache;
        const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
        const elapsed = progressData.time_ms / 1000;
        const remaining = (total - processed) > 0 ? (elapsed / processed) * (total - processed) : 0;

        return {
            cache,
            processed,
            total,
            percent,
            percent_str: `${percent}%`,
            elapsed: elapsed.toFixed(1),
            remaining,
            remaining_str: `(ETA: ${Math.ceil(remaining)}s)`
        };
    },

    // Version counter for Alpine reactivity
    get turnsVersion() {
        // This lets Alpine know the turns have changed
        // by accessing a reactive property that increments
        return this._turnsVersion || 0;
    },

    // Call this from the WebSocket handler after pushing a token
    onTokenArrived() {
        this._turnsVersion = (this._turnsVersion || 0) + 1;
    },

    // Call this from the WebSocket handler after messages_updated
    onMessagesChanged() {
        this._turnsVersion = (this._turnsVersion || 0) + 1;
    },

    get turns() {
        // defined in processors/turns.js
        return getTurns(this);
    }
}
