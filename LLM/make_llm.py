from langchain_ollama import ChatOllama
from API.config import settings
from langchain_openai import ChatOpenAI

def make_llm(model: str | None = None, temperature: float | None = None):
    provider = settings.LLM_PROVIDER.lower()
    temp = temperature if temperature is not None else settings.DEFAULT_TEMPERATURE

    if provider == "ollama":
        return ChatOllama(
            model=model or settings.DEFAULT_LLM_MODEL,
            temperature=temp,
            base_url=settings.OLLAMA_BASE_URL,
        )

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")

        return ChatOpenAI(
            model= settings.OPENAI_MODEL,
            temperature=temp,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,  # None is OK
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")