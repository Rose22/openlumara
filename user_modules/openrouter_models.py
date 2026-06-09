import core
import asyncio
import urllib.request
import urllib.error
import json
import traceback

# Local model (llama-server on LAN):
#   api.base_url: http://192.168.x.x:8080/v1
#   api.key: none
#   This module becomes a no-op (base_url check in __init__).
# Back to OpenRouter: restore base_url and api_key. No other changes needed.

# Read files: core/module.py, core/manager.py
# Hook used: on_system_prompt(), core.module.command

class OpenRouterModels(core.module.Module):
    """Fetches and displays OpenRouter model list with pricing and capabilities."""

    def __init__(self, manager, is_user_module=False):
        super().__init__(manager, is_user_module)
        self.enabled = False
        self._models = []

        base_url = core.config.get("api", "url", "")
        if "openrouter.ai" in base_url.lower():
            self.enabled = True

    async def on_ready(self):
        if not self.enabled:
            return
        # Fetch models in background on startup to not block
        asyncio.create_task(self._fetch_models())

    async def _fetch_models(self):
        def do_fetch():
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"User-Agent": "OpenLumara"}
            )
            try:
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode())
            except Exception as e:
                core.log("openrouter_models", f"Failed to fetch models: {e}")
                return None

        try:
            data = await asyncio.to_thread(do_fetch)
            if data and isinstance(data, dict) and "data" in data:
                self._models = data["data"]
                core.log("openrouter_models", f"Loaded {len(self._models)} models from OpenRouter.")
        except Exception as e:
            core.log("openrouter_models", f"Error parsing models: {e}")

    @core.module.command("models refresh", "Refreshes the OpenRouter model list", send_to_ai=False)
    async def refresh_models(self, message):
        if not self.enabled:
            return "OpenRouter features are disabled (base_url does not contain openrouter.ai)."
        await self._fetch_models()
        return f"Refreshed! Loaded {len(self._models)} models from OpenRouter."

    async def on_system_prompt(self):
        if not self.enabled or not self._models:
            return None

        # Build condensed model list (max 50 to save tokens)
        condensed = "Available OpenRouter models (ID | Name | Context | Cost/1M prompt | Modality | Reasoning):\n"
        count = 0

        for m in self._models:
            if count >= 50:
                break

            m_id = m.get("id", "")
            name = m.get("name", "")
            context = m.get("context_length", "unknown")

            pricing = m.get("pricing", {})
            cost = pricing.get("prompt", "unknown")
            if isinstance(cost, (int, float, str)):
                try:
                    # OpenRouter gives per token cost, multiply by 1M
                    cost = float(cost) * 1_000_000
                    cost = f"${cost:.4f}"
                except ValueError:
                    pass

            arch = m.get("architecture", {})
            modality = arch.get("modality", "text")

            reasoning = "Yes" if "thinking" in m_id.lower() or "reasoning" in m_id.lower() or arch.get("reasoning") else "No"

            condensed += f"- {m_id} | {name} | {context} | {cost} | {modality} | {reasoning}\n"
            count += 1

        return condensed

    def list_openrouter_models(self):
        """Returns the full list of available OpenRouter models with their capabilities and pricing as JSON."""
        if not self.enabled:
            return self.result("OpenRouter is not configured.", success=False)
        return self.result(json.dumps(self._models))
