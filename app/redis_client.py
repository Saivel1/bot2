from redis.asyncio import Redis
from config_data.config import settings


async def init_redis() -> Redis:
    """Инициализация Redis подключения"""
    return await Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASS,
        db=0,  # база данных (0-15)
        decode_responses=True,  # автоматически декодирует байты в строки
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )