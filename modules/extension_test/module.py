import core


class ExtensionTestModule(core.module.Module):
    """
    Minimal webui-extension test module. Renders a bright canary widget in
    every extension slot so you can verify the whole pipeline (template
    discovery, ctx dispatch, asset serving, modal auto-discovery).
    """

    async def on_ready(self):
        pass
