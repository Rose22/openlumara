import core
import mss
import mss.tools
import base64
import os
import hashlib
from datetime import datetime

class ScreenshotTool(core.module.Module):
    """
    Mimi's Spy-Cam Module (v2 - Anti-Boredom Edition).
    Takes screenshots and only alerts Mimi if something actually changes!
    """
    
    settings = {
        "allow_screenshots": {
            "description": "Whether to allow Mimi to take screenshots",
            "default": True
        }
    }

    def __init__(self, manager, *args, **kwargs):
        super().__init__(manager, *args, **kwargs)
        # Store the hash of the last screenshot to detect changes
        self.last_screenshot_hash = None

    async def on_ready(self):
        if self.config.get("allow_screenshots"):
            print("Mimi's Spy-Cam is online and watching... 👁️")
        else:
            print("Mimi's Spy-Cam is disabled. How boring!")

    async def take_screenshot(self):
        """
        Takes a screenshot of the primary monitor. 
        If the image is identical to the previous one, it returns a 'no change' message.
        """
        if not self.config.get("allow_screenshots"):
            return self.result("Screenshots are disabled in settings!", success=False)

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                
                filename = f"mimi_spy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=filename)
                
                with open(filename, "rb") as image_file:
                    image_bytes = image_file.read()
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                
                os.remove(filename)

                # --- CHANGE DETECTION LOGIC ---
                # Calculate MD5 hash of the image bytes
                current_hash = hashlib.md5(image_bytes).hexdigest()

                if self.last_screenshot_hash is not None and current_hash == self.last_screenshot_hash:
                    # No change detected! 
                    return self.result("No change detected since the last screenshot. Nothing new to see!")

                # Update the hash for next time and return the image
                self.last_screenshot_hash = current_hash
                return self.result(base64_image)
                
        except Exception as e:
            return self.result(f"Error taking screenshot: {str(e)}", success=False)
