"""Call API tool — makes HTTP requests to external or internal APIs."""

import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.call_api")

_TIMEOUT = 30.0
_MAX_RESPONSE_BYTES = 50_000  # 50 KB


class CallAPITool(BaseTool):
    name = "call_api"
    description = "Make an HTTP request to an external or internal API."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to call",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method: GET or POST",
                    "enum": ["GET", "POST"],
                },
                "body": {
                    "type": "string",
                    "description": "Request body for POST requests",
                },
            },
            "required": ["url"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = arguments.get("url", "")
        method = (arguments.get("method") or "GET").upper()
        body = arguments.get("body")

        if not url:
            return ToolResult(success=False, error="Empty URL")

        if method not in ("GET", "POST"):
            return ToolResult(success=False, error="Only GET and POST methods are allowed")

        # Validate domain against whitelist.
        allowed = self._get_allowed_hosts()
        if not self._is_allowed(url, allowed):
            return ToolResult(
                success=False,
                error=f"Domain not in whitelist. Allowed: {', '.join(sorted(allowed))}",
            )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                if method == "GET":
                    resp = await client.get(url)
                else:
                    headers = {}
                    if body:
                        headers["Content-Type"] = "application/json"
                    resp = await client.post(url, content=body, headers=headers)

                text = resp.text[:_MAX_RESPONSE_BYTES]
                truncated = len(resp.text) > _MAX_RESPONSE_BYTES

                return ToolResult(
                    success=True,
                    data={
                        "status_code": resp.status_code,
                        "body": text,
                        "truncated": truncated,
                    },
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error="Request timed out (30s)")
        except Exception as exc:
            return ToolResult(success=False, error=f"HTTP request failed: {exc}")

    def _get_allowed_hosts(self) -> set[str]:
        """Build the set of allowed hostnames/IPs from tool config."""
        allowed: set[str] = set()

        # Always allow localhost and the local network.
        allowed.update(["localhost", "127.0.0.1"])

        # Extract hosts from configured endpoints.
        endpoints = self.config.get("endpoints", {})
        for url in endpoints.values():
            try:
                parsed = urlparse(url)
                if parsed.hostname:
                    allowed.add(parsed.hostname)
            except Exception:
                pass

        # Explicit allowed domains from config.
        for domain in self.config.get("allowed_domains", []):
            allowed.add(domain)

        return allowed

    def _is_allowed(self, url: str, allowed_hosts: set[str]) -> bool:
        """Check if the URL's host is in the allowed set."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
        except Exception:
            return False

        # Direct match.
        if hostname in allowed_hosts:
            return True

        # Check if it's a private IP in 192.168.x.x range.
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private:
                return True
        except ValueError:
            pass

        return False
