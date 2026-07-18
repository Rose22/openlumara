// alpine data used in the main container over in templates/index.html
document.addEventListener('alpine:init', () => {
    Alpine.data('main', () => ({
        chats: [],
        categories: [],
        chat: {},
        messages: [],
        user_input: '',
        selectedChat: null,
        selectedCategory: 'general',

        async init() {
            // fetch current chat
            this.chat = await simpleApiFetch('/api/chat/current');
            if (this.chat) {
                this.selectedChat = this.chat.id;
                this.messages = this.chat.messages;
            }

            // fetch all other data
            this.chats = await simpleApiFetch('/api/chats');
            this.categories = await simpleApiFetch('/api/chats/categories');

            await connectWebSocket();
        },

        async selectChat(chatId) {
            if (this.selectedChat === chatId) { return; }

            this.chat = await simpleApiFetch(`/api/chat/load/${chatId}`);
            this.selectedChat = this.chat.id;
            this.messages = this.chat.messages;
        },

        async newChat() {
            await simpleApiPost('/api/chat/new');

            this.chat = await simpleApiFetch('/api/chat/current');
            this.selectedChat = this.chat.id;

            await this.reloadChats();
            await this.reloadChat();
        },

        async reloadChat() {
            if (Alpine.store("stream").state === "streaming") {
                // block chat reload during streaming
                return;
            }

            if (!this.selectedChat) {
                console.log("tried to reload the chat, but no chat is loaded!");
                return;
            }

            this.chat = await simpleApiFetch(`/api/chat/load/${this.selectedChat}`);
            this.messages = this.chat.messages;
        },

        async reloadChats() {
            this.chats = await simpleApiFetch('/api/chats');
        },

        async selectCategory(category) {
            this.selectedCategory = category;
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
            /*
             * moved this to turns.js as this is a really long function
             */
            return getTurns(this);
        },
    }));

    // stores streaming-related data (STREAM_STORE is defined in stores.js)
    Alpine.store('stream', STREAM_STORE);

    // defined in directives.js
    Alpine.directive('auto-scroll', autoScroll);
});
