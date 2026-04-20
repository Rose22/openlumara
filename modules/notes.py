import core

class Notes(core.module.Module):
    """Lets your AI store notes in a notebook. Notes are folders with markdown files, no vendor lock-in!"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = core.storage.StorageDict("notes", "markdown")

    async def on_system_prompt(self):
        if not self.data.keys():
            return None

        categories = ", ".join(self.data.keys())
        return f"current categories containing notes: {categories}"

    async def create(self, name: str, category: str, content: str):
        """create a new note and store it within the notebook"""
        if category not in self.data.keys():
            self.data[category] = {}

        if name in self.data[category].keys():
            return self.result("note already exists! edit it instead. make sure to read it before editing it.", False)

        self.data[category][name] = content
        self.data.save()
        return self.result("note created")

    async def read(self, category: str, name: str):
        """reads a note using its name"""
        if category not in self.data.keys():
            return self.result("category doesn't exist", False)

        if name not in self.data[category].keys():
            return self.result("note does not exist", False)

        return self.result(self.data[category].get(name, "EMPTY"))

    async def edit(self, category: str, name: str, content: str):
        """edits an existing note. ALWAYS read the note first before editing."""
        if category not in self.data.keys():
            return self.result("category doesn't exist", False)

        if name not in self.data[category].keys():
            return self.result("note does not exist", False)

        self.data[category][name] = content
        self.data.save()
        return self.result("note edited")

    def _recursive_items(self, data, prefix=""):
        """Recursively iterate through nested dict items."""
        for key, value in data.items():
            current_key = f"{prefix}/{key}" if prefix else key
            if isinstance(value, dict):
                yield from self._recursive_items(value, current_key)
            else:
                yield current_key, value

    async def list(self, category: str):
        """gets all notes in a specific category"""
        if category not in self.data.keys():
            return self.result("category doesn't exist", False)

        return self.result(list(self.data.get(category, {}).keys()))

    async def search(self, query: str):
        """searches within the stored notes"""
        found = []
        for key, content in self._recursive_items(dict(self.data)):
            if query.lower() in key.lower() or query.lower() in content.lower():
                found.append({key: content})
        return self.result(found)

    async def delete(self, category: str, name: str):
        """deletes a note using its name"""
        if category not in self.data.keys():
            return self.result("category doesn't exist", False)

        if name not in self.data[category].keys():
            return self.result("note does not exist", False)

        del(self.data[category][name])

        # remove category if it's empty now
        if not self.data[category]:
            del self.data[category]

        self.data.save()
        return self.result("note deleted")
