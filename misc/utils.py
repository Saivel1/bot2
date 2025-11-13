from urllib.parse import unquote
from dataclasses import dataclass
from repositories.base import BaseRepository
from db.database import async_session
from db.db_models import UserOrm, LinksOrm, PanelQueue
from datetime import datetime
from marz.backend import marzban_client
from misc.bot_setup import add_monthes
from datetime import timedelta
from logger_setup import logger
import uuid
from marz.backend import MarzbanClient
from config_data.config import settings
import json
from typing import Optional
from app.redis_client import redis_client

MONTH = 30

@dataclass(slots=True)
class LinksSub:
    sub_link: str
    links: list
    titles: list


async def to_link(lst_data: dict):
    links = lst_data.get("links")
    if links is None:
        return False
    
    titles = []
    for link in links:
        sta = link.find("#")
        encoded = link[sta+1:]
        text = unquote(encoded)
        titles.append(text)
    
    sub_link = lst_data.get('subscription_url')
    if sub_link is None:
        return None

    return LinksSub(
        sub_link=sub_link,
        links=links,
        titles=titles
    )

async def get_user_cached(user_id: str, ttl: int = 300) -> dict | None:
    """Получить пользователя с кэшированием на 5 минут"""
    cache_key = f"marzban:user:{user_id}"

    if redis_client is None:
        logger.error("❌ redis_client is None!")
        return None
    
    try:
        cached = await redis_client.get(cache_key)
        logger.debug(f"📦 Результат из Redis: {cached}")
    except Exception as e:
        logger.error(f"❌ Ошибка Redis GET: {e}")
        cached = None
    
    if cached:
        logger.info(f"✓ Cache HIT для {user_id}")
        try:
            return json.loads(cached)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            await redis_client.delete(cache_key)  # Удаляем битый кэш
    
    # Если нет в кэше - запрос к Marzban
    logger.debug(f"Cache miss для {user_id}, запрос к API")
    try:
        res = await marzban_client.get_user(user_id)
        logger.debug(f"📥 Ответ от Marzban: {type(res)} - {res}")
    except Exception as e:
        logger.error(f"❌ Ошибка запроса к Marzban: {e}")
        return None
    
    try:
        json_data = json.dumps(res)
        logger.debug(f"✓ JSON сериализация OK, длина: {len(json_data)}")
    except (TypeError, ValueError) as e:
        logger.error(f"❌ Не могу сериализовать в JSON: {e}")
        logger.error(f"Тип данных: {type(res)}")
        return res  # Возвращаем без кэша
    
    try:
        await redis_client.set(cache_key, json_data, ex=ttl)
        logger.info(f"✓ Сохранено в Redis: {cache_key}")
    except Exception as e:
        logger.error(f"❌ Ошибка Redis SET: {e}")
    
    return res


async def get_user(user_id) -> UserOrm | None:
    '''
    Эта функция принимает на вход user_id который может быть и строкой 
    и текстом. И возвращает запись из БД users с переданным user_id или None
    '''
    user_id = str(user_id)
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=UserOrm)
        res = await user_repo.get_one(user_id=user_id)
        return res


async def get_user_in_links(user_id) -> LinksOrm | None:
    '''
    Эта функция принимает на вход user_id который может быть и строкой 
    и текстом. И возвращает запись из БД links с переданным user_id или None
    '''
    user_id = str(user_id)
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=LinksOrm)
        logger.info(user_id)
        res = await user_repo.get_one(user_id=user_id)
        logger.debug(res)
        return res
    

async def get_links_of_panels(uuid: str) -> list | None:
    '''
    Эта функция принимает на вход uuid строку. 
    И возвращает списоков подписок для обеих панелей, 
    которые есть в таблице links для этого uuid.
    '''
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=LinksOrm)
        res = await user_repo.get_one(uuid=uuid)
        logger.debug(res)

        if res is None:
            return None
        return [res.panel_1, res.panel_2]
    

async def modify_user(username):
    username = str(username)

    user = await marzban_client.get_user(user_id=username)
    logger.debug(user)
    if user is None:
        user = await marzban_client.create_user(username=username)
        logger.info(f'Зареган {user}')
    
    link = await get_user_in_links(user_id=username)
    logger.debug(f"Это ссылка {link}")
    if not link:
        async with async_session() as session:
            repo = BaseRepository(session=session, model=LinksOrm)
            user_uuid = str(uuid.uuid4())
            data_panel = {
                "user_id": username,
                "uuid": user_uuid,
            }
            sub_url = user['subscription_url'] #type: ignore
            logger.debug(f"DATA PANEL: {data_panel}")
            if sub_url.find("world") != -1:
                data_panel["panel_1"] = sub_url
            else:
                data_panel["panel_2"] = sub_url
            logger.debug(f"DATA PANEL AFTER: {data_panel}")
            res = await repo.create(data_panel)
            logger.debug(res)

        await marzban_client.modify_user(
            user_id=username,
            expire=0
        )

    return True


def new_date(expire: datetime, amount: str):
    amount = amount.split(".")[0]
    amou = int(amount)
    cnt_monthes = add_monthes.get(amou)
    
    return expire + timedelta(days=cnt_monthes*MONTH) #type: ignore


def calculate_expire(old_expire):
    current_time = datetime.now()
    
    old_expire = datetime.fromtimestamp(old_expire)
    if old_expire is None:
        new_expire = current_time
    elif old_expire >= current_time:
        new_expire = old_expire
    else:
        new_expire = current_time
    
    return new_expire


async def create_user(user_id, username: str | None = None):
    user_id = str(user_id)
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=UserOrm)
        data = {
            "user_id": user_id
        }
        if username:
            data["username"] = username

        res = await user_repo.create(data)
    
    await modify_user(username=user_id)
    return res



async def get_sub_url(user_id):
    user_id = str(user_id)
    async with async_session() as session:
        repo = BaseRepository(session=session, model=LinksOrm)
        res = await repo.get_one(user_id=user_id)
    logger.info(res)
    return res


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
    


async def create_user_sync(data):
    '''
    Эта функция создаёт пользователя в Marzban принимая на вход
    данные из запроса от самого Marzban и перенаправляя его в другую 
    панель
    '''

    username = data[0]['username']

    pan = data[0]["user"]["subscription_url"]
    logger.debug(f'Пришёл запрос от Marzban с панели: {pan[:15]}')

    pan1 = False

    if pan.find("dns1") != -1: # Если в панели есть dns1 - значит это первая панель
        backend = MarzbanClient(settings.DNS2_URL)
        pan1 = True
    else:
        backend = MarzbanClient(settings.DNS1_URL)


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
        logger.error(f'Возникла ошибка: {e}')


async def update_user_sync(data):
    '''
    Эта функция создаёт пользователя в Marzban принимая на вход
    данные из запроса от самого Marzban и перенаправляя его в другую 
    панель
    '''
    username = data[0]['username']

    pan = data[0]["user"]["subscription_url"]
    logger.debug(f'Пришёл запрос от Marzban с панели: {pan[:15]}')

    pan1 = False

    if pan.find("dns1") != -1: # Если в панели есть dns1 - значит это первая панель
        backend = MarzbanClient(settings.DNS2_URL)
        pan1 = True
    else:
        backend = MarzbanClient(settings.DNS1_URL)

    expire =   data[0]['user']['expire']

    try:
        res = await backend.modify_user(user_id=username, expire=expire)

        if res is None:
            return {"error": 'При создании пользоваетеля возникла ошибка'}
        
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
        logger.error(f'Возникла ошибка: {e}')
    