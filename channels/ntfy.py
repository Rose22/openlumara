import core
import httpx

class Ntfy(core.channel.Channel):
    """
    A special channel that provides push notifications on your phone via NTFY.
    See the channel's settings for setup guidance
    """

    settings = {
        "server": {
            "type": "string",
            "description": "The URL to your server. You can either [host your own server](https://docs.ntfy.sh/install/) (recommended for total privacy), or use [NTFY's official server](https://ntfy.sh/). You then need to install an app on your phone (search for ntfy in the Play Store or App Store), and subscribe it to either your locally hosted server or the public ntfy.sh server.",
            "default": "http://localhost:3050"
        },
        "topic": {
            "type": "string",
            "description": "Topic you want the notifications to be sent to. If using ntfy's public server, this will need to be a unique topic that isn't taken by others, and preferably something random because it's basically like a password! If using your own self hosted server, you can just use anything you want.",
            "default": "openlumara"
        },
        "title": {
            "type": "string",
            "description": "What title should show up in your notifications, above the notification text",
            "default": "OpenLumara"
        }
    }

    dependencies = ["httpx"]

    async def run(self):
        # this is not a normal channel lol
        pass

    async def on_push(self, message: dict):
        content = message.get("content")
        if not content:
            return False

        server = self.config.get("server").rstrip('/')
        topic = self.config.get("topic")
        url = f"{server}/{topic}"

        # prepare headers
        headers = {
            "Title": self.config.get("title"),
            "Priority": "default"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, content=content, headers=headers, timeout=5.0)
                
                if response.status_code in (200, 201, 204):
                    self.log(self.name, "Sent push message to NTFY")
                else:
                    self.log(self.name, f"Failed to send NTFY notification. Status: {response.status_code}")
        except Exception as e:
            self.log(self.name, f"Error forwarding to NTFY: {core.detail_error(e)}")

        return True
