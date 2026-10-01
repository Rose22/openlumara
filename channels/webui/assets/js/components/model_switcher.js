/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
 * quick model switcher for the chat header: reuses the settings store's
 * cached model list and the model.name setting field, so the dropdown in
 * the header and the one in the settings modal always stay in sync.
 */
function modelQuickSwitch() {
    return {
        saving: false,

        get currentModel() {
            return Alpine.store('settings').categories?.model?.settings?.name?.value || '';
        },

        // cached list from the API, with the current model prepended if
        // the API doesn't list it (custom/manual model names)
        get options() {
            const cached = Alpine.store('settings').cachedModels || [];
            if (this.currentModel && !cached.includes(this.currentModel)) {
                return [this.currentModel, ...cached];
            }
            return cached;
        },

        init() {
            const settings = Alpine.store('settings');
            if (!settings.cachedModels) settings.fetchModels();
        },

        async setModel(name) {
            if (!name || name === this.currentModel || this.saving) return;

            this.saving = true;
            try {
                await simpleApiPost('/api/model/set', { name });

                // keep the settings store's field in sync, so the modal
                // reflects the switch without a reload
                const field = Alpine.store('settings').categories?.model?.settings?.name;
                if (field) field.value = name;
            } catch (err) {
                alert('Failed to switch model: ' + err);
            } finally {
                this.saving = false;
            }
        }
    };
}
