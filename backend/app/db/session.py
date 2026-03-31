import os
from sqlmodel import create_engine, SQLModel, Session

DB_URL = os.getenv("DATABASE_URL", "sqlite:///aegis.db")
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, connect_args=connect_args)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
