import core
import random

class Lists(core.module.Module):
    """
    Lets the AI manage lists for you, such as shopping lists, simple todo lists, and so on.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.data = core.storage.StorageDict("lists", "yaml")

    async def on_system_prompt(self):
        output = ""
        pinned_by_cat, unpinned_by_cat = {}, {}
        for cat, lists in self.data.items():
            for name, lst in lists.items():
                if not lst.get("items"): continue
                if lst.get("pinned"): pinned_by_cat.setdefault(cat, []).append((name, lst["items"]))
                else: unpinned_by_cat.setdefault(cat, []).append(name)
        for cat, items in pinned_by_cat.items():
            output += f"## {cat}\n"
            for name, lst_items in items:
                output += f"### {name}\n" + "\n".join(f"{i+1}. {it}" for i, it in enumerate(lst_items)) + "\n"
        if unpinned_by_cat:
            output += "---\nlists that aren't pinned:\n"
            for cat, names in unpinned_by_cat.items():
                output += f"{cat}: {', '.join(names)}\n"
        return output

    def _verify_target(self, category, list_name):
        if category not in self.data.keys():
            return False

        if list_name not in self.data[category].keys():
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

    # async def search(self, query: str, search_in_content: bool = False):
    #     """searches all lists for your query"""
    #     found_list = None
    #     for category_name, category in self.data.items():
    #         for list_name, list in category.items():
    #             for list_item in list["items"]:
    #                 for word in list_item:
    #                     if word.lower().strip() in query:
    #                         found_list = list
    #
    #     if not found_list:
    #         return self.result("no lists found")
    #
    #     output = ""
    #     for index, list_item in enumerate(found_list.get("items")):
    #                 output += f"{index+1}. {list_item}\n"
    #
    #     return self.result(output)

    async def get(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        output = ""
        for index, list_item in enumerate(self.data[category][list_name].get("items")):
                    output += f"{index+1}. {list_item}\n"

        return self.result(output)

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
        if not found_index:
            return self.result("could not find that list item", False)

        target_list["items"][found_index] = item_content
        self.data.save()

        return self.result("list item edited!")

    async def delete_item(self, category: str, list_name: str, item_starts_with: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        target_list = self.data[category][list_name]

        found_index = self._find_item(target_list["items"], item_starts_with)
        if not found_index:
            return self.result("could not find that list item", False)

        target_list["items"].pop(found_index)
        self.data.save()

        return self.result("list item deleted!")

    async def get_random_item(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        return self.result(random.choice(self.data[category][list_name]["items"]))
