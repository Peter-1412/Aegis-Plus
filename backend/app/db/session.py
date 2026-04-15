import os
from pathlib import Path
from sqlmodel import create_engine, SQLModel, Session

BASE_DIR = Path(__file__).resolve().parent.parent.parent
default_db_path = BASE_DIR / "aegis.db"
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{default_db_path}")
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, connect_args=connect_args)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
