import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=r"D:\Project\PreAI\agent-os\experiments\web-llm-provider\.browser_data",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        page = await browser.new_page()
        await page.goto("https://www.doubao.com/chat/")
        await asyncio.sleep(5)

        await page.fill('textarea', '分析美国国情')
        await page.keyboard.press("Enter")
        await asyncio.sleep(10)

        diag = await page.evaluate("""
            () => {
                const results = [];

                // Find the message list
                const msgList = document.querySelector('.message-list-zLoNs1, .list_items');
                if (!msgList) {
                    results.push("ERROR: message list not found");
                    return results.join('\\n');
                }
                results.push("=== Message list children ===");
                results.push(`tag=${msgList.tagName} class=${msgList.className} children=${msgList.children.length}`);

                for (let ci = 0; ci < msgList.children.length; ci++) {
                    const child = msgList.children[ci];
                    const txt = (child.innerText || '').trim().slice(0, 100);
                    const cls = String(child.className || '');
                    const tag = child.tagName;
                    const id = child.id || '';
                    const attrs = [];
                    if (child.getAttribute) {
                        for (const attr of ['data-role', 'data-testid', 'role', 'data-position']) {
                            const v = child.getAttribute(attr);
                            if (v) attrs.push(`${attr}=${v}`);
                        }
                    }
                    results.push(`\\n--- child ${ci} ---`);
                    results.push(`<${tag}> class="${cls.slice(0,80)}" id="${id}" ${attrs.join(' ')}`);
                    results.push(`text: "${txt.replace(/\\n/g, '\\\\n')}"`);

                    // Walk into this child to find inner elements with classes
                    if (ci === msgList.children.length - 1 || ci === msgList.children.length - 2) {
                        // Deep dive into last 2 children (likely the latest user+AI messages)
                        const deepWalk = (el, depth) => {
                            if (depth > 5) return;
                            for (let i = 0; i < el.children.length; i++) {
                                const c = el.children[i];
                                const cTxt = (c.innerText || '').trim().slice(0, 80);
                                const cCls = String(c.className || '');
                                const cTag = c.tagName;
                                const indent = '  '.repeat(depth + 1);
                                if (cCls) {
                                    results.push(`${indent}<${cTag} class="${cCls.slice(0,60)}" text="${cTxt.replace(/\\n/g, '\\\\n')}" />`);
                                }
                                deepWalk(c, depth + 1);
                            }
                        };
                        deepWalk(child, 0);
                    }
                }

                // Also check the specific container elements for the AI response
                results.push("\\n=== container elements with AI text ===");
                const containers = document.querySelectorAll('[class^="container-"]');
                for (const c of containers) {
                    const txt = (c.innerText || '').trim();
                    if (txt && !txt.includes('下载电脑版') && txt.length > 10) {
                        results.push(`class="${c.className.slice(0,50)}"`);
                        // Check if parent has distinguishing class
                        const parent = c.parentElement;
                        if (parent) {
                            results.push(`  parent class="${(parent.className||'').slice(0,50)}"`);
                        }
                        const grandparent = parent ? parent.parentElement : null;
                        if (grandparent) {
                            results.push(`  grandparent class="${(grandparent.className||'').slice(0,50)}"`);
                        }
                    }
                }

                return results.join('\\n');
            }
        """)

        print("=== DOM DIAGNOSTIC ===")
        print(diag)
        print("=== END ===")

        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
