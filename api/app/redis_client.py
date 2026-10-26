from redis.asyncio import Redis

from app.config import get_settings

redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
