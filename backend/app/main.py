"""FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

app = FastAPI(title="StoryGraph API", version="0.2.0", description="Spoiler-aware fictional-world graph exploration")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def root():
    return {"name": "StoryGraph", "docs": "/docs", "api": "/api"}
