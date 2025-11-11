from aiogram import types
from bot_instance import bot, dp
from config_data.config import settings
from contextlib import asynccontextmanager
from logger_setup import logger
from db.database import engine, async_session
from db.db_models import Base, PaymentData, LinksOrm
from repositories.base import BaseRepository
from keyboards.deps import BackButton
from misc.utils import modify_user, calculate_expire, get_user, new_date, get_links_of_panels
import aiohttp, asyncio
from marz.backend import MarzbanClient
from litestar import get, post, Litestar
from litestar.response import Redirect
from litestar.exceptions import NotFoundException, ServiceUnavailableException
from litestar.status_codes import HTTP_302_FOUND
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from pathlib import Path
from litestar.response import Template
from litestar.static_files import StaticFilesConfig


# # Импортируем handlers для регистрации
import handlers.start
import handlers.instructions
import handlers.subsmenu


# app/main.py
from litestar import Litestar, post, get, Request
from litestar.response import Redirect
from litestar.exceptions import NotFoundException, ServiceUnavailableException
from contextlib import asynccontextmanager

import asyncio
import aiohttp
from aiogram import types

BASE_DIR = Path(__file__).parent


# Lifespan для управления webhook
@asynccontextmanager
async def lifespan(app: Litestar):
    """Lifecycle events для установки/удаления webhook"""
    await bot.delete_webhook()
    await bot.set_webhook(
        url=settings.WEBHOOK_URL,
        drop_pending_updates=False
    )
    print(f"Webhook установлен: {settings.WEBHOOK_URL}")
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    #     await conn.run_sync(Base.metadata.create_all)

    yield

    await bot.session.close()
    await bot.delete_webhook()
    print("Бот остановлен")


# Health check
@get("/")
async def root() -> dict:
    return {"status": "running"}


@get("/health")
async def health() -> dict:
    return {"status": "ok"}

templates = TemplateConfig(
    directory=BASE_DIR / Path("templates"),
    engine=JinjaTemplateEngine,
)


# Route handler
@get("/vpn-guide/{user_id:str}")
async def vpn_guide(user_id: str) -> Template:
    user_data = {
        "subscription_link": f"{settings.IN_SUB_LINK}{user_id}",
        "user_id": user_id
    }

    return Template(
        template_name="guide.html",
        context={
            "user_data": user_data,
            "title": "VPN Setup Guide"
        }
    )


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
    pan = data[0]["user"]["subscription_url"]
    pan1 = False

    if pan.find("dns1") != -1: # Если в панели есть dns1 - значит это первая панель
        backend = MarzbanClient(settings.DNS2_URL)
        pan1 = True
    else:
        backend = MarzbanClient(settings.DNS1_URL)

    username = data[0]['username']
    inbounds = data[0]['user']['inbounds']['vless']
    id = data[0]['user']['proxies']['vless']['id']
    expire = data[0]['user']['expire']

    logger.info(f'username --- {username} --- inbounds {inbounds} --- id {id}')
    try:
        res = await backend.create_user_options(username=username, id=id, inbounds=inbounds, expire=expire)
        if res is None:
             return {"error": 'При создании пользоваетеля возникла ошибка'}
        logger.info(res["username"]) 
        async with async_session() as session:
            repo = BaseRepository(session=session, model=LinksOrm)
            new_link = dict()
            if pan1:
                new_link['panel_2'] = res["subscription_url"]
            else:
                new_link['panel_1'] = res["subscription_url"]

            await repo.update_one(
                new_link, 
                username=username)

    except:
        pass
    return {"ok": True}



# Subscription redirect
@get("/sub/{uuid:str}")
async def process_sub(uuid: str) -> Redirect:
    """Проверяем все панели параллельно"""
    
    links = await get_links_of_panels(uuid=uuid)
    logger.info(f'Ссылки {links}')
    
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
        process_sub,
        vpn_guide
    ],
    lifespan=[lifespan],
    debug=True,
    static_files_config=[
        StaticFilesConfig(
            path="/vpn-guide/static",
            directories=[BASE_DIR / "templates" / "static"],  # Папка, где лежит favicon.ico
        )
    ],
    template_config=templates
)