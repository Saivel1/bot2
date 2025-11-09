from urllib.parse import unquote
from dataclasses import dataclass
from repositories.base import BaseRepository
from db.database import async_session
from db.db_models import UserOrm, LinksOrm
from datetime import datetime
from marz.backend import marzban_client
from misc.bot_setup import add_monthes
from datetime import timedelta
from logger_setup import logger
import uuid

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


async def get_user(user_id):
    user_id = str(user_id)
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=UserOrm)
        res = await user_repo.get_one(user_id=user_id)
        return res

async def get_user_in_links(user_id):
    user_id = str(user_id)
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=LinksOrm)
        logger.info(user_id)
        res = await user_repo.get_one(user_id=user_id)
        logger.info(res)
        return res
    

async def get_links_of_panels(uuid: str) -> list | None:
    async with async_session() as session:
        user_repo = BaseRepository(session=session, model=LinksOrm)
        res = await user_repo.get_one(uuid=uuid)
        if res is None:
            return None
        return [res.panel_1, res.panel_2]
    

async def modify_user(username, expire: datetime):
    data = datetime.timestamp(expire)
    data = int(data)
    username = str(username)

    user = await marzban_client.get_user(user_id=username)
    if not user:
        user = await marzban_client.create_user(username=username)
    
    link = await get_user_in_links(user_id=username)
    logger.info(link)
    if not link:
        async with async_session() as session:
            repo = BaseRepository(session=session, model=LinksOrm)
            user_uuid = str(uuid.uuid4())
            data_panel = {
                "user_id": username,
                "uuid": user_uuid,
            }
            sub_url = user['subscription_url'] #type: ignore
            logger.info(data_panel)
            if sub_url.find("world") != -1:
                data_panel["panel_1"] = sub_url
            else:
                data_panel["panel_2"] = sub_url
            logger.info(data_panel)
            res = await repo.create(data_panel)
            logger.info(res)

        await marzban_client.modify_user(
            user_id=username, 
            expire=data
        )
    
    async with async_session() as session:
        repo = BaseRepository(session=session, model=UserOrm)
        await repo.update_one({
            "subscription_end": expire
        }, user_id=username)

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
        return res
    
async def get_sub_url(user_id):
    user_id = str(user_id)
    async with async_session() as session:
        repo = BaseRepository(session=session, model=LinksOrm)
        res = await repo.get_one(user_id=user_id)
    logger.info(res)
    return res