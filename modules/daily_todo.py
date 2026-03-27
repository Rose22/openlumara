import core
import datetime

class DailyTodo(core.module.Module):
    """manages a daily todo list that resets automatically every day"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # We use StorageDict to store both the date and the list of tasks.
        self.storage = core.storage.StorageDict(f"daily_todo", "json")

    def _check_date(self):
        """
        Checks if the stored date matches today.
        If not (or if it's a brand new list), it clears the tasks and updates the date.
        This runs automatically before any read/write operation.
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # If the date differs from today, reset the list
        if self.storage.get("date") != today:
            self.storage["date"] = today
            self.storage["tasks"] = []
            self.storage.save()

    # ---------------------------------------------------------
    # AI Tools (Async methods for the AI to call)
    # ---------------------------------------------------------

    async def add_task(self, task: str):
        """
        Adds a new task to today's todo list.
        Use this when the user asks to remember a task or add something to their list.
        """
        self._check_date()

        if "tasks" not in self.storage:
            self.storage["tasks"] = []

        self.storage["tasks"].append(task)
        self.storage.save()
        return self.result(f"Task added: '{task}'")

    async def remove_task(self, index: int):
        """
        Removes a task from the list by its index number (1-based).
        Use this when the user wants to delete or remove a task.
        """
        self._check_date()

        tasks = self.storage.get("tasks", [])

        # Adjust for 1-based index (humans usually count from 1)
        if 1 <= index <= len(tasks):
            removed_task = tasks.pop(index - 1)
            self.storage["tasks"] = tasks
            self.storage.save()
            return self.result(f"Removed task: '{removed_task}'")
        else:
            return self.result(f"Invalid task number {index}. There are {len(tasks)} tasks.", False)

    async def edit_task(self, index: int, new_text: str):
        """
        Edits an existing task by its index number (1-based).
        Use this when the user wants to change the wording of a task.
        """
        self._check_date()

        tasks = self.storage.get("tasks", [])

        if 1 <= index <= len(tasks):
            old_task = tasks[index - 1]
            tasks[index - 1] = new_text
            self.storage["tasks"] = tasks
            self.storage.save()
            return self.result(f"Updated task {index} from '{old_task}' to '{new_text}'")
        else:
            return self.result(f"Invalid task number {index}. There are {len(tasks)} tasks.", False)

    async def list_tasks(self):
        """
        Lists all tasks currently on the todo list.
        Use this when the user asks what is on their list or what they have to do today.
        """
        self._check_date()

        tasks = self.storage.get("tasks", [])
        date_str = self.storage.get("date", "today")

        if not tasks:
            return self.result("The todo list is currently empty.")

        response = f"Todo list for {date_str}:\n"
        for i, task in enumerate(tasks, 1):
            response += f"{i}. {task}\n"

        return self.result(response)

    # ---------------------------------------------------------
    # User Commands (Decorated methods for direct user interaction)
    # ---------------------------------------------------------

    @core.module.command("todo")
    async def cmd_list(self, args):
        """list tasks for today"""
        return await self.list_tasks()

    @core.module.command("add", temporary=True)
    async def cmd_add(self, args):
        """add a task to the list"""
        if not args:
            return "Please specify a task to add."
        return await self.add_task(" ".join(args))

    @core.module.command("remove", temporary=True)
    async def cmd_remove(self, args):
        """remove a task by its number"""
        if not args:
            return "Please specify a task number to remove."
        try:
            return await self.remove_task(int(args[0]))
        except ValueError:
            return "Please provide a valid number."

    @core.module.command("edit", temporary=True)
    async def cmd_edit(self, args):
        """edit a task by its number"""
        if len(args) < 2:
            return "Usage: edit [number] [new task text]"
        try:
            return await self.edit_task(int(args[0]), " ".join(args[1:]))
        except ValueError:
            return "Please provide a valid number."
