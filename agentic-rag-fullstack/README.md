# Agentic RAG — Full Stack

Two pieces, matching the original project guide:

- **`backend/`** — FastAPI wrapping the LangGraph agent (`/chat`, `/ingest`, `/health`). Same
  logic as your Colab notebook, refactored into standalone modules so it can run as a service.
  Deploy target: **Hugging Face Spaces** (Docker).
- **`frontend/`** — Next.js chat UI. Calls the backend's `/chat` endpoint and renders the
  agent's step trace (`retrieve → grade → web search → generate`) and citations above/below
  each answer. Deploy target: **Vercel**.

## Run locally

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or your preferred env tool
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY, TAVILY_API_KEY
uvicorn api:app --reload --port 7860
```

Ingest a document once the server is running:

```bash
curl -X POST http://localhost:7860/ingest -F "file=@/path/to/your.pdf"
```

**Frontend**

```bash
cd frontend
npm install
cp .env.local.example .env.local   # points at http://localhost:7860 by default
npm run dev
```

Open http://localhost:3000 and start asking questions.

## Deploy

**Backend → Hugging Face Spaces**
1. Create a new Space, SDK = **Docker**.
2. Push the contents of `backend/` to the Space's git repo (the `Dockerfile` is already set up
   for port 7860, which Spaces expects).
3. In the Space's **Settings → Repository secrets**, add `OPENAI_API_KEY` and `TAVILY_API_KEY`.
4. Once it builds, your API is live at `https://<your-space>.hf.space`. Check
   `https://<your-space>.hf.space/health`.

**Frontend → Vercel**
1. Push `frontend/` to a GitHub repo, import it in Vercel.
2. Set the environment variable `NEXT_PUBLIC_API_URL` to your Space's URL from above.
3. Deploy. Vercel auto-detects Next.js — no extra config needed.

## Notes

- The backend's Qdrant runs **embedded** (writes to disk at `./qdrant_db`). On Hugging Face
  Spaces free tier this disk is ephemeral — it resets on redeploy/restart. For persistent
  storage, point `QDRANT_PATH`/collection at a hosted Qdrant Cloud instance instead (free tier
  available) and set `QDRANT_URL` accordingly (see the notebook's config cell for that pattern).
- CORS in `backend/api.py` is wide open (`allow_origins=["*"]`) to make local development easy.
  Lock this down to your actual Vercel domain before treating this as production-ready.
