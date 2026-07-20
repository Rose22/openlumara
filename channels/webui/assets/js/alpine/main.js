/*
 * main data used by index.html's x-data attribute
 * i want to figure out some way to split this up into multiple files,
 * since that would make the code even cleaner,
 * but for now this will have to do
 */
function getMainData() {
    return {
        chats: [],
        categories: [],
        chat: {},
        user_input: '',
        last_user_input: '',
        selectedChat: null,
        selectedCategory: 'general',
        currentModal: '',

        messages: [],
        editingMessageIndex: null,
        editContent: '',

        /* 
         * a special notification to be used in case of important information,
         * such as "not connected to backend" (websockets)
         */
        notice: null,

        async init() {
            self.notice = "Please wait, connecting to backend server..";
            await connectWebSocket();

            // fetch current chat
            const chat = await simpleApiFetch('/api/chat/current');
            this.chat = chat;
            this.selectedChat = chat.id;
            this.messages = chat.messages;

            // fetch all other data
            this.chats = await simpleApiFetch('/api/chats');
            
            // sort it in descending order
            this.chats.reverse();

            this.categories = await simpleApiFetch('/api/chats/categories');
        },

        /* ----------------------
         * chat-specific functions
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

            // make sure it always shows the bottom of the chat
            await forceScrollDown(document.getElementById("messages"));
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

        get turns() {
            // defined in chat/turns.js
            return getTurns(this);
        }
    }
}
