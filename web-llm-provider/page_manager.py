import asyncio
import logging
import re
import time

import html2text

from browser_manager import BrowserManager

logger = logging.getLogger(__name__)


class PageManager:
    def __init__(self, browser_manager: BrowserManager):
        self._browser = browser_manager
        self._lock = asyncio.Lock()
        self._request_timeout: float = 120.0
        self._last_request_time: float = 0.0

    def set_request_timeout(self, timeout: float) -> None:
        self._request_timeout = timeout

    async def send_and_read(self, prompt: str) -> str:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < 2.0:
                await asyncio.sleep(2.0 - elapsed)
            try:
                return await self._do_send_and_read(prompt)
            finally:
                self._last_request_time = time.monotonic()

    async def _do_send_and_read(self, prompt: str) -> str:
        page = await self._browser.ensure_page_alive()
        selectors = self._browser.selectors

        input_el = await page.wait_for_selector(
            selectors.input_field,
            timeout=15000,
        )
        if input_el is None:
            raise RuntimeError("Could not find input field")

        await input_el.click()
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.05)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.1)
        await input_el.fill(prompt)
        await page.evaluate("(el) => el.dispatchEvent(new Event('input', { bubbles: true }))", input_el)
        await asyncio.sleep(0.2)
        await page.keyboard.press("Enter")

        response_text = await self._wait_for_response(page)

        if not response_text.strip():
            raise RuntimeError("Empty response from LLM")

        return response_text.strip()

    async def _wait_for_response(self, page) -> str:
        timeout_ms = int(self._request_timeout * 1000)

        baseline_rows = await page.evaluate("""
            () => {
                const list = document.querySelector('.list_items');
                if (!list) return 0;
                return list.children.length;
            }
        """)

        stop_sel = self._browser.selectors.stop_button
        stop_btn = None
        try:
            stop_btn = await page.wait_for_selector(
                stop_sel,
                timeout=3000,
            )
        except Exception:
            pass

        if stop_btn is not None:
            elapsed = 0.0
            interval = 0.5
            deadline = self._request_timeout
            while elapsed < deadline:
                await asyncio.sleep(interval)
                elapsed += interval
                still = await page.evaluate(f"""
                    () => !!document.querySelector({stop_sel!r})
                """)
                if not still:
                    logger.info("Generating indicator gone, response complete")
                    break
        else:
            logger.info("No stop button found, polling for new content stability")
            last_len = 0
            for _ in range(120):
                await asyncio.sleep(0.5)
                cur_len = await page.evaluate(f"""
                    () => {{
                        const list = document.querySelector('.list_items');
                        if (!list) return 0;
                        const rows = [...list.children];
                        if (rows.length <= {baseline_rows}) return -1;
                        for (let i = rows.length - 1; i >= 0; i--) {{
                            if (rows[i].querySelector('[class^="container-"]')) {{
                                const clone = rows[i].cloneNode(true);
                                const folds = clone.querySelectorAll('details, [class*="fold"], [class*="collapse"], [class*="think"], [class*="reason"]');
                                for (const el of folds) el.remove();
                                return (clone.textContent || '').trim().length;
                            }}
                        }}
                        return -1;
                    }}
                """)
                if cur_len == -1:
                    continue
                if cur_len == last_len and cur_len > 0:
                    logger.info(f"New content stable at {cur_len} chars")
                    break
                last_len = cur_len

        await asyncio.sleep(1)

        response_text = await self._extract_response_text(page)
        return response_text.strip()

    async def _extract_response_text(self, page) -> str:
        data = await page.evaluate("""
            () => {
                const list = document.querySelector('.list_items');
                if (!list) return { html: '', toolCalls: [] };

                const rows = [...list.children].filter(r => (r.textContent || '').trim());
                for (let i = rows.length - 1; i >= 0; i--) {
                    const containers = rows[i].querySelectorAll('[class^="container-"]');
                    if (containers.length > 0) {
                        const outer = containers[0].cloneNode(true);
                        const metas = outer.querySelectorAll('[class*="text-dbx-text-secondary"]');
                        for (const el of metas) el.remove();
                        const folds = outer.querySelectorAll('details, [class*="fold"], [class*="collapse"], [class*="think"], [class*="reason"]');
                        for (const el of folds) el.remove();

                        const toolCalls = [];
                        const seen = new Set();
                        const toolEls = outer.querySelectorAll('code[class*="preai-tool"]');
                        for (const el of toolEls) {
                            const raw = el.textContent.trim();
                            if (!raw || seen.has(raw)) continue;
                            seen.add(raw);
                            toolCalls.push(raw);
                            const pre = el.closest('pre');
                            if (pre) {
                                pre.remove();
                            } else {
                                el.remove();
                            }
                        }

                        return { html: outer.innerHTML, toolCalls };
                    }
                }
                return { html: rows.length > 0 ? rows[rows.length - 1].textContent || '' : '', toolCalls: [] };
            }
        """)

        if not data:
            return ''

        tool_calls_raw = data.get('toolCalls', [])
        html_content = data.get('html', '')

        if not html_content:
            return ''

        logger.info(f'JS extracted {len(tool_calls_raw)} tool call(s)')

        converter = html2text.HTML2Text()
        converter.body_width = 0
        converter.ignore_links = False
        converter.ignore_images = False
        converter.ignore_emphasis = False
        converter.protect_links = True
        converter.unicode_snob = True
        markdown = converter.handle(html_content)

        if tool_calls_raw:
            markdown = re.sub(r'(?m)^\s*(?:```(?:language-)?preai-tool```\s*)?\s*preai-tool\s*$', '', markdown)
            blocks = '\n\n'.join(f'```preai-tool\n{raw}\n```' for raw in tool_calls_raw)
            markdown = markdown.rstrip() + '\n\n' + blocks

        logger.info(f'Extracted markdown ({len(markdown)} chars, {len(tool_calls_raw)} tool blocks)')
        return markdown.strip()
