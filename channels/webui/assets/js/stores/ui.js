UI_STORE = {
    scrollThreshold: 50,
    errors: [],
    currentModal: null,
    notice: null,

    shouldScroll: true,

    windowWidth: window.innerWidth,
    isMobile: false,

    showSidebar: true,
    showCategories: true,
    showChatList: true,

    expandReasoning: false,

    async init() {
        // check if this is a phone
        this.windowWidth = window.innerWidth;
        this.isMobile = window.innerWidth <= 768;

        // hide sidebar on mobile (in favor of a hamburger button)
        this.showSidebar = !this.isMobile;

        // on mobile, the sidebar is a drill-down navigator rather than a two-column pane
        this.showCategories = !this.isMobile;
        this.showChatList = true;

        this.expandReasoning = localStorage.getItem("expandReasoning");
    },

    async toggleSidebar() {
        this.showSidebar = !this.showSidebar;
    },
    async toggleCategories() {
        this.showCategories = !this.showCategories;
    },
    async toggleChatList() {
        this.showChatList = !this.showChatList;
    },

    async toggleMobileSidebarView() {
        // toggles between the chatlist and the categories list
        if (this.showChatList) {
            this.showChatList = false;
            this.showCategories = true;
        } else {
            this.showChatList = true;
            this.showCategories = false;
        }
    },

    async openModal(name) {
        if (this.currentModal === 'settings') {
            // auto-save the settings when switching to a different modal
            await Alpine.store('settings').saveSettings();
        }

        this.currentModal = name;

        /*
         * post-open actions
         */

        if (name === 'logs') {
            // scroll down to the bottom
            await Alpine.nextTick();

            const el = document.getElementById('log-container');
            if (el) el.scrollTop = el.scrollHeight;
        }
    },
    async closeModal() {
        this.currentModal = null;
    },

    /*
     * Called from @scroll on the messages container.
     * Toggles shouldScroll based on whether the user is near the bottom.
     */
    onScroll(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        const wasAtBottom = this.shouldScroll;

        if (distFromBottom < this.scrollThreshold) {
            this.shouldScroll = true;
        } else {
            this.shouldScroll = false;
        }
    },

    async scrollToBottom(containerId = 'messages') {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        Alpine.nextTick(() => {
            el.scrollTop = el.scrollHeight;
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        Alpine.nextTick(() => {
            el.scrollTop = el.scrollHeight;
            this.shouldScroll = true;
        });
    },
}
