from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, SessionLocal, engine
from models import Card, User
from routes import auth, cards, daily_reward, game, leaderboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, coins in ((auth.DEMO_PLAYER, 750), ("demo-rival", 2500)):
            if not db.query(User).filter_by(username=name).first():
                db.add(User(username=name, coins=coins, energy=1000, max_energy=1000))
        if not db.query(Card).filter_by(name="Energy Workshop").first():
            db.add(Card(name="Energy Workshop", category="demo", price=500))
        db.commit()
    yield


app = FastAPI(title="Clicker Game Backend | Local Demo", lifespan=lifespan)
for router in (auth.router, game.router, cards.router, daily_reward.router, leaderboard.router):
    app.include_router(router)


@app.get("/")
def root():
    return {"mode": "local demo", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
