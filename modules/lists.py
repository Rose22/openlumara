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
        # display all pinned lists all fancy in the prompt
        output = ""
        #output += "Pinned lists (you can see their full contents):\n"
        unpinned_lists = {}
        for category_name, lists in self.data.items():
            category_header_displayed = False

            for list_name, list in lists.items():
                if not list.get("pinned"):
                    if category_name not in unpinned_lists.keys():
                        unpinned_lists[category_name] = []

                    unpinned_lists[category_name].append(list_name)
                    continue

                if not list.get("items"):
                    continue

                if not category_header_displayed:
                    output += f"## {category_name}\n"
                    category_header_displayed = True

                output += f"### {list_name}\n"
                for index, list_item in enumerate(list.get("items")):
                    output += f"{index+1}. {list_item}\n"
                output += "\n"

        # display unpinned lists as just their names
        if unpinned_lists:
            output += "---\nlists that aren't pinned:\n"
            for category_name, items in unpinned_lists.items():
                items_str = ", ".join(items)
                output += f"{category_name}: {items_str}\n"

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
        """Deletes a list. ONLY use this if user explicitely asks for it!"""

        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        del(self.data[category][list_name])
        # check if the category still contains any lists. if not, delete the category itself
        if not self.data[category]:
            del(self.data[category])

        self.data.save()

        return self.result("list deleted!")

    async def pin(self, category: str, list_name: str):
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
        """retrieves the contents of a list"""

        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        output = ""
        for index, list_item in enumerate(self.data[category][list_name].get("items")):
                    output += f"{index+1}. {list_item}\n"

        return self.result(output)

    async def add_item(self, category: str, list_name: str, item_content: str):
        """
        Adds an item to a list. List items are 1-indexed.
        """
        self._create_if_non_existent(category, list_name)

        target_list = self.data[category][list_name]
        target_list["items"].append(item_content)
        self.data.save()

        return self.result("list item added!")

    async def edit_item(self, category: str, list_name: str, index: int, item_content: str):
        """
        Edits an item in a list. List items are 1-indexed.
        """
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        target_list = self.data[category][list_name]
        target_index = index-1 # the system prompt shows list items as 1-indexed
        if target_index < 0 or target_index >= len(target_list["items"]):
            return self.result("invalid list index", False)

        target_list["items"][target_index] = item_content
        self.data.save()

        return self.result("list item edited!")

    async def delete_item(self, category: str, list_name: str, index: int):
        """
        Deletes an item in a list. List items are 1-indexed.
        """
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        target_list = self.data[category][list_name]
        target_index = index-1 # the system prompt shows list items as 1-indexed
        if target_index < 0 or target_index >= len(target_list["items"]):
            return self.result("invalid list index", False)

        target_list["items"].pop(target_index)
        self.data.save()

        return self.result("list item deleted!")

    async def get_random_item(self, category: str, list_name: str):
        if not self._verify_target(category, list_name):
            return self.result("that list doesn't exist")

        return self.result(random.choice(self.data[category][list_name]["items"]))
