from pydantic import BaseModel

class Post(BaseModel):
    title: str
    link: str
    comments: list[str] | None = None
    html: str | None = None

