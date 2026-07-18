function partialToolcallRenderer(data, depth = 0) {
    let _data = data;
    let _depth = depth;

    return {
        get type() {
            if (_data === null) return 'null';
            if (Array.isArray(_data)) return 'array';
            return typeof _data;
        },

        get isObject() { return this.type === 'object'; },
        get isArray() { return this.type === 'array'; },
        get isScalar() { return ['string', 'number', 'boolean'].includes(this.type); },

        get entries() {
            if (this.isObject) return Object.entries(_data);
            if (this.isArray) return _data.map((v, i) => [i, v]);
            return [];
        },

        get maxItems() {
            if (_depth === 0) return 8;
            if (_depth === 1) return 6;
            return 4;
        },

        get hasMore() {
            return this.entries.length > this.maxItems;
        },

        get visibleEntries() {
            return this.entries.slice(0, this.maxItems);
        },

        get remaining() {
            return this.entries.length - this.maxItems;
        },

        get preview() {
            if (!this.isArray) return '';
            return _data.slice(0, 3)
                .map(item => {
                    if (typeof item === 'string') return `"${item.substring(0, 15)}${item.length > 15 ? '...' : ''}"`;
                    if (typeof item === 'number' || typeof item === 'boolean') return String(item);
                    if (item === null) return 'null';
                    if (Array.isArray(item)) return '[...]';
                    if (typeof item === 'object') {
                        const keys = Object.keys(item);
                        return keys.length > 0 ? `{${keys[0]}...}` : '{}';
                    }
                    return String(item);
                })
                .join(', ') + (_data.length > 3 ? '...' : '');
        },

        toggle() {
            this.collapsed = !this.collapsed;
        },

        showFull() {
            window._jsonModalData = window._jsonModalData || {};
            const id = 'jm-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            window._jsonModalData[id] = _data;
            showFullJsonModal(id, `${this.type}[${this.entries.length}]`);
        }
    };
}
