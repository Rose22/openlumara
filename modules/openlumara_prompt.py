import core

class OpenlumaraPrompt(core.module.Module):
    """Makes the AI aware of OpenLumara itself"""

    _header = "agent_platform"

    async def on_system_prompt(self):
        return """
You are running on an AI Agent Platform called OpenLumara. You are autonomous and can use the tools at your disposal to perform actions on behalf of the user.
"""
