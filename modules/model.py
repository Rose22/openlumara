import core

class Model(core.module.Module):
    """lets your AI help you switch between models"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = None

    async def on_system_prompt(self):
        """Returns a list of AI/LLM models available to switch to"""
        if not self.models:
            self.models = await self.manager.API._AI.models.list()
        models_str = ", ".join([model.id for model in self.models.data])
        current_model = self.manager.API.get_model()
        return f"Current model: {current_model}\nModels you can switch to using the models_switch() toolcall: {models_str}"

    async def on_command(self, args: list):
        if not self.models:
            self.models = await self.manager.API._AI.models.list()
        model_list = "\n".join([model.id for model in self.models.data])

        if not args:
            return f"Current model: {self.manager.API.get_model()}"

        match args[0]:
            case "switch":
                if len(args) < 2:
                    return "please provide a model to switch to"
                print(args)
                return await self.switch(args[1].strip())
            case "list":
                return model_list
            case _:
                return "valid commands are: list, switch. check /help"
    async def on_command_help(self):
        return """
/model                 show currently active model
/model list            list models
/model switch <name>   switch to model with provided name
"""
    async def switch(self, name: str):
        if not self.models:
            self.models = await self.manager.API._AI.models.list()

        found = False
        found_id = None
        for model in self.models.data:
            if model.id.lower() == name.strip().lower():
                found = True
                found_id = model.id

        if not found:
            return "model does not exist. use models_list() first"

        core.config.config["model"] = found_id
        core.config.config.save()

        self.manager.API.set_model(found_id)

        return f"model has been switched to {found_id}"

