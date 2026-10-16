"""FastAPI application entrypoint for StoryGraph."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

app = FastAPI(
    title="StoryGraph API",
    version="0.4.0",
    description="Spoiler-aware fictional-world narrative graph exploration API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "name": "StoryGraph API",
        "status": "online",
        "docs": "/docs",
        "api": "/api",
    }
