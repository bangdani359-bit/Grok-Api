from fastapi import FastAPI, HTTPException
from urllib.parse import urlparse, ParseResult
from pydantic import BaseModel
from core.grok import Grok
import uvicorn
import os

app = FastAPI()

# FILE SYSTEM PROMPT
SYSTEM_PROMPT_FILE = "system-prompt.txt"

def load_system_prompt() -> str | None:
    """Baca system prompt dari file jika ada"""
    if os.path.exists(SYSTEM_PROMPT_FILE):
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

# HEALTH CHECK → wajib buat Deployra
@app.get("/")
async def health():
    return {"status": "ok"}

# REQUEST BODY
class ConversationRequest(BaseModel):
    proxy: str | None = None
    message: str
    model: str = "grok-3-auto"
    extra_data: dict | None = None

# FORMAT PROXY
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

# ENDPOINT ASK
@app.post("/ask")
async def create_conversation(request: ConversationRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Handle proxy opsional
    proxy = None
    if request.proxy:
        try:
            proxy = format_proxy(request.proxy)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Proxy error: {str(e)}")

    try:
        bot = Grok(request.model, proxy)

        # ===========================
        # 🔥 SYSTEM PROMPT HANDLING DARI FILE
        # ===========================
        system_prompt = load_system_prompt()
        if system_prompt:
            final_message = f"{system_prompt}\n\nUser: {request.message}"
        else:
            final_message = request.message

        answer = bot.start_convo(final_message, request.extra_data)

        return {"status": "success", **answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

# RUN UVICORN
if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
