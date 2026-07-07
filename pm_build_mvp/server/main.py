"""
FastAPI server hosting the PM planning workflow.

Run from pm_build_mvp/ so `harness`, `workflows`, `server` resolve:

    uvicorn server.main:app --reload --port 8000

The React dev server (frontend/, port 5173) talks to this API; CORS below
allows the Vite default origins.
"""
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness import event_stream
from harness.workspace_init import init_workspace

from server.routes import agents, decisions, documents, intent, kernel, runs, stream, workspace

_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app() -> FastAPI:
    init_workspace()
    # Same-process publish: every canonical event also reaches SSE subscribers.
    event_stream.enable()

    app = FastAPI(title="PM Build MVP Server", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(runs.router)
    app.include_router(stream.router)
    app.include_router(intent.router)
    app.include_router(workspace.router)
    app.include_router(kernel.router)
    app.include_router(decisions.router)
    app.include_router(agents.router)
    app.include_router(documents.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
