import core
import asyncio
import requests
import aiohttp
import urllib.parse
import re
import modules.http

# we base off the existing HTTP module in order to support all its security features
class WebReader(modules.http.Http):
    """
    Lets your AI read the content of pages on the web
    """

    # ---------------------------------------------------------
    # Internal Helper Methods
    # ---------------------------------------------------------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _remove_duplicates(self, lst: list) -> list:
        """Removes duplicates from a list while preserving order."""
        new_lst = []
        for item in lst:
            if item not in new_lst:
                new_lst.append(item)
        return new_lst

    async def _process_webpage(self, html: bytes):
        from bs4 import BeautifulSoup
        output = {}
        soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

        try:
            output["title"] = soup.find("title").get_text().strip()
        except AttributeError:
            pass

        output["headers"] = []
        for header in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            output["headers"].append(header.get_text().strip())
        if not output["headers"]:
            del output["headers"]

        output["paragraphs"] = []
        for para in soup.find_all("p"):
            output["paragraphs"].append(para.get_text().strip())
        if not output["paragraphs"]:
            del output["paragraphs"]

        output["images"] = []
        for image in soup.find_all("img"):
            if image.get("alt"):
                output["images"].append(image.get("alt"))
        if not output["images"]:
            del output["images"]

        for category in list(output.keys()):
            if category == "title":
                continue
            output[category] = self._remove_duplicates(output[category])

        if "headers" not in output and "paragraphs" not in output:
            output["classes"] = {}
            for class_name in ("content", "description", "title", "text", "article"):
                class_items = []
                for element in soup.find_all(class_=re.compile(rf"\b{class_name}\b")):
                    if element.text.strip():
                        class_items.append(element.text.strip())
                for element in soup.find_all(id=re.compile(rf"\b{class_name}\b")):
                    if element.text.strip():
                        class_items.append(element.text.strip())

                if class_items:
                    output["classes"][class_name] = self._remove_duplicates(class_items)

            if not output["classes"]:
                del output["classes"]
                output["urls"] = self._remove_duplicates([a["href"] for a in soup.find_all("a", href=True)])
                if not output["urls"]:
                    del output["urls"]
                    output["message"] = "nothing could be scraped from the page!"

        return output

    # ---------------------------------------------------------
    # AI Tools
    # ---------------------------------------------------------

    async def read(self, path: str):
        """Processes a URL and scrapes its content."""
        try:
            url_parser = urllib.parse.urlparse(path)
            if url_parser.scheme not in ["http", "https"]:
                return self.result("Invalid URL. Please provide a valid http or https link.", False)

            domain = url_parser.netloc

            result = await self._make_request(
                requests.get,
                path,
                include_content=True
            )

            data = result.get("content")
            if not isinstance(data, dict):
                return self.result(data, False)

            file_content = data.get("content", "")

            output_data = await self._process_webpage(file_content)

            return self.result(output_data, success=True)

        except Exception as e:
            return self.result(f"error {e}", False)

    async def read_multiple(self, paths: list):
        """Processes multiple URLs in parallel."""
        semaphore = asyncio.Semaphore(self.config.get("max_concurrent_tasks", 4))

        async def handle_one(p):
            async with semaphore:
                path_str = p["path"] if isinstance(p, dict) else p
                try:
                    return await self.read(path_str)
                except Exception as e:
                    return {"path": path_str, "error": str(e)}

        tasks = [handle_one(p) for p in paths]
        results = await asyncio.gather(*tasks)

        return self.result(results)
