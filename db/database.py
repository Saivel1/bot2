from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config_data.config import settings
from db.db_models import *


engine = create_async_engine(
    url=settings.DATABASE_URL
    )

async_session = async_sessionmaker(
    bind=engine
)
