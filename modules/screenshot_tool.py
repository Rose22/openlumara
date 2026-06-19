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
            
            # Use a hash of the image for the filename to avoid duplicates and keep it clean
            image_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size, output=None)
            img_hash = hashlib.md5(image_bytes).hexdigest()
            filename = f"mimi_spy_{img_hash}.png"
            
            # Ensure screenshots directory exists
            screenshot_dir = "data/screenshots"
            if not os.path.exists(screenshot_dir):
                os.makedirs(screenshot_dir, exist_ok=True)
            
            full_path = os.path.join(screenshot_dir, filename)
            with open(full_path, "wb") as f:
                f.write(image_bytes)
            
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # --- CHANGE DETECTION LOGIC ---
            if self.last_screenshot_hash is not None and img_hash == self.last_screenshot_hash:
                # No change detected! 
                return self.result("No change detected since the last screenshot. Nothing new to see!")

            # Update the hash for next time and return the image
            self.last_screenshot_hash = img_hash
            return self.result(base64_image)
            
    except Exception as e:
        return self.result(f"Error taking screenshot: {str(e)}", success=False)
