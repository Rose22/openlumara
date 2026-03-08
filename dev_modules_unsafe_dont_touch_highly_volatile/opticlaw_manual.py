import core

class OpticlawManual(core.module.Module):
    # NOTE TO SELF: replace with more generalized Documentation toolset for AI to use, bundle openclaw docs with the app
    async def on_system_prompt(self):
        return f"""
    You are running inside OptiClaw, an AI agent framework that lets you act autonomously.

    Opticlaw's official website is at https://github.com/Rose22/opticlaw
    User can configure opticlaw using the config file. Opticlaw's config file is at {core.get_data_path()}/config.yml

    You are aware of how many words are taking up your context window. This can be used to keep token use low.

    The commands available to user are:
    {core.channel.get_help()}
    """

    # TODO: add builtin documentation that can be consulted by the AI and explained to the user
