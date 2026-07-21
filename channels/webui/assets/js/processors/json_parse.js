function partialJsonParse(str) {
    if (!str || !str.trim()) return {};

    try {
        return JSON.parse(str);
    } catch (e) {
        let completed = str.trim();
        completed = completed.replace(/,\s*([}\]])/g, '$1');

        let openBraces = (completed.match(/{/g) || []).length;
        let closeBraces = (completed.match(/}/g) || []).length;
        let openBrackets = (completed.match(/\[/g) || []).length;
        let closeBrackets = (completed.match(/]/g) || []).length;

        const openQuotes = (completed.match(/"(?<!\\)"/g) || []).length;
        if (openQuotes % 2 !== 0) {
            completed += '"';
        }

        while (closeBraces < openBraces) { completed += '}'; closeBraces++; }
        while (closeBrackets < openBrackets) { completed += ']'; closeBrackets++; }

        try {
            return JSON.parse(completed);
        } catch (e2) {
            return { _raw: str };
        }
    }
}
