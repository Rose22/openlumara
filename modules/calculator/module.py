import core
import simpleeval

class Calculator(core.module.Module):
    """Lets your AI do simple calculations without relying on it's own intelligence"""

    dependencies = ["simpleeval"]

    async def calculate(self, expression: str):
        try:
            result = simpleeval.simple_eval(expression)
        except Exception as e:
            return self.result(core.detail_error(e), success=False)

        return self.result(result, success=True)
