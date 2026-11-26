"""FastAPI entrypoint for Vercel Serverless Functions + local development."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
    load_dotenv(_root / ".env.local")
except ImportError:
    pass

from ._lib import db_helper, nlp_engine

app = FastAPI(
    title="Taste of Himalaya Chatbot API",
    description="Self-hosted NLP food ordering & tracking chatbot powered by FastAPI + Neon PostgreSQL.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    session_id: str | None = Field(default=None, max_length=128)


class ResetRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "taste-of-himalaya-chatbot",
        **db_helper.check_health(),
    }


@app.get("/api/menu")
def list_menu():
    return {"items": db_helper.get_menu_items()}


@app.post("/api/chat")
def chat(req: ChatRequest):
    session_id = (req.session_id or "").strip() or str(uuid4())
    result = nlp_engine.process_message(req.message, session_id)
    return {
        "session_id": session_id,
        **result,
    }


@app.post("/api/reset")
def reset_session(req: ResetRequest):
    db_helper.save_session(req.session_id, None, {})
    return {"status": "ok", "session_id": req.session_id}


# Serve static frontend locally when running `uvicorn api.index:app --reload`
# (On Vercel, files in `public/` are served directly by Vercel's CDN.)
_public_dir = Path(__file__).resolve().parent.parent / "public"
if not os.getenv("VERCEL") and _public_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_public_dir), html=True), name="static")
