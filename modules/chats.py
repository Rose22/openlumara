import core
import os
import json
import datetime

# Caches flattened chat history text per file, keyed by mtime, so unchanged histories skip re-reading.
_history_cache = {}

def _history_text(path):
    # reads a chat history file and flattens its message contents into one searchable string, using the mtime cache
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""

    cached = _history_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(path, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception:
        return ""

    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if isinstance(content, str) and content.strip():
            parts.append(content)

    text = "\n".join(parts)
    _history_cache[path] = (mtime, text)
    return text

class Chats(core.module.Module):
    """Lets you or the AI manage your chats"""

    settings = {
        "insert_system_prompt": {
            "description": "Make the AI aware of what categories exist for your chats to be sorted into. Highly recommended!",
            "default": True
        }
    }

    async def on_ready(self):
        if not self.config.get("insert_system_prompt"):
            self.disabled_tools.append("get_categories")

    async def on_system_prompt(self):
        if not self.config.get("insert_system_prompt"):
            return None

        cats = await self._get_categories()
        return f"Available categories to categorise chat into: {', '.join(cats)}" if len(cats) > 1 else None

    async def _get_categories(self):
        cats = [c for c in self.channel.context.chat.get_categories() if len(c.split(":")) == 1 and c]
        return cats

    async def get_categories(self):
        cats = await self._get_categories()
        if not cats:
            return self.result("There are no categories yet. Create one!")

        return self.result(cats)

    async def organize(self, new_name: str, category: str, tags: list = None):
        """Lets you rename, categorize, and tag the current chat. If the chat fits within an existing category (defined in your system prompt), use that one. If a fitting category does not exist, create a new one."""
        if not new_name:
            return self.result("name must not be blank", False)

        if tags is None:
            tags = []

        await self.channel.context.chat.set("title", new_name)
        await self.channel.context.chat.set("category", category)
        await self.channel.context.chat.set("tags", tags)
        return self.result(f"chat organised!")

    async def search(self, query: str):
        """Searches within all previous chats the user ever had with you. Very useful for recalling information from the past! Use only if user explicitly requests it, or if you can't find a past event the user is referring to within your current context!"""
        chat_list = self.channel.context.chat

        entries = []
        for meta in chat_list.get_all():
            chat_id = meta.get("id")
            if not chat_id:
                continue

            title = meta.get("title") or ""
            category = meta.get("category") or ""
            path = core.get_data_path(os.path.join(chat_list.path, "history", f"{chat_id}.json"))
            text = _history_text(path)

            if not title and not text:
                continue

            entries.append({"id": chat_id, "title": title, "category": category, "text": text})

        results = await core.search.search(entries, query, field_weights={"title": 2.0, "category": 1.0, "text": 1.0}, top_n=20)

        if isinstance(results, str):
            return self.result(results)

        if not results:
            return self.result("no results found")

        lines = []
        for hit in results:
            entry = hit["entry"]
            line = f'[{entry["category"]}] "{entry["title"]}" (score {hit["score"]:.2f})'
            if entry["text"]:
                snippet = core.search.make_snippet(entry["text"], query)
                if snippet:
                    line += f"\n  {snippet}"
            lines.append(line)

        return self.result("\n".join(lines))
