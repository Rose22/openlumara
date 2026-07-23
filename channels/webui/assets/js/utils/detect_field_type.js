function detectType(value, key = '') {
    // special keys that should be displayed in a special way
    switch (key) {
        case "model.name":                  return "model_select"
        case "api.url":                     return "api_url"
        case "api.key":                     return "api_key"
        case "model.reasoning_effort":      return "reasoning_effort_slider"
    }

    // standard types
    if (value === null || value === undefined) return 'text';
    else if (typeof value === 'boolean') return 'boolean';
    else if (typeof value === 'number' && !key.toLowerCase().endsWith('id')) return 'number';
    else if (Array.isArray(value)) return 'array';
    else if (typeof value === 'string') {
        if (value.match(/^https?:\/\//)) return 'url';
        else if (value.includes('\n')) return 'textarea';
        else return 'text';
    } else {
        return 'text';
    }
}
