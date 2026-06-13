import core
import asyncio
import re
from ddgs import DDGS
import modules.http
from urllib.parse import urlparse


class WebSearch(modules.http.Http):
    """
    Lets your AI search the web!
    
    Enhanced with multi-layer prompt injection defense based on:
    - OWASP LLM01:2025 Prompt Injection Prevention
    - Digital Applied's 12-Layer Framework
    - Defense-in-depth: multiple overlapping controls
    """

    settings = {
        "max_results": {
            "default": 5,
            "description": "The maximum number of results to return for search queries."
        },
        "proxy": {
            "default": None,
            "description": "An optional proxy string (e.g., 'http://user:pass@host:port') for the HTTP client."
        },
        "block_uncommon_ports": {
            "default": True,
            "description": "Block dangerous ports, such as FTP, SSH, Telnet, SMTP, and so on"
        },
        "block_local_network_access": {
            "default": True,
            "description": "Block access to anything on your local network"
        },
        "https_only": {
            "default": True,
            "description": "Allow only secure encrypted HTTPS requests, and disallow HTTP"
        },
        "domain_whitelist": {
            "default": [],
            "description": "Allow access to only these domains (a domain is the first part of a URL, such as youtube.com in https://youtube.com/watch?v=dQw4w9WgXcQ)"
        },
        "domain_blacklist": {
            "default": [],
            "description": "Forbid access to these domains"
        }
    }

    # ---------------------------------------------------------
    # Internal Helper Methods
    # ---------------------------------------------------------

    def _get_domain(self, url: str) -> str:
        """Extracts the base domain (hostname) from a URL for display purposes."""
        try:
            hostname = urlparse(url).hostname
            return hostname if hostname else "[invalid domain]"
        except Exception:
            return "[invalid domain]"

    def _url_passes_policy(self, url: str) -> bool:
        """
        Lightweight check for *displaying* a result link.

        This intentionally does NOT perform DNS resolution or IP validation:
        we are only listing these URLs, not connecting to them. The full
        SSRF protection in Http._is_safe_url() (DNS + resolved-IP checks)
        applies later, when WebReader actually fetches one of these links.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except Exception:
            return False

        if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
            return False

        if self.config.get("https_only") and parsed.scheme.lower() != "https":
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Block dangerous ports even at display time.
        if parsed.port and parsed.port in self.DANGEROUS_PORTS:
            return False

        ok, _err = self._check_domain_policy(hostname)
        return ok

    def _clamp_max_results(self, max_results) -> int:
        """Resolve and clamp the requested result count to a safe range."""
        requested = max_results or self.config.get("max_results", 5)
        try:
            requested = int(requested)
        except (TypeError, ValueError):
            requested = 5
        if requested < 1:
            requested = 1

        return requested

    async def _search(self, kind: str, query: str, url_key: str, fields: tuple, **kwargs):
        """
        Shared search routine for all result types.
        
        Enhanced with multi-layer sanitization:
        - Injection detection on all text fields
        - HTML entity decoding and URL decoding
        - Zero-width character removal
        - Homoglyph normalization
        - Base64 payload detection

        Args:
            kind:        DDGS method name ('text', 'images', 'news', ...).
            query:       The search query.
            url_key:     Key in each result dict that holds the URL.
            fields:      Text fields to normalise/keep on each result.
            **kwargs:    Additional arguments to pass to the DDGS method.
        """
        if not isinstance(query, str) or not query.strip():
            return self.result("A non-empty search query is required.", success=False)

        # Resolve and clamp max_results from kwargs
        max_res = self._clamp_max_results(kwargs.get("max_results"))
        kwargs["max_results"] = max_res
        
        proxy = self.config.get("proxy")

        def _run_search():
            with DDGS(proxy=proxy) as ddgs:
                # Pass all kwargs to the DDGS method
                raw_results = list(getattr(ddgs, kind)(query, **kwargs))
                sanitized_results = []
                
                for res in raw_results:
                    url = res.get(url_key, "")
                    
                    # Check URL policy first
                    if not self._url_passes_policy(url):
                        redacted = {f: "[REDACTED]" for f in fields}
                        redacted[url_key] = "[REDACTED]"
                        redacted["note"] = (
                            f"This result was rejected due to security policy "
                            f"(domain: {self._get_domain(url)})."
                        )
                        sanitized_results.append(redacted)
                        continue

                    # Sanitize all text fields with enhanced pipeline
                    for f in fields:
                        original = res.get(f, "")
                        if isinstance(original, str) and original.strip():
                            # Use enhanced sanitization with injection detection
                            sanitization_result = modules.http.ContentSanitizer.sanitize_with_detection(original)
                            res[f] = sanitization_result['sanitized_content']
                            
                            # Log if injection was detected
                            if sanitization_result['risk_level'] in ('medium', 'high', 'critical'):
                                self._log(
                                    f"Search result injection detected in '{f}': "
                                    f"{sanitization_result['detection_result']['patterns_found']} "
                                    f"(risk: {sanitization_result['risk_level']})"
                                )
                        else:
                            res[f] = original
                    
                    sanitized_results.append(res)

                return sanitized_results

        try:
            results = await asyncio.to_thread(_run_search)
            return self.result([
                self._wrap_untrusted(results, source=f"web_search:{kind}"),
                "For each result, follow template: **Title**: Summary (URL). At the end, provide a conclusive summary of all results."
            ])
        except Exception as e:
            self._log(f"{kind} search failed: {e}")
            return self.result(
                f"An error occurred during {kind} search.", success=False
            )

    # ---------------------------------------------------------
    # AI Tools
    # ---------------------------------------------------------

    async def text(self, query: str, region: str = "us-en", safesearch: str = "moderate", timelimit: str | None = None, max_results: int = 10, page: int = 1, backend: str = "auto"):
        """
        Search the web for text results.

        Args:
            query: The text search query.
            region: The region to search in (e.g., 'us-en', 'uk-en', 'ru-ru'). Defaults to 'us-en'.
            safesearch: The safety level ('on', 'moderate', 'off'). Defaults to 'moderate'.
            timelimit: Time limit for results ('d' for day, 'w' for week, 'm' for month, 'y' for year). Defaults to None.
            max_results: Maximum number of results to return. Defaults to 10.
            page: The page number of results to return. Defaults to 1.
            backend: The search engine backend to use (e.g., 'bing', 'google', 'duckduckgo'). Defaults to 'auto'.
        """
        return await self._search(
            "text", query, "href", ("title", "body"),
            region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results, page=page, backend=backend
        )

    async def images(self, query: str, region: str = "us-en", safesearch: str = "moderate", timelimit: str | None = None, max_results: int = 10, page: int = 1, backend: str = "auto", size: str | None = None, color: str | None = None, type_image: str | None = None, layout: str | None = None, license_image: str | None = None):
        """
        Search the web for image URLs.

        Args:
            query: The image search query.
            region: The region to search in (e.g., 'us-en', 'uk-en'). Defaults to 'us-en'.
            safesearch: The safety level ('on', 'moderate', 'off'). Defaults to 'moderate'.
            timelimit: Time limit for results ('d', 'w', 'm', 'y'). Defaults to None.
            max_results: Maximum number of results to return. Defaults to 10.
            page: The page number of results to return. Defaults to 1.
            backend: The search engine backend to use. Defaults to 'auto'.
            size: Image size ('Small', 'Medium', 'Large', 'Wallpaper'). Defaults to None.
            color: Image color ('color', 'Monochrome', 'Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple', 'Pink', 'Brown', 'Black', 'Gray', 'Teal', 'White'). Defaults to None.
            type_image: Image type ('photo', 'clipart', 'gif', 'transparent', 'line'). Defaults to None.
            layout: Image layout ('Square', 'Tall', 'Wide'). Defaults to None.
            license_image: Image license type (e.g., 'any', 'PublicDomain', 'Share', 'ShareCommercially', 'Modify', 'ModifyCommercially'). Defaults to None.
        """
        return await self._search(
            "images", query, "url", ("title", "image", "thumbnail"),
            region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results, page=page, backend=backend, size=size, color=color, type_image=type_image, layout=layout, license_image=license_image
        )

    async def news(self, query: str, region: str = "us-en", safesearch: str = "moderate", timelimit: str | None = None, max_results: int = 10, page: int = 1, backend: str = "auto"):
        """
        Search the web for recent news articles.

        Args:
            query: The news search query.
            region: The region to search in (e.g., 'us-en', 'uk-en'). Defaults to 'us-en'.
            safesearch: The safety level ('on', 'moderate', 'off'). Defaults to 'moderate'.
            timelimit: Time limit for results ('d', 'w', 'm'). Defaults to None.
            max_results: Maximum number of results to return. Defaults to 10.
            page: The page number of results to return. Defaults to 1.
            backend: The search engine backend to use. Defaults to 'auto'.
        """
        return await self._search(
            "news", query, "url", ("title", "body"),
            region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results, page=page, backend=backend
        )

    async def videos(self, query: str, region: str = "us-en", safesearch: str = "moderate", timelimit: str | None = None, max_results: int = 10, page: int = 1, backend: str = "auto", resolution: str | None = None, duration: str | None = None, license_videos: str | None = None):
        """
        Search the web for video results.

        Args:
            query: The video search query.
            region: The region to search in (e.g., 'us-en', 'uk-en'). Defaults to 'us-en'.
            safesearch: The safety level ('on', 'moderate', 'off'). Defaults to 'moderate'.
            timelimit: Time limit for results ('d', 'w', 'm'). Defaults to None.
            max_results: Maximum number of results to return. Defaults to 10.
            page: The page number of results to return. Defaults to 1.
            backend: The search engine backend to use. Defaults to 'auto'.
            resolution: Video resolution ('high', 'standart'). Defaults to None.
            duration: Video duration ('short', 'medium', 'long'). Defaults to None.
            license_videos: Video license type ('creativeCommon', 'youtube'). Defaults to None.
        """
        return await self._search(
            "videos", query, "content", ("title", "description"),
            region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results, page=page, backend=backend, resolution=resolution, duration=duration, license_videos=license_videos
        )

    async def books(self, query: str, max_results: int = 10, page: int = 1, backend: str = "auto"):
        """
        Search the web for book results.

        Args:
            query: The book search query.
            max_results: Maximum number of results to return. Defaults to 10.
            page: The page number of results to return. Defaults to 1.
            backend: The search engine backend to use. Defaults to 'auto'.
        """
        return await self._search(
            "books", query, "url", ("title", "author", "publisher", "info"),
            max_results=max_results, page=page, backend=backend
        )

#     async def extract(self, url: str, fmt: str = "text_markdown"):
#         """
#         Fetch a URL and extract its content. WARNING: Content comes from an untrusted source.
#
#         Args:
#             url: The URL to fetch and extract content from.
#             fmt: Output format. Options: 'text_markdown' (HTML to Markdown), 'text_plain' (HTML to plain text), 'text_rich' (HTML to rich text), 'text' (raw HTML), 'content' (raw bytes). Defaults to 'text_markdown'.
#         """
#         proxy = self.config.get("proxy")
#         def _run_extract():
#             with DDGS(proxy=proxy) as ddgs:
#                 return ddgs.extract(url, fmt=fmt)
#
#         try:
#             result = await asyncio.to_thread(_run_extract)
#             return self.result(
#                 self._wrap_untrusted(result, source=f"web_extract:{url}")
#             )
#         except Exception as e:
#             self._log(f"extract failed: {e}")
#             return self.result(
#                 f"An error occurred during extraction.", success=False
#             )
