# FastAPI Clicker Game Backend

A local portfolio demo of a clicker game backend. Players earn virtual coins by spending energy, progress through levels, buy upgrade cards, claim daily rewards, and compete on a leaderboard.

## Run locally

Use Python 3.12. From this directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app\main.py
```

Open [Swagger UI](http://127.0.0.1:8000/docs). Run **POST /demo/session**, copy the `access_token` into **Authorize**, and try these endpoints:

| Endpoint | What it shows |
| --- | --- |
| GET /game/me | Coins, energy, and level progress |
| POST /game/click | Earn coins and spend energy |
| GET /cards/ | List upgrade cards |
| POST /cards/{card_id}/buy | Buy a card with virtual coins |
| POST /daily/claim | Claim today's reward |
| GET /game/leaderboard | Compare synthetic players |

The demo seeds two synthetic players and one card in its own SQLite database. Click throttling uses a local Redis emulator. No external credentials or services are required. This is a loopback-only demo: anyone with local access can obtain a token for the same synthetic player. Restarting the server invalidates demo tokens; gameplay state stays in the local demo database.

The original project used PostgreSQL, Redis and SMS OTP. This edition demonstrates the gameplay API with a synthetic session instead. All currency and rewards are virtual.
