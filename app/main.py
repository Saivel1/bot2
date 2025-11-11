from aiogram import types
from bot_instance import bot, dp
from config_data.config import settings
from logger_setup import logger
from db.database import async_session
from db.db_models import PaymentData, LinksOrm, PanelQueue
from repositories.base import BaseRepository
from misc.utils import get_links_of_panels
from marz.backend import MarzbanClient

from litestar import Litestar, post, get, Request
from litestar.response import Redirect,Template
from litestar.exceptions import NotFoundException, ServiceUnavailableException
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.static_files import StaticFilesConfig

from pathlib import Path
import json
import aiohttp, asyncio
from contextlib import asynccontextmanager



# # Импортируем handlers для регистрации
import handlers.start
import handlers.instructions
import handlers.subsmenu


BASE_DIR = Path(__file__).parent


# Lifespan для управления webhook
@asynccontextmanager
async def lifespan(app: Litestar):
    """Lifecycle events для установки/удаления webhook"""
    await bot.delete_webhook()
    logger.debug("Вебхук удалён")
    await bot.set_webhook(
        url=settings.WEBHOOK_URL,
        drop_pending_updates=False
    )
    logger.info(f"Webhook установлен: {settings.WEBHOOK_URL}")
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    #     await conn.run_sync(Base.metadata.create_all)

    yield

    await bot.session.close()
    await bot.delete_webhook()
    logger.info("Бот остановлен")


# Health check
@get("/")
async def root() -> dict:
    return {"status": "running"}


@get("/health")
async def health() -> dict:
    logger.debug(f'{"="*15}Health{"="*15}')
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
    logger.debug(f"UUID: {user_id}| Перешёл по ссылке гайда")
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
    logger.debug(f"Запрос от TelegramAPI пришёл.")
    data = await request.json()

    logger.debug(f"Udate TelegramApi {data}")
    update = types.Update(**data)

    await dp.feed_update(bot, update)
    return {"ok": True}


async def accept_panel(new_link: dict, username: str):
    logger.debug("Зашли в редактор БД")
    try:
        async with async_session() as session:
            repo = BaseRepository(session=session, model=LinksOrm)
            logger.debug(f'{"="*15} Репо создан {"="*15}')
            base_res = await repo.update_where(
                    data=new_link, 
                    user_id=username)
            logger.debug(f'Новая запись {base_res}')
    except Exception as e:
        logger.error(f'Ошибка при добавленни ссылки в БД {e}')
        raise ValueError


# Marzban webhook
@post("/marzban")
async def webhook_marz(request: Request) -> dict:
    data = await request.json()
    data_str = json.dumps(data, ensure_ascii=False)
    logger.debug(f'Пришёл запрос от Marzban {data_str[:20]}')

    pan = data[0]["user"]["subscription_url"]
    logger.debug(f'Пришёл запрос от Marzban с панели: {pan[:15]}')

    pan1 = False
    url_for_create = ""

    if pan.find("dns1") != -1: # Если в панели есть dns1 - значит это первая панель
        backend = MarzbanClient(settings.DNS2_URL)
        pan1 = True
        url_for_create = settings.DNS2_URL
    else:
        backend = MarzbanClient(settings.DNS1_URL)
        url_for_create = settings.DNS1_URL


    username = data[0]['username']
    inbounds = data[0]['user']['inbounds']['vless']
    id =       data[0]['user']['proxies']['vless']['id']
    expire =   data[0]['user']['expire']

    logger.debug(f'Данные пользователя: username --- {username} --- inbounds {inbounds} --- id {id}')
    try:
        res = await backend.create_user_options(username=username, id=id, inbounds=inbounds, expire=expire)

        if res is None:
            return {"error": 'При создании пользоваетеля возникла ошибка'}
        
        if res['status'] == 409:
            return {"msg": "тут нечего делать"}
            
        logger.debug(f'Создан пользователь: {res["username"]}') 

        new_link = dict()
        if pan1:
            new_link['panel_2'] = res["subscription_url"]
        else:
            new_link['panel_1'] = res["subscription_url"]
        
        logger.debug(f"Данные для бд {'='*15} {new_link} : {username}")
        # Добавляем в бд запись о новой ссылке
        await accept_panel(new_link=new_link, username=username)

    except ValueError:
        logger.error('Не получилось получить вторую ссылку')

    except Exception as e:
        logger.error("Ошибка с Марзбан")
        async with async_session() as session:
            repo = BaseRepository(session=session, model=PanelQueue)
            if not isinstance(expire, int):
                expire = int(expire) if expire else 0

            if not isinstance(inbounds, list):
                inbounds = inbounds if isinstance(inbounds, list) else [inbounds] if inbounds else []

            await repo.create({
                "uuid": id,
                "panel": url_for_create,
                "username": username,
                "expire": expire,
                "inbounds": inbounds
            })

    return {"ok": True}



# Subscription redirect
@get("/sub/{uuid:str}")
async def process_sub(uuid: str) -> Redirect:
    """Проверяем все панели параллельно"""
    
    links = await get_links_of_panels(uuid=uuid)
    logger.debug(f'Ссылки {links}')
    
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
            logger.debug(f"Подписка отдана: {link}")
            return Redirect(path=link)
    logger.warning("Панели недоступны")
    # Все недоступны
    raise ServiceUnavailableException(detail="All panels unavailable")


# Subscription redirect
@get("/sub/{uuid:str}/info")
async def process_sub_info(uuid: str) -> Redirect:
    """Проверяем все панели параллельно"""
    
    links = await get_links_of_panels(uuid=uuid)
    logger.debug(f'Ссылки {links}')
    
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
        link = link + "/info"
        if is_available:
            logger.debug(f"Подписка отдана: {link}")
            return Redirect(path=link)
    logger.warning("Панели недоступны")
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
        vpn_guide,
        process_sub_info
    ],
    lifespan=[lifespan],
    debug=False,
    static_files_config=[
        StaticFilesConfig(
            path="/static",
            directories=[BASE_DIR / "templates" / "static"],  # Папка, где лежит favicon.ico
        )
    ],
    template_config=templates
)