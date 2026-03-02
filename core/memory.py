import core
import json
import datetime

class Memory(core.storage.Storage):
    """manages the AI's memory"""
    # TODO: rewrite in progress

    def create(self, content: str, tags: list, pinned: bool = False):
        mem = {
            "content": content,
            "tags": tags,
            "pinned": pinned,
            "date_created": datetime.datetime.now().isoformat()
        }
        self.append(mem)
        self.save()

    def edit(self, index: int, content: str = None, tags: list = None):
        if index > len(self) or index < 0:
            return False

        if content:
            self[index]["content"] = content
        if tags:
            self[index]["tags"] = tags

        self.save()

    def delete(self, index: int):
        if index >= len(self) or index < 0:
            print("index not found")
            return False
        self.pop(index)
        self.save()
        return True

    def pin(self, index: int):
        if index >= len(self) or index < 0:
            return False
        self[index]["pinned"] = True
        self.save()
        return True
    def unpin(self, index: int):
        if index >= len(self) or index < 0:
            return False
        self[index]["pinned"] = False
        self.save()
        return True

    def get_pinned(self):
        found = []
        for index, mem in enumerate(self):
            if mem.get("pinned"):
                # add ID to it.. ID = index in the list
                mem_copy = mem.copy()
                mem_copy["id"] = index
                found.append(mem_copy)

        return found

    def search(self, query: str, search_in_content: bool = False):
        results = []
        query_lower = query.lower()

        for index, mem in enumerate(self):
            mem_copy = mem.copy()
            mem_copy["id"] = index

            # Check tags: split tags into words and check if any word is in the query
            match_found = False
            tags = mem.get("tags", [])

            for tag in tags:
                # Split tag into words and check if any word exists in the query
                if any(word in query_lower for word in tag.lower().split()):
                    match_found = True
                    break

            # Check content only if no tag match found
            if not match_found and search_in_content:
                content = mem.get("content", "")
                if content and query_lower in content.lower():
                    match_found = True

            if match_found:
                results.append(mem_copy)

        return results
