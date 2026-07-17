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
            this.chats = await simpleApiFetch('/api/chats');
            this.categories = await simpleApiFetch('/api/chats/categories');
            this.messages = await simpleApiFetch('/api/chat/messages');
        },

        async selectChat(chatId) {
            if (this.selectedChat === chatId) { return; }

            this.selectedChat = chatId;
            this.chat = await simpleApiFetch(`/api/chat/load/${chatId}`);
            this.messages = this.chat.messages;
        },

        async selectCategory(category) {
            this.selectedCategory = category;
        }
    }))
})
