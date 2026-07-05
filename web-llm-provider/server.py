import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from typing import Any

from browser_manager import BrowserManager
from page_manager import PageManager

logger = logging.getLogger(__name__)

browser_manager = BrowserManager()
page_manager = PageManager(browser_manager)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str = "doubao"
    messages: list[ChatMessage]
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "user"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting browser...")
    await browser_manager.start()
    logger.info(f"Waiting for login at {browser_manager.selectors.url}")
    logger.info("Please log in manually in the opened browser window.")
    try:
        await browser_manager.wait_for_login()
    except TimeoutError as e:
        logger.error(str(e))
        raise
    logger.info("Browser ready to accept requests")
    yield
    logger.info("Stopping browser...")
    await browser_manager.stop()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Request body: {await request.body()}")
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.get("/v1/models", response_model=ModelList)
async def list_models():
    return ModelList(
        data=[
            ModelInfo(
                id="doubao",
                created=int(time.time()),
            )
        ]
    )


@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    prompt = _extract_prompt(request.messages)
    logger.info(f"Extracted prompt: {prompt[:200]}")

    try:
        text = await page_manager.send_and_read(prompt)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if request.stream:
        return _sse_response(text, request.model)

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
            }
        ],
    )


def _sse_response(text: str, model: str) -> StreamingResponse:
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    chunk_size = 5

    async def event_stream():
        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'content': chunk}, 'finish_reason': None}]})}\n\n"
            await asyncio.sleep(0.01)
        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _extract_prompt(messages: list[ChatMessage]) -> str:
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    last_user = [m for m in messages if m.role == "user"]
    if not last_user:
        raise HTTPException(status_code=400, detail="No user message found")
    content = last_user[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(parts)
    return str(content or "")
