from .helper import GREETING

# lets tests observe re-execution: reload() re-runs this file in place
LOAD_COUNT = globals().get("LOAD_COUNT", 0) + 1


class DemoModule:
    name = "demo"
    header = "Demo"
