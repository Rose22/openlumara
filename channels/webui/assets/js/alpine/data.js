// main data used by index.html's x-data attribute
function getMainData() {
    return {
        chats: [],
        categories: [],
        chat: {},
        messages: [],
        user_input: '',
        last_user_input: '',
        selectedChat: null,
        selectedCategory: 'general',
        currentModal: '',

        async init() {
            // fetch current chat
            this.chat = await simpleApiFetch('/api/chat/current');
            if (this.chat) {
                this.selectedChat = this.chat.id;
                this.messages = this.chat.messages;
            }

            // fetch all other data
            this.chats = await simpleApiFetch('/api/chats');
            
            // sort it in descending order
            this.chats.reverse();

            this.categories = await simpleApiFetch('/api/chats/categories');

            await connectWebSocket();
        },

        async loadChat(chatId) {
            if (this.selectedChat === chatId) { return; }

            // don't allow chat switching if a stream is ongoing
            if (Alpine.store("stream").state != 'idle') { return; }

            result = await simpleApiFetch(`/api/chat/load/${chatId}`);
            if (!result) { return; }

            this.chat = result;
            this.selectedChat = chatId;
            this.messages = result.messages;
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

            result = await simpleApiFetch(`/api/chat/load/${this.selectedChat}`);
            if (!result) { return }

            this.chat = result;
            this.selectedChat = result.id;
            this.messages = result.messages;
        },

        async reloadChats() {
            this.chats = await simpleApiFetch('/api/chats');

            // sort it in descending order
            this.chats = this.chats.reverse();
        },

        async selectCategory(category) {
            this.selectedCategory = category;
        },

        async clearInput() {
            // store the last user input for use in things like placeholder message bubbles
            this.last_user_input = this.user_input;
            this.user_input = '';
        },

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
