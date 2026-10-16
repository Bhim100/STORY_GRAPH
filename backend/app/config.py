"""Configuration module for StoryGraph backend."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Locate root directory and load .env
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# FalkorDB / Redis Connection Settings
FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_PASSWORD = os.getenv("FALKORDB_PASSWORD", None) or None
FALKORDB_USERNAME = os.getenv("FALKORDB_USERNAME", None) or None
GRAPH_NAME = os.getenv("GRAPH_NAME", "glass_orchard")

# LLM Providers (for Phase 5)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
