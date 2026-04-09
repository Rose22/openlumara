import core
import core.module

def get_all(respect_config: bool = True):
    import modules
    import user_modules
    return core.module.load([modules, user_modules], core.module.Module, respect_config=respect_config)
