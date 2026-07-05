from dataclasses import dataclass


@dataclass
class SiteSelectors:
    url: str
    input_field: str
    send_button: str
    response_area: str
    stop_button: str
    login_indicator: str


DOUBAO_SELECTORS = SiteSelectors(
    url="https://www.doubao.com/chat/",
    input_field="textarea.semi-input-textarea",
    send_button="button[type='submit']",
    response_area="[class*='container-'][class*='flex-1']",
    stop_button="button:has-text('Stop')",
    login_indicator="textarea",
)

SITES: dict[str, SiteSelectors] = {
    "doubao": DOUBAO_SELECTORS,
}
