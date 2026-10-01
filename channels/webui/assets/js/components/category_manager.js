/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
   logic for the sidebar's "manage categories" modal.

   categories are derived from the chats that use them, so creating one
   goes through /api/chats/categories/create (backend validation + a
   fresh chat inside the new category). deleting goes through
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
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // counts come from the backend now; this used to fetch every
            // chat (limit=100000) just to count them client-side.
            try {
                this.counts = await simpleApiFetch('/api/chats/categories/count') ?? {};
            } catch (err) {
                this.counts = {};
            }
        },

        countFor(category) {
            return this.counts[category] ?? 0;
        },

        async add() {
            this.error = '';
            const name = this.newCategory.trim().toLowerCase();

            this.busy = true;
            try {
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                // name validation (empty, ':' reserved for subcategories,
                // duplicates) moved backend-side; the endpoint creates the
                // new chat inside the new category, making it the active chat
                await simpleApiPost('/api/chats/categories/create', { name: name });

                await Alpine.store('chat').reloadCategories();
                await Alpine.store('chat').reloadChats();
                await Alpine.store('chat').reloadChat();

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
