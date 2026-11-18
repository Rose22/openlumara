function thinkingToggle(initial) {
    return {
        enabled: initial,
        saving: false,

        async toggle() {
            if (this.saving) return;
            this.saving = true;

            const next = !this.enabled;
            try {
                await simpleApiPost('/api/settings/field', { path: ['model', 'enable_thinking'], value: next });
                this.enabled = next;

                const field = Alpine.store('settings').categories?.model?.settings?.enable_thinking;
                if (field) field.value = next;
            } catch (err) {
                alert('Failed to toggle thinking: ' + err);
            } finally {
                this.saving = false;
            }
        }
    };
}
