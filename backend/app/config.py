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

# LLM provider (optional; graph answers remain available without it)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def get_llm_client():
    """Returns an initialized (OpenAI-compatible client, model_name) or (None, None).
    
    Automatically detects Google Gemini API keys (starting with 'AQ.' or 'AIza', or GEMINI_API_KEY)
    and configures the native OpenAI-compatible Gemini endpoint.
    """
    api_key = GEMINI_API_KEY or OPENAI_API_KEY
    if not api_key:
        return None, None

    is_gemini = bool(GEMINI_API_KEY) or api_key.startswith("AQ.") or api_key.startswith("AIza")

    from openai import OpenAI
    if is_gemini:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        return OpenAI(api_key=api_key, base_url=base_url), model
    else:
        base_url = OPENAI_BASE_URL or None
        model = OPENAI_MODEL
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url), model
        return OpenAI(api_key=api_key), model
