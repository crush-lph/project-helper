from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    path: str = Field(description="仓库相对路径，例如 src/main.py")


class SearchRepoInput(BaseModel):
    query: str = Field(description="搜索关键词，例如 FastAPI、def handle、class User")


class SymbolQueryInput(BaseModel):
    query: str = Field(description="符号名或部分符号名，例如 create_app、Service.health")
