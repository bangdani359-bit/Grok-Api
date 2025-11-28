from fastapi import FastAPI, HTTPException, Header
from urllib.parse import urlparse, ParseResult
from pydantic import BaseModel
from core.grok import Grok
import uvicorn
import os
import json
from typing import List
from fastapi.concurrency import run_in_threadpool

app = FastAPI()

SYSTEM_PROMPT_FILE = "system-prompt.txt"
APIKEY_FILE = "apikeys.json"

def load_system_prompt() -> str | None:
    if os.path.exists(SYSTEM_PROMPT_FILE):
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def load_apikeys() -> List[str]:
    if os.path.exists(APIKEY_FILE):
        with open(APIKEY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_apikeys(keys: List[str]):
    with open(APIKEY_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)

def validate_apikey(apikey: str):
    keys = load_apikeys()
    if apikey not in keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/")
async def health():
    return {"status": "ok"}

class ConversationRequest(BaseModel):
    proxy: str | None = None
    message: str
    model: str = "grok-3-auto"
    extra_data: dict | None = None

def format_proxy(proxy: str) -> str:
    if not proxy.startswith(("http://", "https://")):
        proxy = "http://" + proxy

    parsed: ParseResult = urlparse(proxy)

    if parsed.scheme not in ("http", ""):
        raise ValueError("Invalid scheme")

    if not parsed.hostname or not parsed.port:
        raise ValueError("Invalid host/port")

    if parsed.username and parsed.password:
        return f"http://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
    else:
        return f"http://{parsed.hostname}:{parsed.port}"

@app.post("/ask")
async def create_conversation(request: ConversationRequest, x_api_key: str = Header(...)):
    validate_apikey(x_api_key)

    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    proxy = None
    if request.proxy:
        try:
            proxy = format_proxy(request.proxy)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Proxy error: {str(e)}")

    try:
        bot = Grok(request.model, proxy)

        # LOAD SYSTEM PROMPT
        system_prompt = load_system_prompt()
        extra_data = request.extra_data or {}
        if system_prompt:
            extra_data["system_prompt"] = system_prompt

        # NON-BLOCKING
        answer = await run_in_threadpool(bot.start_convo, request.message, extra_data)

        return {"status": "success", **answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

class APIKeyRequest(BaseModel):
    apikey: str

@app.post("/apikey/add")
async def add_apikey(req: APIKeyRequest):
    keys = load_apikeys()
    if req.apikey in keys:
        raise HTTPException(status_code=400, detail="API key already exists")
    keys.append(req.apikey)
    save_apikeys(keys)
    return {"status": "success", "message": f"API key {req.apikey} added"}

@app.post("/apikey/del")
async def delete_apikey(req: APIKeyRequest):
    keys = load_apikeys()
    if req.apikey not in keys:
        raise HTTPException(status_code=404, detail="API key not found")
    keys.remove(req.apikey)
    save_apikeys(keys)
    return {"status": "success", "message": f"API key {req.apikey} deleted"}

@app.get("/apikey/l")
async def list_apikeys():
    keys = load_apikeys()
    return {"status": "success", "apikeys": keys}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
