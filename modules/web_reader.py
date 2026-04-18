import core
import asyncio
import aiohttp
import urllib.parse
import re

class WebReader(core.module.Module):
    """
    Lets your AI read the content of pages on the web
    """

    settings = {
        "max_concurrent_tasks": 4
    }

    # ---------------------------------------------------------
    # Internal Helper Methods
    # ---------------------------------------------------------

    async def _http_request(self, url: str) -> bytes:
        """Internal helper to fetch remote content."""
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3"}
        ) as session:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    raise Exception(f"Request failed with status {response.status}")
                return await response.read()

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

    async def read(self, path: str, purpose: str, memory: str, multi: bool = False):
        """
        Processes a URL and scrapes its content.
        """
        try:
            url_parser = urllib.parse.urlparse(path)
            if url_parser.scheme not in ["http", "https"]:
                return self.result(None, error="Invalid URL. Please provide a valid http or https link.", success=False)

            domain = url_parser.netloc

            file_content = await self._http_request(path)
            output_data = await self._process_webpage(file_content)

            result_data = {
                "data": output_data,
            }

            if not multi:
                result_data["ai_instructions"] = {
                    "important_details": memory,
                    "purpose_of_request": purpose,
                }
                return self.result(result_data, success=True)
            return result_data

        except Exception as e:
            return self.result({"error": str(e)}, error=str(e), success=False)

    async def read_multiple(self, paths: list, purpose: str, memory: str):
        """Processes multiple URLs in parallel."""
        semaphore = asyncio.Semaphore(self.config.get("max_concurrent_tasks", 4))

        async def handle_one(p):
            async with semaphore:
                path_str = p["path"] if isinstance(p, dict) else p
                try:
                    return await self.read(path_str, purpose, memory, multi=True)
                except Exception as e:
                    return {"path": path_str, "error": str(e)}

        tasks = [handle_one(p) for p in paths]
        results = await asyncio.gather(*tasks)

        return {
            "results": results,
            "ai_instructions": {
                "important_details": memory,
                "purpose_of_request": f"{purpose}. Include links to all sources.",
            },
        }
