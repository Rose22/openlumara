function secretFieldKeyword(title) {
    if (!title) return null;
    const t = title.toLowerCase();
    for (const kw of ['password', 'token', 'key']) {
        if (t.includes(kw)) return kw;
    }
    return null;
}
