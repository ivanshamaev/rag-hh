from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://rag:rag@localhost:5432/rag_hh"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
