import os


HOST: str = os.environ.get("WEB_LLM_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("WEB_LLM_PORT", "9091"))
HEADLESS: bool = os.environ.get("WEB_LLM_HEADLESS", "false").lower() == "true"
REQUEST_TIMEOUT: int = int(os.environ.get("WEB_LLM_REQUEST_TIMEOUT", "120"))
BROWSER_DATA_DIR: str = os.environ.get(
    "WEB_LLM_BROWSER_DATA_DIR",
    os.path.join(os.path.dirname(__file__), ".browser_data"),
)
LOGIN_WAIT_TIMEOUT: int = int(os.environ.get("WEB_LLM_LOGIN_WAIT_TIMEOUT", "300"))
PAGE_URL: str = "https://www.doubao.com/chat/"
