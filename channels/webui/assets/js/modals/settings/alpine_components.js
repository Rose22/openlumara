// Toggle List Component
function toggleList() {
    return {
        item: {},
        enabledSet: new Set(),
        allItems: [],

        init() {
            if (this.item && this.item.value) {
                this.enabledSet = new Set(this.item.value.enabled || []);
                this.allItems = getAllToggleItems(this.item.value);
            }
        },

        toggle(name) {
            if (this.enabledSet.has(name)) {
                this.enabledSet.delete(name);
            } else {
                this.enabledSet.add(name);
            }
            this.commit();
        },

        get sorted() {
            return this.allItems.sort();
        },

        get enabledCount() {
            return this.enabledSet.size;
        },

        commit() {
            this.$dispatch('change', {
                key: this.item.key,
                value: {
                    enabled: [...this.enabledSet],
                    disabled: this.allItems.filter(i => !this.enabledSet.has(i))
                }
            });
        }
    }
}

// Array Input Component
function arrayInput() {
    return {
        item: {},
        items: [],

        init() {
            if (this.item && this.item.value && Array.isArray(this.item.value)) {
                this.items = [...this.item.value];
            } else if (this.item && this.item.value) {
                this.items = [this.item.value];
            }
        },

        add() {
            this.items.push('');
            this.commit();
        },

        remove(index) {
            this.items.splice(index, 1);
            this.commit();
        },

        update(index, value) {
            this.items[index] = value;
            this.commit();
        },

        commit() {
            this.$dispatch('change', {
                key: this.item.key,
                value: this.items
            });
        }
    }
}

// Object Input Component
function objectInput() {
    return {
        item: {},
        entries: [],

        init() {
            if (this.item && this.item.value && typeof this.item.value === 'object') {
                this.entries = Object.entries(this.item.value).map(([k, v]) => [k, v]);
            }
        },

        add() {
            this.entries.push(['', '']);
            this.commit();
        },

        remove(index) {
            this.entries.splice(index, 1);
            this.commit();
        },

        updateKey(index, key) {
            this.entries[index][0] = key;
            this.commit();
        },

        updateValue(index, value) {
            // Try to parse as JSON if it looks like JSON
            try {
                if (value.startsWith('{') || value.startsWith('[')) {
                    JSON.parse(value);
                    this.entries[index][1] = value;
                } else {
                    this.entries[index][1] = value;
                }
            } catch {
                this.entries[index][1] = value;
            }
            this.commit();
        },

        commit() {
            const obj = Object.fromEntries(this.entries);
            this.$dispatch('change', {
                key: this.item.key,
                value: obj
            });
        }
    }
}
