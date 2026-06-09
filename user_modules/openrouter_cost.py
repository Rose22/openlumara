import core

# Local model (llama-server on LAN):
#   api.base_url: http://192.168.x.x:8080/v1
#   api.key: none
#   This module becomes a no-op (base_url check in __init__).
# Back to OpenRouter: restore base_url and api_key. No other changes needed.

# Read files: core/module.py, core/manager.py, core/context.py
# Hook used: _on_completion hook in manager.py

class OpenRouterCost(core.module.Module):
    """Tracks token usage and cost for OpenRouter."""

    def __init__(self, manager, is_user_module=False):
        super().__init__(manager, is_user_module)
        self.enabled = False
        self._total_cost = 0.0
        self._total_tokens = 0

        base_url = core.config.get("api", "url", "")
        if "openrouter.ai" in base_url.lower():
            self.enabled = True

    async def on_ready(self):
        if not self.enabled:
            return

        # Hook into manager's completion
        if not hasattr(self.manager, "_completion_hooks"):
            self.manager._completion_hooks = []

        self.manager._completion_hooks.append(self._on_raw)

    async def _on_raw(self, raw: dict, message: dict) -> None:
        """Hook called after an API request completes. Extracts usage and mutates the message dict."""
        usage = raw.get("usage", {})

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        cost = usage.get("cost", None)

        # In stream responses, sometimes 'cost' is provided, otherwise we leave it None
        if cost is not None:
            try:
                cost = float(cost)
                self._total_cost += cost
            except ValueError:
                cost = None

        self._total_tokens += total_tokens

        # Build the clean _usage dictionary
        _usage = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
            "cost": cost,
            "reasoning": usage.get("reasoning_tokens", None)
        }

        # Also store session totals so the frontend can retrieve them easily if needed
        # Or just append it to the message. The UI stat display can accumulate or just show per-message
        _usage["session_cost"] = self._total_cost
        _usage["session_tokens"] = self._total_tokens

        message["_usage"] = _usage
