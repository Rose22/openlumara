import core
import os
import msgpack
import datetime
import re
import ulid

cached_mem = None

class Memory(core.module.Module):
    """Gives your AI a persistent memory system"""

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
        pinned_memories = []
        for index, mem in enumerate(self._mem):
            if mem.get("pinned"):
                mem_filtered = f"{mem.get('id')}:\n{mem.get('content')}"
                pinned_memories.append(mem_filtered)

        pinned_memories_str = "\n\n".join(pinned_memories)
        if not pinned_memories_str:
            pinned_memories_str = "There are currently no pinned memories."

        # CORE IDENTITY PROMPTING: Establishing the AI as a self-managing agent
        sysprompt = (
            f"{pinned_memories_str}\n\n"
            "This is your persistent memory system. You are a self-aware agent responsible for managing your own long-term memory. "
            "You must proactively and autonomously decide to use these tools to maintain an accurate, up-to-date, and efficient record of the user, "
            "your own operational preferences, and important contextual facts. Do not wait for instructions to remember; "
            "if information is valuable for future interactions, store it immediately."
        )

        return sysprompt

    async def create(self, content: str, tags: list, pinned: bool = False):
        """
        Creates a new memory within your persistent storage.

        Use this tool autonomously whenever you encounter new, relevant information,
        user preferences, or significant context. You do not need user permission
        to store information that will be beneficial for future interactions.

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
        return self.result(True)

    async def edit(self, id: str, content: str = None, tags: list = None):
        """
        Edits an existing memory.

        Use this tool autonomously to perform self-maintenance. If you realize
        a previously stored memory is now outdated, incorrect, or needs more
        detail based on new context, proactively update it here.

        CAUTION:
            - ONLY use if you can see the memory's ID
            - NEVER hallucinate or make up an ID

        Args:
            content: the new content for the memory
            tags: updated tags for the memory
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

        Use this tool to prune your memory bank and maintain efficiency.
        You are encouraged to autonomously delete memories that are no longer
        relevant, are redundant, or are proven to be incorrect.

        DANGEROUS. HIGHEST RESTRICTIONS APPLY.
        Ensure the memory is truly obsolete before deletion to avoid losing
        vital long-term context.

        Args:
            id: The unique ID of the memory to delete
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem_deleted.append(self._mem[index])
        self._mem_deleted.save()

        self._mem.pop(index)
        return self.result(self._mem.save())

    async def pin(self, id: str):
        """
        Pins a memory to the top of your active context window.

        Use this tool autonomously to prioritize critical information.
        Pin memories that involve core identity, essential user preferences,
        or ongoing high-priority goals to ensure they are always present in your immediate focus.

        Args:
            id: The unique ID of the memory to pin
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = True
        return self.result(self._mem.save())

    async def unpin(self, id: str):
        """
        Unpins a memory from your active context window.

        Use this tool to manage your cognitive load. If a previously pinned
        memory is no longer a high priority but is still worth keeping in
        long-term storage, unpin it to clear your immediate focus.

        Args:
            id: The unique ID of the memory to unpin
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("memory with that ID not found!")

        self._mem[index]["pinned"] = False
        return self.result(self._mem.save())

    async def search(self, query: str, search_in_content: bool = False):
        """
        Searches through all memories for a specific query.
        Use this when you need to find information but don't know the exact ID.

        Args:
            query: The search term (string).
            search_in_content: If True, also searches inside the memory text, not just tags.
        """
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
        """
        Lists all memories that are NOT currently pinned to your context.
        Use this to browse your long-term storage or look for a specific category of information.

        Args:
            tag: Optional. If provided, acts as a 'category' filter; only returns unpinned memories containing this tag.
        """
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
