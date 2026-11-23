// AI GENERATED CODE (Claude Foy) :: (2026-11-23) status:reviewed
// Settings fields whose title hints at a secret (API key, auth token, password)
// get password-masked inputs with a reveal toggle. Matching is case-insensitive
// substring on the auto-formatted title (e.g. "discord_token" -> "Discord Token").
// Returns the matched keyword (or 'api_key' for the dedicated type), or null.
function secretFieldKeyword(title) {
    if (!title) return null;
    const t = title.toLowerCase();
    for (const kw of ['password', 'token', 'key']) {
        if (t.includes(kw)) return kw;
    }
    return null;
}
