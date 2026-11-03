from fakeredis import FakeRedis

# Redis-compatible counters run locally in this demo; no external connection.
redis_client = FakeRedis(decode_responses=True)


def get_redis():
    return redis_client
