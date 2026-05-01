import core
import os
import msgpack
import datetime
import re
import ulid

cached_mem = None

class Memory(core.module.Module):
    """Gives your AI a persistent memory system"""

    settings = {
        "put_memory_autonomy_instructions_in_system_prompt": True,
        "put_pinned_memories_in_system_prompt": True,
        "max_pinned_memories": 20
    }

    def __init__(self, *args, **kwargs):
        super().__init__( *args, **kwargs)
        self._mem = core.storage.StorageList("memory", type="msgpack")
        self._mem_deleted = core.storage.StorageList("deleted_memories", type="json")
        self.max_pinned = 10

    def _get_index(self, ulid: str) -> int:
        """checks if a memory with ID exists in memories"""
        for index, mem in enumerate(self._mem):
            if ulid.strip() == mem.get("id").strip():
                return index
        return -1

    async def on_system_prompt(self):
        pinned_str = ""
        automem_prompt = ""

        if self.config.get("put_memory_autonomy_instructions_in_system_prompt"):
            automem_prompt = "This is your persistent memory system. You are responsible for managing your own long-term memory. You must proactively and autonomously decide to use these tools to maintain an accurate, up-to-date, and efficient record of the user, your own operational preferences, and important contextual facts. Do not wait for instructions to remember; if information is valuable for future interactions, store it immediately."

        if self.config.get("put_pinned_memories_in_system_prompt"):
            count = 1
            prompt_mem_list = []
            for mem in reversed(self._mem):
                if not mem.get("pinned"):
                    continue

                if count > self.config.get("max_pinned_memories"):
                    break

                prompt_mem_list.append(mem)
                count += 1

            pinned = [f"{m['id']}:\n{m['content']}" for m in prompt_mem_list]
            pinned_str = "\n\n".join(pinned)+"\n\n" or "There are currently no pinned memories.\n\n"

        if not pinned_str and not automem_prompt:
            return None

        return f"{pinned_str}{automem_prompt}"

    async def create(self, content: str, tags: list, pinned: bool = False):
        """Creates a new persistent memory. Use for storing relevant info, preferences, or context for future interactions.
        
        Args:
            content: the contents of the memory
            tags: a list of tags to associate with the memory for later lookup
            pinned: whether to pin a memory to the top of your context window (use for high-importance facts)
        """
        mem = {
            "id": str(ulid.ULID()),
            "content": content,
            "tags": tags,
            "pinned": pinned,
            "date_created": datetime.datetime.now().isoformat()
        }
        self._mem.append(mem)
        self._mem.save()
        return self.result(f"memory added. ID: {mem['id']}")

    async def edit(self, id: str, content: str = None, tags: list = None):
        """Edits an existing memory. Use for self-maintenance/updating outdated info. CAUTION: ONLY use if you can see the memory's ID; NEVER hallucinate IDs."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        if content:
            self._mem[index]["content"] = content
        if tags:
            self._mem[index]["tags"] = tags

        return self.result(self._mem.save())

    async def delete(self, id: str):
        """Deletes a memory. Use to prune irrelevant/redundant info. DANGEROUS: Ensure memory is truly obsolete before deleting."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem_deleted.append(self._mem[index])
        self._mem_deleted.save()

        self._mem.pop(index)
        return self.result(self._mem.save())

    async def pin(self, id: str):
        """Pins a memory to the top of your active context window. Use for critical identity, user preferences, or high-priority goals."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = True
        return self.result(self._mem.save())

    async def unpin(self, id: str):
        """Unpins a memory to manage cognitive load. Use when a pinned memory is no longer high priority."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = False
        return self.result(self._mem.save())

    async def search(self, query: str, search_in_content: bool = False):
        """Searches memories by query. Use when you need to recall past info but don't know the exact ID."""
        query_lower = query.lower()
        results = []

        for mem in self._mem:
            content = str(mem.get("content", "")).lower()
            tags = [str(t).lower() for t in mem.get("tags", [])]

            match_found = False
            # Check if query is in any of the tags
            if any(query_lower in tag for tag in tags):
                match_found = True
            # Check if query is in content (if enabled)
            elif search_in_content and query_lower in content:
                match_found = True

            if match_found:
                results.append(f"ID: {mem.get('id')} | Tags: {mem.get('tags')} | Content: {mem.get('content')}")

        if not results:
            return self.result(f"No memories found matching '{query}'.")

        return self.result("\n".join(results))

    async def list_unpinned(self, tag: str = None):
        """Lists all unpinned memories. Use to browse long-term storage or filter by tag."""
        results = []
        for mem in self._mem:
            if not mem.get("pinned"):
                tags = mem.get("tags", [])

                if tag:
                    # Filter by tag (category)
                    if any(tag.lower() in t.lower() for t in tags):
                        results.append(f"ID: {mem.get('id')} | Tags: {tags} | Content: {mem.get('content')}")
                else:
                    # List everything unpinned
                    results.append(f"ID: {mem.get('id')} | Tags: {tags} | Content: {mem.get('content')}")

        if not results:
            msg = "No unpinned memories found."
            if tag:
                msg += f" (No unpinned memories found with tag '{tag}')"
            return self.result(msg)

        return self.result("\n".join(results))
