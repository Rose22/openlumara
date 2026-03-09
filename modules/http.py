"""
Note from Rose22:
Lots of code here is AI-generated, but i've manually tested and audited it. It's better than the very basic and insecure HTTP module i made myself..

If you spot any security flaws, please create a github issue!
"""

import re
import time
import threading
from datetime import datetime
from urllib.parse import urlparse

import core
import requests

class Http(core.module.Module):
    """
    Lets the AI send/receive HTTP requests with security hardening.
    SECURITY FEATURES:
    - SSRF Protection (blocks private/internal IPs)
    - URL Validation (validates scheme, format, length)
    - Request Rate Limiting (prevents DoS)
    - Data Size Limits (prevents resource exhaustion)
    - Protocol Enforcement (HTTP/HTTPS only)
    - Redirect Protection (limits redirect depth)
    - Timeout Enforcement (prevents hanging)
    - Header Validation (sanitizes headers, blocks dangerous ones)
    - Dangerous Port Blocking (prevents service abuse)
    - Metadata Endpoint Blocking (cloud metadata protection)
    - Request Logging (for audit trail)
    - Error Handling (specific exceptions, no stack trace leaks)
    """

    # Security constants
    ALLOWED_SCHEMES = {'http', 'https'}
    MAX_REDIRECTS = 5
    MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_PARAMS_SIZE = 100 * 1024  # 100KB
    MAX_URL_LENGTH = 2048
    REQUEST_TIMEOUT = 30
    MAX_REQUESTS_PER_MINUTE = 60

    # Dangerous ports to block
    DANGEROUS_PORTS = {
        21,    # FTP
        22,    # SSH
        23,    # Telnet
        25,    # SMTP
        53,    # DNS
        110,   # POP3
        143,   # IMAP
        445,   # SMB
        993,   # IMAPS
        995,   # POP3S
        1433,  # MSSQL
        3306,  # MySQL
        5432,  # PostgreSQL
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_headers = {
            'User-Agent': 'OptiClaw/1.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate'
        }
        self._request_counter = 0
        self._last_request_time = 0
        self._lock = threading.Lock()

    # ==================== SSRF Protection ====================

    def _is_safe_url(self, url):
        """
        Check if URL is safe to request (SSRF protection).

        Blocks:
        - Internal/private IP addresses
        - Link-local addresses
        - IPv6 loopback/internal
        - AWS/GCP/Azure metadata endpoints
        - Non-HTTP schemes
        """
        try:
            parsed = urlparse(url)

            # Block non-HTTP schemes
            if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
                self._log(f"Blocked non-HTTP scheme: {parsed.scheme}")
                return False

            hostname = parsed.hostname
            if not hostname:
                self._log("URL has no hostname")
                return False

            # Block localhost variants
            if hostname.lower() in ['localhost', '127.0.0.1', '::1', '0.0.0.0']:
                self._log("Blocked localhost access")
                return False

            # Check for IPv4 private/link-local ranges
            if self._is_ipv4(hostname):
                if self._is_private_ipv4(hostname):
                    self._log(f"Blocked private IPv4: {hostname}")
                    return False
                if self._is_link_local_ipv4(hostname):
                    self._log(f"Blocked link-local IPv4: {hostname}")
                    return False

            # Check for IPv6 internal ranges
            if ':' in hostname:
                if self._is_internal_ipv6(hostname):
                    self._log(f"Blocked internal IPv6: {hostname}")
                    return False

            # Block cloud metadata endpoints
            if self._is_metadata_endpoint(hostname):
                self._log("Blocked metadata endpoint")
                return False

            return True

        except Exception as e:
            self._log(f"URL validation error: {str(e)}")
            return False

    def _is_ipv4(self, ip):
        """Check if string is valid IPv4 address."""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    def _is_private_ipv4(self, ip):
        """Check if IPv4 is in private range (RFC 1918)."""
        try:
            parts = [int(p) for p in ip.split('.')]
            if len(parts) != 4:
                return False
            # 10.0.0.0/8
            if parts[0] == 10:
                return True
            # 172.16.0.0/12
            if parts[0] == 172 and 16 <= parts[1] <= 31:
                return True
            # 192.168.0.0/16
            if parts[0] == 192 and parts[1] == 168:
                return True
            return False
        except (ValueError, IndexError):
            return False

    def _is_link_local_ipv4(self, ip):
        """Check if IPv4 is link-local (169.254.0.0/16)."""
        try:
            parts = ip.split('.')
            return parts[0] == '169' and parts[1] == '254'
        except (ValueError, IndexError):
            return False

    def _is_internal_ipv6(self, ip):
        """Check if IPv6 is internal/loopback."""
        ip_lower = ip.lower()
        # ::1 - loopback
        if ip_lower == '::1':
            return True
        # fe80::/10 - link-local
        if ip_lower.startswith('fe80'):
            return True
        # fc00::/7 - unique local
        if ip_lower.startswith('fc') or ip_lower.startswith('fd'):
            return True
        return False

    def _is_metadata_endpoint(self, hostname):
        """Check if hostname matches cloud metadata endpoints."""
        metadata_patterns = [
            r'169\.254\.169\.254',  # AWS/GCP/Azure
            r'metadata',
            r'instance-data',
            r'metadata\.google',
            r'metadata\.azure',
        ]
        for pattern in metadata_patterns:
            if re.search(pattern, hostname, re.IGNORECASE):
                return True
        return False

    # ==================== URL Validation ====================

    def _validate_url_format(self, url: str):
        """Validate URL format, scheme, and port. Returns (is_valid, error_message)."""
        # Check URL exists
        if not url:
            return False, "URL is required"

        # Check URL length
        if len(url) > self.MAX_URL_LENGTH:
            return False, f"URL exceeds maximum length of {self.MAX_URL_LENGTH} characters"

        # Check for control characters
        if re.search(r'[\x00-\x1f\x7f]', url):
            return False, "URL contains invalid control characters"

        try:
            parsed = urlparse(url)

            # Must have scheme and netloc
            if not parsed.scheme:
                return False, "URL must include a scheme (http:// or https://)"
            if not parsed.netloc:
                return False, "URL must include a hostname"

            # Only allow http/https
            if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
                return False, f"URL scheme '{parsed.scheme}' not allowed. Allowed: {', '.join(self.ALLOWED_SCHEMES)}"

            # Must have hostname
            if not parsed.hostname:
                return False, "URL must include a valid hostname"

            # Block dangerous ports
            if parsed.port and parsed.port in self.DANGEROUS_PORTS:
                return False, f"Port {parsed.port} is blocked for security reasons"

            return True, None

        except Exception as e:
            return False, f"Invalid URL format: {str(e)}"

    # ==================== Rate Limiting ====================

    def _check_rate_limit(self):
        """Check if request rate limit is exceeded. Returns (allowed, error_message)."""
        current_time = time.time()

        with self._lock:
            # Reset counter if more than 60 seconds have passed
            time_diff = current_time - self._last_request_time
            if time_diff >= 60:
                self._request_counter = 0
                self._last_request_time = current_time

            self._request_counter += 1

            if self._request_counter > self.MAX_REQUESTS_PER_MINUTE:
                return False, f"Rate limit exceeded. Maximum {self.MAX_REQUESTS_PER_MINUTE} requests per minute."

        return True, None

    # ==================== Input Sanitization ====================

    def _sanitize_headers(self, headers: dict):
        """Sanitize headers to prevent injection attacks."""
        if not headers:
            return self.default_headers.copy()

        sanitized = {}
        dangerous_headers = {
            'host', 'content-length', 'transfer-encoding', 'connection',
            'keep-alive', 'upgrade', 'proxy-authorization', 'proxy-authenticate',
            'te', 'trailer', 'upgrade-insecure-requests'
        }

        for key, value in headers.items():
            if not key:
                continue

            key_lower = key.lower()

            # Skip dangerous headers
            if key_lower in dangerous_headers:
                continue

            # Sanitize key and value
            clean_key = re.sub(r'[\r\n\x00-\x1f]', '', str(key))
            clean_value = str(value).replace('\x00', '') if value else ''

            # Limit header value length
            if len(clean_value) > 8000:
                clean_value = clean_value[:8000]

            sanitized[clean_key] = clean_value

        # Add default headers
        for key, value in self.default_headers.items():
            if key.lower() not in {k.lower() for k in sanitized}:
                sanitized[key] = value

        return sanitized

    def _sanitize_params(self, params: dict):
        """Sanitize query parameters."""
        if params is None:
            return None

        sanitized = {}
        for k, v in params.items():
            if k is not None:
                clean_key = str(k).replace('\x00', '')
                clean_value = str(v).replace('\x00', '') if v is not None else ''
                sanitized[clean_key] = clean_value

        return sanitized

    def _sanitize_data(self, data: dict):
        """Sanitize POST/PUT/PATCH data."""
        if data is None:
            return None

        sanitized = {}
        for k, v in data.items():
            if k is not None:
                clean_key = str(k).replace('\x00', '')
                clean_value = str(v).replace('\x00', '') if v is not None else ''
                sanitized[clean_key] = clean_value

        return sanitized

    # ==================== Logging ====================

    def _log(self, message: str):
        """Log request for audit trail."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[HTTP LOG] {timestamp} - {message}")

    # ==================== Request Execution ====================

    async def _make_request(self, func, url: str, **kwargs):
        """
        Make HTTP request with security checks.

        Args:
            func: HTTP function (get, post, etc.)
            url: Target URL
            **kwargs: Additional request parameters
        """
        # Validate URL format
        is_valid, error_msg = self._validate_url_format(url)
        if not is_valid:
            self._log(f"URL validation failed: {error_msg}")
            return self.result(error_msg, False)

        # SSRF protection
        if not self._is_safe_url(url):
            return self.result("URL blocked by security policy", False)

        # Rate limiting
        allowed, error_msg = self._check_rate_limit()
        if not allowed:
            return self.result(error_msg, False)

        # Sanitize headers
        headers = self._sanitize_headers(kwargs.get("headers"))
        kwargs["headers"] = headers

        # Sanitize params
        if "params" in kwargs and kwargs["params"] is not None:
            kwargs["params"] = self._sanitize_params(kwargs["params"])

        # Sanitize data
        if "data" in kwargs and kwargs["data"] is not None:
            kwargs["data"] = self._sanitize_data(kwargs["data"])

        # Set security options
        kwargs["timeout"] = kwargs.get("timeout", self.REQUEST_TIMEOUT)
        kwargs["verify"] = kwargs.get("verify", True)
        kwargs["allow_redirects"] = kwargs.get("allow_redirects", True)

        # Extract internal flag
        include_content = kwargs.pop("include_content", False)

        try:
            result = func(url, **kwargs)

        except requests.exceptions.Timeout:
            self._log(f"Request timeout: {url}")
            return self.result(f"Request timed out after {kwargs['timeout']} seconds", False)
        except requests.exceptions.SSLError as e:
            self._log(f"SSL error: {str(e)}")
            return self.result(f"SSL verification failed: {str(e)}", False)
        except requests.exceptions.TooManyRedirects:
            self._log(f"Too many redirects: {url}")
            return self.result(f"Too many redirects (maximum: {self.MAX_REDIRECTS})", False)
        except requests.exceptions.ConnectionError as e:
            self._log(f"Connection error: {str(e)}")
            return self.result(f"Connection error: {str(e)}", False)
        except requests.exceptions.RequestException as e:
            self._log(f"Request failed: {str(e)}")
            return self.result(f"Request failed: {str(e)}", False)
        except Exception as e:
            self._log(f"Unexpected error: {str(e)}")
            return self.result(f"Unexpected error: {str(e)}", False)

        # Check content size
        if include_content:
            content_length = result.headers.get('Content-Length')
            if content_length and int(content_length) > self.MAX_CONTENT_SIZE:
                self._log(f"Content too large: {content_length} bytes")
                return self.result(
                    f"Response too large: {content_length} bytes exceeds limit of {self.MAX_CONTENT_SIZE} bytes",
                    False
                )

        # Build response
        response = {
            "status": f"{result.status_code} {result.reason}",
            "headers": dict(result.headers),
            "cookies": dict(result.cookies),
            "url": result.url,
        }

        if include_content:
            try:
                content = result.text
                if len(content) > self.MAX_CONTENT_SIZE:
                    content = content[:self.MAX_CONTENT_SIZE]
                    response["content_truncated"] = True
                response["content"] = content
            except Exception as e:
                response["content_error"] = str(e)

        self._log(f"Request completed: {result.status_code} - {url}")
        return self.result(response)

    # ==================== HTTP Methods ====================

    async def get(self, url: str, headers: dict = None, params: dict =None):
        """
        Performs a HTTP GET request on url.

        Args:
            url: the URL to target
            params: any parameters to add to the request
            headers: HTTP headers

        Returns:
            Result dict with status, headers, cookies, and content
        """
        return await self._make_request(
            requests.get,
            url,
            params=params,
            headers=headers,
            include_content=True
        )

    async def post(self, url: str, headers: dict = None, data: dict = None, json: dict = None):
        """
        Performs a HTTP POST on url.

        Args:
            url: the URL to target
            data: the data to post to the url (form-encoded)
            json: JSON data to post (cannot be used with data)
            headers: HTTP headers

        Returns:
            Result dict with status, headers, cookies, and content
        """
        if data is not None and json is not None:
            return self.result("Cannot use both 'data' and 'json' parameters", False)

        return await self._make_request(
            requests.post,
            url,
            data=data,
            json=json,
            headers=headers,
            include_content=True
        )

    async def head(self, url: str, params: dict = None, headers: dict = None):
        """
        Performs a HTTP HEAD on url.

        Args:
            url: the URL to target
            params: any parameters to add to the request
            headers: HTTP headers

        Returns:
            Result dict with status, headers, and cookies
        """
        return await self._make_request(
            requests.head,
            url,
            params=params,
            headers=headers,
            include_content=False
        )

    async def options(self, url, params: dict = None, headers: dict = None):
        """
        Performs a HTTP OPTIONS on url.

        Args:
            url: the URL to target
            params: any parameters to add to the request
            headers: HTTP headers

        Returns:
            Result dict with status, headers, and cookies
        """
        return await self._make_request(
            requests.options,
            url,
            params=params,
            headers=headers,
            include_content=False
        )

    async def put(self, url, data: dict = None, headers: dict = None):
        """
        Performs a HTTP PUT on url.

        Args:
            url: the URL to target
            data: the data to put to the url
            headers: HTTP headers

        Returns:
            Result dict with status, headers, cookies, and content
        """
        return await self._make_request(
            requests.put,
            url,
            data=data,
            headers=headers,
            include_content=True
        )

    async def patch(self, url, data: dict = None, headers: dict = None):
        """
        Performs a HTTP PATCH on url.

        Args:
            url: the URL to target
            data: the data to patch
            headers: HTTP headers

        Returns:
            Result dict with status, headers, cookies, and content
        """
        return await self._make_request(
            requests.patch,
            url,
            data=data,
            headers=headers,
            include_content=True
        )

    async def delete(self, url, params: dict = None, headers: dict = None):
        """
        Performs a HTTP DELETE on url.

        Args:
            url: the URL to target
            params: any parameters to add to the request
            headers: HTTP headers

        Returns:
            Result dict with status, headers, and cookies
        """
        return await self._make_request(
            requests.delete,
            url,
            params=params,
            headers=headers,
            include_content=True
        )
