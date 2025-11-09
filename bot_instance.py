from aiogram import Bot, Dispatcher
from config_data.config import settings

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()