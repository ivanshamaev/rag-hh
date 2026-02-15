from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://rag:rag@localhost:5432/rag_hh"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Опционально: OAuth hh.ru — токен и при необходимости client_id/client_secret (см. https://dev.hh.ru/)
    hh_token: str | None = None
    hh_user_agent: str = "RAG-HH/1.0"
    hh_client_id: str | None = None
    hh_client_secret: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
