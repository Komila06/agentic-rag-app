"""
FastAPI wrapper around the agentic RAG graph.

Run locally:
    uvicorn api:app --host 0.0.0.0 --port 7860

Deploy: Hugging Face Spaces (Docker SDK, port 7860). Set OPENAI_API_KEY and
TAVILY_API_KEY as Space secrets.
"""
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_graph import rag_app, run_ingest

app = FastAPI(title="Agentic RAG API")

# Allow the Vercel-hosted frontend (or local dev) to call this API from the browser.
# Restrict allow_origins to your actual frontend URL(s) in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    question: str


class ChatOut(BaseModel):
    answer: str
    steps: list[str]
    sources: list[dict]
    web_used: bool


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    result = rag_app.invoke({"question": body.question})
    return {
        "answer": result.get("generation", ""),
        "steps": result.get("steps", []),
        "sources": result.get("sources", []),
        "web_used": result.get("web_used", False),
    }


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Only .pdf, .txt, .md files are supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        chunk_count = run_ingest(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"filename": file.filename, "chunks_added": chunk_count}
