from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
from app.config import settings

engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

@contextmanager
def get_session():
    with Session(engine) as s:
        yield s
