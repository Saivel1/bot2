from aiogram import types
from bot_instance import bot, dp
from config_data.config import settings
from contextlib import asynccontextmanager
from logger_setup import logger
from db.database import engine, async_session
from db.db_models import Base, PaymentData
from repositories.base import BaseRepository
from keyboards.deps import BackButton
from misc.utils import modify_user, calculate_expire, get_user, new_date, get_links_of_panels
import aiohttp, asyncio
from marz.backend import marzban_client
from litestar import get, post, Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.datastructures import State
from litestar.response import Template
from pathlib import Path
from litestar.template.config import TemplateConfig
from litestar.response import Redirect
from litestar.exceptions import NotFoundException, ServiceUnavailableException
from litestar.status_codes import HTTP_302_FOUND


# # Импортируем handlers для регистрации
import handlers.start
import handlers.instructions
import handlers.paymenu
import handlers.subsmenu
import handlers.trial


# app/main.py
from litestar import Litestar, post, get, Request
from litestar.response import Redirect
from litestar.exceptions import NotFoundException, ServiceUnavailableException
from litestar.datastructures import State
from contextlib import asynccontextmanager

import asyncio
import aiohttp
from aiogram import types


# Lifespan для управления webhook
@asynccontextmanager
async def lifespan(app: Litestar):
    """Lifecycle events для установки/удаления webhook"""
    await bot.set_webhook(
        url=settings.WEBHOOK_URL,
        drop_pending_updates=False
    )
    print(f"Webhook установлен: {settings.WEBHOOK_URL}")
    
    yield
    
    await bot.delete_webhook()
    await bot.session.close()
    print("Бот остановлен")


# Health check
@get("/")
async def root() -> dict:
    return {"status": "running"}


@get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Telegram webhook
@post("/webhook")
async def webhook(request: Request) -> dict:
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}


# Marzban webhook
@post("/marzban")
async def webhook_marz(request: Request) -> dict:
    data = await request.json()
    logger.info(data)
    return {"ok": True}


# Yookassa payment webhook
@post("/pay")
async def yoo_kassa(request: Request) -> dict:
    data = await request.json()
    event = data.get('event')
    order_id = data.get('object', {}).get("id", {})

    if order_id == {}:
        logger.warning(f'{order_id} Response: {data}')
        return {"status": "ne-ok"}
    
    obj = await change_status(order_id=order_id, status=event)
    if not obj:
        logger.info(f"Order: {order_id} was canceled or TimeOut")
        return {"response": "Order was canceled"}
    
    obj_data = data.get("object", {})
    pay_id, pay_am = obj_data.get('id'), obj_data.get('amount')

    logger.info(f'{pay_id} | {pay_am}')
    user_marz = await marzban_client.get_user(user_id=obj.user_id)

    user = await get_user(user_id=obj.user_id)
    expire = calculate_expire(old_expire=user_marz['expire']) #type: ignore
    new_expire = new_date(expire=expire, amount=pay_am['value'])

    try:
        await modify_user(username=obj.user_id, expire=new_expire)
        logger.info(f"Для пользователя {obj.user_id} оплата и обработка прошли успешно.")

        await bot.send_message(
            chat_id=obj.user_id, #type: ignore
            text=f"Оплата прошла успешно на сумму: {obj.amount}", #type: ignore
            reply_markup=BackButton.back_start()
        )

        await bot.send_message(
            chat_id=482410857,
            text=f"Пользователь {obj.user_id} заплатил {obj.amount}"
        )
    except Exception as e:
        logger.warning(e)
        await bot.send_message(
            text="Возникла ошибка, напиши в поддержку /help",
            chat_id=obj.user_id
        )

    return {"ok": True}


# Subscription redirect
@get("/sub/{uuid:str}")
async def process_sub(uuid: str) -> Redirect:
    """Проверяем все панели параллельно"""
    
    links = await get_links_of_panels(uuid=uuid)
    
    if not links:
        raise NotFoundException(detail="Subscription not found")
    
    async def check_panel(link: str) -> tuple[bool, str]:
        """Проверить доступность панели"""
        try:
            timeout = aiohttp.ClientTimeout(total=3.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                response = await session.get(url=link)
                return (response.status in (200, 201), link)
        except Exception:
            return (False, link)
    
    # Проверяем все панели параллельно
    results = await asyncio.gather(*[check_panel(link) for link in links])
    
    # Выбираем первую рабочую
    for is_available, link in results:
        if is_available:
            logger.info(f"Подписка отдана: {link}")
            return Redirect(path=link)
    
    # Все недоступны
    raise ServiceUnavailableException(detail="All panels unavailable")


# Вспомогательная функция (твоя существующая логика)
async def change_status(order_id: str, status: str):
    st = status.split(".")[1]
    async with async_session() as session:
        repo = BaseRepository(session=session, model=PaymentData)
        res = await repo.update_one({
            "status": st
        }, payment_id=order_id)
        if st == 'canceled':
            await repo.delete_where(payment_id=order_id)
            return False
        if st == 'waiting_for_capture':
            return None
        return res


# Создание приложения
app = Litestar(
    route_handlers=[
        root,
        health,
        webhook,
        webhook_marz,
        yoo_kassa,
        process_sub,
    ],
    lifespan=[lifespan],
    debug=True
)