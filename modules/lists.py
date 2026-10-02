import core
import random

class Lists(core.module.Module):
    """
    Lets the AI manage lists for you, such as shopping lists, simple todo lists, and so on.
    """

    settings = {
        "insert_system_prompt": {
            "description": "Whether to put pinned lists in the system prompt. This will make your AI aware of pinned lists and their content at all times! So you can simply ask your AI to pin one of your lists, and then it will always know what's in it. Careful though, this can blow up context size fast, depending on the list!",
            "default": True
        },
        "max_pinned_lists": {
            "default": 10,
            "depends": "insert_system_prompt"
        }
    }

    async def on_ready(self):
        self.data = core.storage.StorageDict("lists", "yaml")

    async def on_system_prompt(self):
        if not self.config.get("insert_system_prompt"):
            return None

        output = ""
        pinned_by_cat, unpinned_by_cat = {}, {}
        count = 1

        for cat, lists in reversed(self.data.items()):
            for name, lst in lists.items():
                if count > self.config.get("max_pinned_lists"):
                    break

                count += 1
                if not lst.get("items"): continue
                if lst.get("pinned"): pinned_by_cat.setdefault(cat, []).append((name, lst["items"]))
                else: unpinned_by_cat.setdefault(cat, []).append(name)

        for cat, items in pinned_by_cat.items():
            output += f"## {cat}\n"
            for name, lst_items in items:
                output += f"### {name}\n" + "\n".join(f"- {it}" for it in lst_items) + "\n"
        if unpinned_by_cat:
            output += "---\nlists that aren't pinned:\n"
            for cat, names in unpinned_by_cat.items():
                output += f"{cat}: {', '.join(names)}\n"

        return output

    def _verify_target(self, category, list_name):
        if category not in self.data:
            return False
            
        if list_name not in self.data.get(category, {}):
            return False

        return True

    def _create_if_non_existent(self, category, list_name):
        if not self._verify_target(category, list_name):
            if category not in self.data.keys():
                self.data[category] = {}

            self.data[category][list_name] = {"items": [], "pinned": False}
            self.data.save()
            return True

        return False

    async def create(self, category: str, name: str, items: list = None, pinned: bool = False):
        if category not in self.data.keys():
            self.data[category] = {}

        if name in self.data[category].keys():
            return self.result("list already exists!", False)

        if not items:
            items = []

        self.data[category][name] = {"items": items, "pinned": pinned}
        self.data.save()

        return self.result("list created!")

#     async def rename(self, name: str, new_name: str):
#         target_list = self._find_list(list_name)
#         if target_list == None:
#             return self.result("that list doesn't exist", False)
#
#         del(target_list)
#         self.data.save()
#
#         return self.result("list deleted!")

    async def delete(self, category: str, list_name: str):
        """Deletes a list. ONLY use if user explicitly asks."""
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        del(self.data[category][list_name])
        # check if the category still contains any lists. if not, delete the category itself
        if not self.data[category]:
            del(self.data[category])

        self.data.save()

        return self.result("list deleted!")

    async def pin(self, category: str, list_name: str):
        """Pins a list to the top of your context."""
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        self.data[category][list_name]["pinned"] = True
        self.data.save()

        return self.result("list pinned!")
    async def unpin(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        self.data[category][list_name]["pinned"] = False
        self.data.save()

        return self.result("list unpinned!")

    async def search(self, query: str):
        """Searches all lists for your query: matches both list names and individual list items, ranked by relevance."""
        self.data.load()

        list_entries = []
        item_entries = []
        for category_name, category in self.data.items():
            if not isinstance(category, dict):
                continue
            for list_name, lst in category.items():
                if not isinstance(lst, dict):
                    continue

                items = [i for i in lst.get("items", []) if isinstance(i, str) and i.strip()]
                list_entries.append({"name": f"[{category_name}] {list_name}", "items": len(items)})
                for item in items:
                    item_entries.append({"category": category_name, "list": list_name, "item": item})

        list_results = await core.search.search(list_entries, query, field_weights={"name": 1.0}, top_n=5)
        item_results = await core.search.search(item_entries, query, field_weights={"item": 1.0}, top_n=15)

        if isinstance(list_results, str):
            return self.result(list_results)
        if isinstance(item_results, str):
            return self.result(item_results)

        if not list_results and not item_results:
            return self.result(f"no lists or list items found matching '{query}'")

        lines = []
        if list_results:
            lines.append("lists matching the query:")
            for hit in list_results:
                entry = hit["entry"]
                lines.append(f"- {entry['name']} ({entry['items']} items, score {hit['score']:.2f})")
        if item_results:
            lines.append("list items matching the query:")
            for hit in item_results:
                entry = hit["entry"]
                lines.append(f"- [{entry['category']}] {entry['list']}: {entry['item']} (score {hit['score']:.2f})")

        return self.result("\n".join(lines))

    async def get(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        return self.result(self.data[category][list_name].get("items"))

    def _find_item(self, items: list, starts_with: str):
        for index, item in enumerate(items):
            if item.strip().lower().startswith(starts_with.strip().lower()):
                return index
        return None

    async def add_item(self, category: str, list_name: str, item_content: str):
        """adds item to list. creates list if nonexistent."""
        self._create_if_non_existent(category, list_name)

        target_list = self.data[category][list_name]
        target_list["items"].append(item_content)
        self.data.save()

        return self.result("list item added!")

    async def edit_item(self, category: str, list_name: str, item_starts_with: str, item_content: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        target_list = self.data[category][list_name]

        found_index = self._find_item(target_list["items"], item_starts_with)
        if found_index is None:
            return self.result("could not find that list item", False)

        target_list["items"][found_index] = item_content
        self.data.save()

        return self.result("list item edited!")

    async def delete_item(self, category: str, list_name: str, item_starts_with: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        target_list = self.data[category][list_name]

        found_index = self._find_item(target_list["items"], item_starts_with)
        if found_index is None:
            return self.result("could not find that list item", False)

        target_list["items"].pop(found_index)
        self.data.save()

        return self.result("list item deleted!")

    async def get_random_item(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        return self.result(random.choice(self.data[category][list_name]["items"]))
