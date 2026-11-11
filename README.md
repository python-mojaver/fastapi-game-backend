# FastAPI Clicker Game Backend

A local portfolio demo of a clicker game backend. Players earn virtual coins by spending energy, progress through levels, buy upgrade cards, claim daily rewards, and compete on a leaderboard.

Two RabbitMQ workers process demo player registrations and leaderboard CSV exports. Both APIs return a job ID so the caller can check the result later.

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

The demo seeds two synthetic players and one card in its own SQLite database. Click throttling uses a local Redis emulator. The gameplay endpoints run without external credentials or services. This is a loopback-only demo: anyone with local access can obtain a token for the same synthetic player. Restarting the server invalidates demo tokens; gameplay state stays in the local demo database.

The original project used PostgreSQL, Redis and SMS OTP. This local edition uses a synthetic session for gameplay and accepts username-only registrations to demonstrate queue processing. All currency and rewards are virtual.

## تمرین RabbitMQ با خروجی جدول رتبه‌بندی

این تمرین به Docker و افزونهٔ Docker Compose نیاز دارد. در ویندوز می‌توانید Docker Desktop را اجرا کنید. از پوشهٔ پروژه در PowerShell سرویس RabbitMQ را بالا بیاورید و API را طبق دستورهای بخش اول اجرا کنید.

```powershell
docker compose -f compose.rabbitmq.yaml up -d --wait
```

1. در Swagger با `POST /demo/session` توکن بگیرید و روی **Authorize** بزنید. با `POST /game/leaderboard/exports` درخواست گزارش بفرستید. وقتی RabbitMQ دریافت پیام را تأیید کند، API با `202 Accepted` یک `job_id` و مسیر دانلود برمی‌گرداند. هنگام قطع ارتباط با بروکر، API به‌جای `202` خطای `503` برمی‌گرداند.
2. قبل از روشن کردن Worker، صفحهٔ مدیریت RabbitMQ را در `http://127.0.0.1:15672` باز کنید. نام کاربری محلی `game_demo` و رمز نمونه `local_demo_only` است. در صف `leaderboard.exports` تعداد پیام‌های **Ready** را ببینید. مسیر دانلود تا زمانی که فایل آماده شود `404` برمی‌گرداند.
3. در یک PowerShell جدا از همان پوشهٔ پروژه، Worker را اجرا کنید. بعد از پیام **Leaderboard export … is ready**، درخواست `GET /game/leaderboard/exports/{job_id}` را با همان توکن بفرستید تا فایل CSV حداکثر ۱۰۰ نفر اول را بگیرید. فایل از وضعیت جدول در زمان پردازش ساخته می‌شود.

```powershell
.\.venv\Scripts\python.exe app\leaderboard_export.py
```

- `enqueue_export` نقش **Producer** دارد. اطلاعات کار را به JSON تبدیل می‌کند و به صف می‌فرستد.
- `consume_export` نقش **Consumer** دارد. پیام را می‌خواند، با `write_export` فایل CSV را در همان فضای دادهٔ نسخهٔ محلی بازی می‌سازد و سپس به RabbitMQ تأیید **ACK** می‌دهد. اگر Worker قبل از ACK قطع شود، RabbitMQ می‌تواند پیام را دوباره تحویل دهد. اگر فایل همان کار قبلاً کامل شده باشد، Worker از همان فایل استفاده می‌کند.

## صف ثبت‌نام آزمایشی بازیکن

با RabbitMQ و API روشن، در Swagger مسیر `POST /demo/register` را اجرا کنید و `username` بدهید. مثلاً `player-101`. API پس از تأیید RabbitMQ، پاسخ `202` و شناسهٔ درخواست را برمی‌گرداند. در مسیر `GET /demo/register/{job_id}` می‌توانید وضعیت را ببینید.

1. با Worker خاموش چند درخواست ثبت کنید. در پنل RabbitMQ تعداد پیام‌های **Ready** در صف `game.registrations` بالا می‌رود و وضعیت درخواست‌ها `queued` است.
2. Worker ثبت‌نام را در یک ترمینال جدا اجرا کنید. این Worker حساب بازیکن را در SQLite می‌سازد، نتیجه را ذخیره می‌کند و بعد به پیام **ACK** می‌دهد.
3. وضعیت درخواست‌ها را دوباره بگیرید. `created` یعنی بازیکن ساخته شده و شناسهٔ او در `user_id` می‌آید. اگر دو نفر هم‌زمان یک نام بدهند، یکی `created` و دیگری `username_taken` می‌گیرد. اگر API نتواند تأیید RabbitMQ را بگیرد، پاسخ `503` می‌دهد. از شناسهٔ همان پاسخ برای بررسی وضعیت `publish_unconfirmed` یا نتیجهٔ نهایی استفاده کنید.

```powershell
.\.venv\Scripts\python.exe app\registration_worker.py
```

مسیرهای ثبت‌نام در `app/routes/auth.py` هستند. برای دنبال کردن پردازش، `enqueue_registration` و `create_player` را در `app/registration_worker.py` ببینید. پیام صف فقط شناسهٔ درخواست را دارد. اطلاعات ثبت‌نام و نتیجه در دیتابیس محلی ذخیره می‌شوند. ثبت‌نام این دمو با نام کاربری انجام می‌شود و مسیر ورود آزمایشی بازی همچنان `POST /demo/session` است.
