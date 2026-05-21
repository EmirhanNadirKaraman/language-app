import os
from pathlib import Path
from dotenv import load_dotenv
import asyncpg

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_pool: asyncpg.Pool | None = None


async def create_pool():
    global _pool
    _pool = await asyncpg.create_pool(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


async def close_pool():
    if _pool:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    return _pool
