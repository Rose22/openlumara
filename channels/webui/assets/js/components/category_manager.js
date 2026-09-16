/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
   logic for the sidebar's "manage categories" modal.

   categories are derived from the chats that use them, so there is no
   create endpoint: adding a category = creating a fresh chat inside it
   (chat store's newChat(name)). deleting goes through
   /api/chats/categories/delete, which moves the category's chats to
   'general'. */
function categoryManager() {
    return {
        newCategory: '',
        error: '',
        confirming: null,
        counts: {},
        busy: false,

        init() {
            this.refresh();
        },

        async refresh() {
            // one unpaginated fetch of every chat, counted per category.
            // blank categories count towards 'general' (backend treats
            // blank as general).
            const result = await simpleApiFetch('/api/chats?offset=0&limit=100000');

            const counts = {};
            for (const chat of (result?.messages ?? [])) {
                const cat = chat.category || 'general';
                counts[cat] = (counts[cat] ?? 0) + 1;
            }
            this.counts = counts;
        },

        countFor(category) {
            return this.counts[category] ?? 0;
        },

        async add() {
            this.error = '';
            const name = this.newCategory.trim().toLowerCase();

            if (!name) {
                this.error = 'category name cannot be empty';
                return;
            }
            if (name.includes(':')) {
                this.error = "':' is reserved for subcategories";
                return;
            }

            const existing = (Alpine.store('chat').categories ?? [])
                .map(c => (c ?? '').toLowerCase());
            if (existing.includes(name)) {
                this.error = `"${name}" already exists`;
                return;
            }

            this.busy = true;
            try {
                // the new chat becomes the active chat in the new category
                await Alpine.store('chat').newChat(name);
                this.newCategory = '';
                await this.refresh();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to create category';
            } finally {
                this.busy = false;
            }
        },

        async confirmDelete(name) {
            this.busy = true;
            try {
                await Alpine.store('chat').deleteCategory(name);
                this.confirming = null;
                await this.refresh();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to delete category';
            } finally {
                this.busy = false;
            }
        }
    };
}
