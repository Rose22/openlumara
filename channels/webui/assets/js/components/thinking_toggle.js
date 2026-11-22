function thinkingToggle(initial) {
    return {
        enabled: initial,
        saving: false,

        async toggle() {
            if (this.saving) return;

            const previous = this.enabled;
            const next = !previous;

            this.enabled = next;
            this.saving = true;

            try {
                await simpleApiPost('/api/settings/field', { path: ['model', 'enable_thinking'], value: next });

                const field = Alpine.store('settings').categories?.model?.settings?.enable_thinking;
                if (field) field.value = next;
            } catch (err) {
                this.enabled = previous;
                alert('Failed to toggle thinking: ' + err);
            } finally {
                this.saving = false;
            }
        }
    };
}
