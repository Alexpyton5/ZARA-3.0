"""
Browser Action — Playwright-based browser automation.
"""
from __future__ import annotations

import asyncio
import base64
import json

from core.action_registry import ActionResult, action, get_registry
from core.url_security import URLSecurityError, validate_public_http_url, validate_public_ip

# Playwright is optional
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


_browser_instance = None
_browser_context = None
_playwright = None


async def _guard_public_request(route) -> None:
    """Abort browser requests that resolve outside the public internet."""

    try:
        await asyncio.to_thread(validate_public_http_url, route.request.url)
    except URLSecurityError:
        await route.abort("blockedbyclient")
        return
    await route.continue_()


async def _validate_browser_response_peer(response) -> None:
    """Validate the actual document peer when Playwright exposes it."""

    if response is None:
        return
    server_addr = getattr(response, "server_addr", None)
    if not callable(server_addr):
        return
    peer = await server_addr()
    if isinstance(peer, dict) and peer.get("ipAddress"):
        await asyncio.to_thread(validate_public_ip, str(peer["ipAddress"]))


async def _get_browser():
    """Get or create browser instance."""
    global _browser_instance, _browser_context, _playwright

    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed. Run: uv pip install playwright && playwright install")

    if _playwright is None:
        _playwright = await async_playwright().start()

    if _browser_instance is None:
        _browser_instance = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

    if _browser_context is None:
        _browser_context = await _browser_instance.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            service_workers="block",
        )
        # The guard remains active for redirects, subresources and navigations
        # caused later by browser_click/browser_type.
        await _browser_context.route("**/*", _guard_public_request)

    return _browser_context


@action(
    name="browser_navigate",
    category="browser",
    description="Navigate to a URL",
    risk="LOW",
    capability="READ_ONLY",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "wait_until": {"type": "string", "description": "Wait condition (default: networkidle)", "default": "networkidle", "enum": ["load", "domcontentloaded", "networkidle"]},
            "timeout": {"type": "integer", "description": "Timeout in ms (default: 30000)", "default": 30000},
        },
        "required": ["url"],
    },
    async_execution=True,
)
async def browser_navigate_action(url: str, wait_until: str = "networkidle", timeout: int = 30000) -> ActionResult:
    """Navigate to a URL."""
    try:
        validated = await asyncio.to_thread(validate_public_http_url, url)
        context = await _get_browser()
        page = await context.new_page()

        resp = await page.goto(validated.url, wait_until=wait_until, timeout=timeout)
        await _validate_browser_response_peer(resp)
        final_url = await asyncio.to_thread(validate_public_http_url, page.url)

        return ActionResult(
            success=True,
            output=f"Navigated to {final_url.url}",
            data={
                "url": final_url.url,
                "title": await page.title(),
                "status": resp.status if resp else None,
            }
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_click",
    category="browser",
    description="Click an element",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector"},
            "wait_for": {"type": "string", "description": "Wait for selector before click"},
        },
        "required": ["selector"],
    },
    async_execution=True,
    capability="PC_CONTROL",
)
async def browser_click_action(selector: str, wait_for: str = "") -> ActionResult:
    """Click an element."""
    try:
        context = await _get_browser()
        pages = context.pages
        page = pages[-1] if pages else await context.new_page()

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=5000)

        await page.click(selector, timeout=5000)

        return ActionResult(success=True, output=f"Clicked: {selector}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_type",
    category="browser",
    description="Type text into an input",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector for input"},
            "text": {"type": "string", "description": "Text to type"},
            "delay": {"type": "integer", "description": "Delay between keystrokes in ms (default: 50)", "default": 50},
        },
        "required": ["selector", "text"],
    },
    async_execution=True,
    capability="PC_CONTROL",
)
async def browser_type_action(selector: str, text: str, delay: int = 50) -> ActionResult:
    """Type text into an input."""
    try:
        context = await _get_browser()
        pages = context.pages
        page = pages[-1] if pages else await context.new_page()

        await page.fill(selector, "", timeout=5000)
        await page.type(selector, text, delay=delay)

        return ActionResult(success=True, output=f"Typed into {selector}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_screenshot",
    category="browser",
    description="Take a screenshot",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Save path (optional, returns base64 if not provided)"},
            "full_page": {"type": "boolean", "description": "Full page screenshot (default: false)", "default": False},
        },
        "required": [],
    },
    async_execution=True,
)
async def browser_screenshot_action(path: str = "", full_page: bool = False) -> ActionResult:
    """Take a screenshot."""
    try:
        context = await _get_browser()
        pages = context.pages
        page = pages[-1] if pages else await context.new_page()

        if path:
            await page.screenshot(path=path, full_page=full_page)
            return ActionResult(
                success=True,
                output=f"Screenshot saved to {path}",
                data={"path": path}
            )
        else:
            img_bytes = await page.screenshot(full_page=full_page)
            b64 = base64.b64encode(img_bytes).decode()
            return ActionResult(
                success=True,
                output="Screenshot captured (base64)",
                data={"screenshot_base64": b64, "size": len(img_bytes)}
            )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_extract",
    category="browser",
    description="Extract data from page using CSS selectors",
    parameters={
        "type": "object",
        "properties": {
            "selectors": {"type": "object", "description": "Mapping of field names to CSS selectors"},
            "attribute": {"type": "string", "description": "Attribute to extract (default: textContent)", "default": "textContent"},
        },
        "required": ["selectors"],
    },
    async_execution=True,
)
async def browser_extract_action(selectors: dict, attribute: str = "textContent") -> ActionResult:
    """Extract data from page."""
    try:
        context = await _get_browser()
        pages = context.pages
        page = pages[-1] if pages else await context.new_page()

        result = {}
        for field, selector in selectors.items():
            try:
                if attribute == "textContent":
                    value = await page.locator(selector).first.text_content(timeout=3000)
                elif attribute == "innerHTML":
                    value = await page.locator(selector).first.inner_html(timeout=3000)
                else:
                    value = await page.locator(selector).first.get_attribute(attribute, timeout=3000)
                result[field] = value
            except Exception:
                result[field] = None

        return ActionResult(
            success=True,
            output=json.dumps(result, indent=2),
            data=result
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_eval",
    category="browser",
    description="Execute JavaScript in page context",
    risk="HIGH",
    parameters={
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "JavaScript code to execute"},
        },
        "required": ["script"],
    },
    async_execution=True,
    capability="CODE_EXECUTION",
)
async def browser_eval_action(script: str) -> ActionResult:
    """Execute JavaScript."""
    try:
        context = await _get_browser()
        pages = context.pages
        page = pages[-1] if pages else await context.new_page()

        result = await page.evaluate(script)

        return ActionResult(
            success=True,
            output=json.dumps(result) if not isinstance(result, str) else result,
            data=result
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="browser_close",
    category="browser",
    description="Close browser",
    parameters={},
    async_execution=True,
)
async def browser_close_action() -> ActionResult:
    """Close browser."""
    global _browser_instance, _browser_context, _playwright

    try:
        if _browser_context:
            await _browser_context.close()
            _browser_context = None
        if _browser_instance:
            await _browser_instance.close()
            _browser_instance = None
        if _playwright:
            await _playwright.stop()
            _playwright = None

        return ActionResult(success=True, output="Browser closed")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


get_registry()
