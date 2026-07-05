import logging

import uvicorn

from config import HOST, PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Web LLM Provider on {HOST}:{PORT}")
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        log_level="info",
    )
