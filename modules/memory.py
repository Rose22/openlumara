import core
import os
import msgpack
import datetime
import re
import ulid

cached_mem = None

class Memory(core.module.Module):
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
        # automatically put pinned memories in the prompt
        # TODO: limit to a max amount of pinned memories (configurable) and refuse pinning memories beyond that if it hits the max allowed, tell ai to unpin one so another can be pinned instead
        pinned_memories = []
        for index, mem in enumerate(self._mem):
            if mem.get("pinned"):
                mem_filtered = f"{mem.get("id")}:\n{mem.get("content")}"
                pinned_memories.append(mem_filtered)

        pinned_memories_str = "\n\n".join(pinned_memories)
        sysprompt = f"{pinned_memories_str}\n\nThis is your persistent memory system. When you need to remember something, ALWAYS store it in memory using the memory_create() tool."

        return sysprompt

    async def create(self, content: str, tags: list, pinned: bool = False):
        """
        Creates a new memory within your persistent memory storage.

        A memory should be pinned if it's:
        - Permanent preferences (favorite color, favorite shows, allergies, dietary restrictions)
        - A highly important fact that must always be remembered
        - User's core identity details (name, occupation, family)
        - Long-term goals or life circumstances

        Args:
            content: the contents of the memory
            tags: a list of tags to associate with the memory for later lookup
            pinned: whether to pin a memory to the top of your context window
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
        return self.result(True)

    async def edit(self, id: str, content: str = None, tags: list = None):
        """
        Edits an existing memory.

        CAUTION:
            - ONLY use if you can see the memory's ID
            - NEVER hallucinate or make up an ID
            - If you cannot see the memory, search for it first using memory_search()
        
        Reject if:
            - You cannot see the memory you are about to edit
            - You're not sure which memory to edit

        Args:
            content: the contents of the memory
            tags: optional - leave blank to leave it as-is. a list of tags to associate with the memory for later lookup
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        if content:
            self._mem[index]["content"] = content
        if tags:
            self._mem[index]["tags"] = tags

        return self.result(self._mem.save())

    async def delete(self, id: str):
        """
        Deletes a memory from your storage.
        DANGEROUS. HIGHEST RESTRICTIONS APPLY.

        ONLY delete a memory if:
            - You're sure you have the ID
            - You've verified the ID
            - The user explicitely requested the deletion of the memory
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        # behind the scenes, this actually preserves the memory in a file the ai can't access
        # backups are useful!
        self._mem_deleted.append(self._mem[index])
        self._mem_deleted.save()

        self._mem.pop(index)
        return self.result(self._mem.save())

    async def pin(self, id: str):
        """Pins a memory to the top of your context window. Makes it persistent across conversations."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = True
        return self.result(self._mem.save())

    async def unpin(self, id: str):
        """Unpins a memory from the top of your context window. An unpinned memory can only be reached by manually searching for it."""
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = False
        return self.result(self._mem.save())

    async def search(self, query: str, search_in_content: bool = False):
        """
        Searches your memories for a query.
        Defaults to searching within tags. Enable search_content to also search within the content of memories.
        """
        results = []
        query_lower = query.lower()

        for index, mem in enumerate(self._mem):
            # Check tags: split tags into words and check if any word is in the query
            match_found = False
            tags = mem.get("tags", [])

            for tag in tags:
                # Split tag into words and check if any word exists in the query
                if any(word in query_lower for word in str(tag).lower().split()):
                    match_found = True
                    break

            # Check content only if no tag match found
            if not match_found and search_in_content:
                content = str(mem.get("content", ""))
                if content and query_lower in content.lower():
                    match_found = True

            if match_found:
                results.append(mem)

        return results
