from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

data_dir = Path(__file__).resolve().parent / ".demo-data"
data_dir.mkdir(exist_ok=True)
engine = create_engine(URL.create("sqlite", database=str(data_dir / "game.sqlite3")))
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    with SessionLocal() as session:
        yield session
