import core
import urllib.request
import urllib.parse
import json
import ast
import re

class DevTools(core.module.Module):
    """
    Module providing developer tools: YouTube search, file AST extraction, and GitHub search.
    """

    async def on_ready(self):
        core.log("dev_tools", "Developer Tools Module loaded.")

    def search_youtube(self, query: str):
        """
        Searches YouTube for videos matching the query.

        Args:
            query (str): The search term.
        """
        try:
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')

            # Extract video IDs using a simple regex
            video_ids = re.findall(r"watch\?v=(\S{11})", html)

            # Remove duplicates while preserving order
            seen = set()
            unique_ids = []
            for vid in video_ids:
                if vid not in seen:
                    seen.add(vid)
                    unique_ids.append(vid)

            if not unique_ids:
                return self.result("No videos found.")

            # Return top 5 results
            results = []
            for vid in unique_ids[:5]:
                results.append(f"https://www.youtube.com/watch?v={vid}")

            return self.result("\n".join(results))
        except Exception as e:
            return self.result(f"Error searching YouTube: {e}", success=False)

    def get_file_ast(self, filepath: str):
        """
        Parses a local Python file and extracts its Abstract Syntax Tree (classes and functions).
        Useful for understanding code structure without reading the full source.

        Args:
            filepath (str): The path to the Python file.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            # A cleaner approach for classes and functions
            output = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    output.append(f"Class: {node.name}")
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                            output.append(f"  Method: {item.name}")
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    output.append(f"Function: {node.name}")

            if not output:
                return self.result("No classes or functions found in file.")

            return self.result("\n".join(output))
        except Exception as e:
            return self.result(f"Error parsing file: {e}", success=False)

    def search_github(self, query: str):
        """
        Searches GitHub repositories using the public GitHub API.

        Args:
            query (str): The search term.
        """
        try:
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&per_page=5"
            req = urllib.request.Request(url, headers={'User-Agent': 'OpenLumara-Agent'})

            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))

            if 'items' not in data or not data['items']:
                return self.result("No repositories found.")

            results = []
            for item in data['items']:
                results.append(f"{item['full_name']} - {item['html_url']}\nDescription: {item['description']}\nStars: {item['stargazers_count']}")

            return self.result("\n\n".join(results))
        except Exception as e:
            return self.result(f"Error searching GitHub: {e}", success=False)
