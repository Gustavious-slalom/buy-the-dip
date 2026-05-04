import pytest
from sqlmodel import SQLModel, create_engine, Session


@pytest.fixture(name="db_session")
def db_session_fixture():
    """In-memory SQLite session for model tests — avoids global metadata reload issues."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
