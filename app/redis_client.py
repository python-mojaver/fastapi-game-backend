from fakeredis import FakeRedis

# شمارندهٔ کلیک در نسخهٔ نمونه‌کار با شبیه‌ساز محلی Redis کار می‌کند.
redis_client = FakeRedis(decode_responses=True)


def get_redis():
    return redis_client
