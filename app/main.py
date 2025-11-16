from aiogram import types
from bot_instance import bot, dp
from config_data.config import settings
from keyboards.deps import BackButton
from logger_setup import logger
from db.database import async_session
from db.db_models import PaymentData, LinksOrm
from repositories.base import BaseRepository
from misc.utils import get_links_of_panels, get_user, modify_user, new_date, create_user_sync, update_user_sync
from marz.backend import MarzbanClient
from app.redis_client import init_redis
from redis.asyncio import Redis
import app.redis_client as redis_module 
from app.redis_client import close_redis


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

    global redis_client

    redis_module.redis_client = await init_redis()
    await redis_module.redis_client.ping() #type: ignore
    logger.info("Redis connected")


    yield


    await close_redis()
    logger.info("Redis disconnected")

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
    logger.debug(data)
    data_str = json.dumps(data, ensure_ascii=False)

    username = data[0]['username']
    action   = data[0]['action']
    cache_key = f"marzban:{username}:{action}"

    if action == "reached_days_left":
        ttl = 3600  # 1 час - чтобы не спамить каждое обновление
    elif action == "user_expired":
        ttl = 300   # 5 минут
    else:
        ttl = 20    # 20 секунд для остальных

    logger.debug(f'Пришли данные до Редиса {username} | {action} | {cache_key}')
    exist = await redis_module.redis_client.exists(cache_key) #type: ignore
    logger.debug(exist)

    if exist: #type: ignore
        logger.info(f'Дублирование операции для {username}')
        return {'msg': 'operation for user been'}

    logger.debug(action)
    await redis_module.redis_client.set(cache_key, "1", ex=ttl) #type: ignore
    logger.debug('Добавлен в Redis')


    logger.debug(f'Пришёл запрос от Marzban {data_str[:20]}')
    if action == 'user_created':
        await create_user_sync(data=data)

    elif action == 'user_updated':
        await update_user_sync(data=data)

    elif action == 'user_expired':
        print('Отправить сообщение юзеру')
        
    elif action == 'reached_days_left':
        print('Отправить сообщение юзеру День остался')

    return {"ok": True}



# Subscription redirect
@get("/sub/{uuid:str}")
async def process_sub(uuid: str) -> Redirect:
    """Проверяем все панели параллельно"""
    
    links = await get_links_of_panels(uuid=uuid)
    logger.debug(f'Ссылки {links}')
    
    if not links:
        raise NotFoundException(detail="Subscription not found")
    
    async def check_panel(link: str, max_attempts: int = 3, delay: int = 1) -> tuple[bool, str]:
        """Проверить доступность панели с retry"""
        timeout = aiohttp.ClientTimeout(total=3.0)
        connector = aiohttp.TCPConnector(ssl=False)
        
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector
                ) as session:
                    response = await session.get(url=link)
                    
                    # Успех
                    if response.status in (200, 201):
                        return (True, link)
                    
                    # Серверные ошибки - retry
                    elif 500 <= response.status < 600 and attempt < max_attempts - 1:
                        logger.warning(f"Panel {link} retry {attempt + 1}/{max_attempts}: статус {response.status}")
                        await asyncio.sleep(delay * (attempt + 1))
                        continue
                    
                    # Клиентские ошибки - сразу False
                    else:
                        return (False, link)
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_attempts - 1:
                    logger.warning(f"Panel {link} retry {attempt + 1}/{max_attempts}: {e}")
                    await asyncio.sleep(delay * (attempt + 1))
                else:
                    logger.debug(f"Panel {link} недоступна после {max_attempts} попыток")
                    return (False, link)
            
            except Exception as e:
                logger.error(f"Неожиданная ошибка при проверке {link}: {e}")
                return (False, link)
        
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
    
    backend = MarzbanClient(settings.M_DIGITAL_URL)
    
    obj_data = data.get("object", {})
    pay_id, pay_am = obj_data.get('id'), obj_data.get('amount')
    logger.info(f'{pay_id} | {pay_am}')
    
    user_marz = await backend.get_user(user_id=obj.user_id)
    expire = calculate_expire(old_expire=user_marz['expire']) #type: ignore
    new_expire = new_date(expire=expire, amount=pay_am['value'])
    
    try:
        await modify_user(username=obj.user_id) #, expire=new_expire)
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


# Вспомогательная функция (твоя существующая логика)
async def change_status(order_id: str, status: str) -> PaymentData | None:
    '''
    Это функция принимает status: str, который должен быть
    smth.succeeded | smth.canceled | smth.waiting_for_capture

    В status обязательно должна быть точка-разделитель, по ней
    делится на smth - который не имеет значения, и смысловую часть после точки

    1. Canceled - Возвращает -- None -- и удаляет запись из бд с order_id
    2. waiting_for_capture - Неизвестный ответ возвращает -- None --
    3. Succeeded - меняет статус у записи с order_id и возвращает объект -- ORM --
    '''

    st = status.split(".")[1]
    if st == 'waiting_for_capture':
        return None
    async with async_session() as session:
        repo = BaseRepository(session=session, model=PaymentData)
        if st == 'succeeded':
            res = await repo.update_one({
                "status": st
            }, payment_id=order_id)
            logger.debug(f'Ответ из БД после обновления {res}')
            return res
        elif st == 'canceled':
            res = await repo.delete_where(payment_id=order_id)
            logger.debug(f'Ответ из БД после удаления {res}')
            return None
        


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
    debug=False,
    static_files_config=[
        StaticFilesConfig(
            path="/static",
            directories=[BASE_DIR / "templates" / "static"],  # Папка, где лежит favicon.ico
        )
    ],
    template_config=templates
)