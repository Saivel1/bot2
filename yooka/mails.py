import aiohttp
from config_data.config import settings as s
from logger_setup import logger

class Anymessage():
    def __init__(self):
        self.email = None

    async def get_balance(self):
        async with aiohttp.ClientSession() as session:
            url = f'https://api.anymessage.shop/user/balance?token={s.ANY_TOKEN}'
            response = await session.get(url)
            data = await response.json()
            return data

    async def order_email(self):
        async with aiohttp.ClientSession() as session:
            try:
                url = f'https://api.anymessage.shop/email/order?token={s.ANY_TOKEN}&site={s.ANY_SITE}&domain={s.ANY_DOMAIN}'
                response = await session.get(url)
                data = await response.json()
                self.email = data['email']
                return self.email
            except Exception as e:
                balance = await self.get_balance()
                logger.warning(f'Баланс: {balance}')
                logger.warning(f'Ошибка в покупке email, функции order_email: {e}')