import core

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

    async def delete(self, list_name: str):
        for category_name, category in self.data.items():
            if list_name in category.keys():
                target_category = category_name

        if not target_category:
            return self.result("that list doesn't exist")

        del(self.data[target_category][list_name])
        self.data.save()

        return self.result("list deleted!")

    async def pin(self, list_name: str):
        """Deletes a list. ONLY use this if user explicitely asks for it!"""

        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        target_list["pinned"] = True
        self.data.save()

        return self.result("list pinned!")
    async def unpin(self, list_name: str):
        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        target_list["pinned"] = False
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

    async def get(self, list_name: str):
        """retrieves the contents of a list"""

        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        output = ""
        for index, list_item in enumerate(target_list.get("items")):
                    output += f"{index+1}. {list_item}\n"

        return self.result(output)

    def _find_list(self, list_name: str):
        # find the list by it's name
        target_category = None

        for category_name, category in self.data.items():
            if list_name in category.keys():
                target_category = category_name

        if not target_category:
            return None

        return self.data[target_category][list_name]

    async def add_item(self, list_name: str, item_content: str):
        """
        Adds an item to a list. List items are 1-indexed.
        """
        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        target_list["items"].append(item_content)
        self.data.save()

        return self.result("list item added!")

    async def edit_item(self, list_name: str, index: int, item_content: str):
        """
        Edits an item in a list. List items are 1-indexed.
        """
        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        target_index = index-1 # the system prompt shows list items as 1-indexed
        if target_index < 0 or target_index >= len(target_list["items"]):
            return self.result("invalid list index", False)

        target_list["items"][target_index] = item_content
        self.data.save()

        return self.result("list item edited!")

    async def delete_item(self, list_name: str, index: int):
        """
        Deletes an item in a list. List items are 1-indexed.
        """
        target_list = self._find_list(list_name)
        if target_list == None:
            return self.result("that list doesn't exist", False)

        target_index = index-1 # the system prompt shows list items as 1-indexed
        if target_index < 0 or target_index >= len(target_list["items"]):
            return self.result("invalid list index", False)

        target_list["items"].pop(target_index)
        self.data.save()

        return self.result("list item deleted!")
