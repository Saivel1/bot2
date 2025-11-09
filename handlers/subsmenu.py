from aiogram import F
from bot_instance import dp
from keyboards.builder import SubMenu
from keyboards.deps import BackButton
from aiogram.types import CallbackQuery
from logger_setup import logger
from marz.backend import marzban_client
from misc.utils import to_link, get_sub_url, get_user_in_links
from config_data.config import settings as s

text_pattern = """
🔐 **Ваши подписки IV VPN**

📋 Универсальная ссылка подписки:
(Нажмите для копирования)
"""

@dp.callback_query(F.data == "subs")
async def main_subs(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    logger.info(f"ID : {user_id} | Нажал Subs")
    res = await get_sub_url(user_id)
    if res is None:
        await callback.message.edit_text( #type: ignore
            text="❌ У вас пока нет активной подписки.\n\nОформите подписку для получения доступа к VPN.",
            reply_markup=BackButton.back_start()
        )
        return
    sub_link = res.uuid
    text_reponse = text_pattern
    text_reponse += "\n" + f"`{s.IN_SUB_LINK}{sub_link}`" #type: ignore
    res = await marzban_client.get_user(user_id)
    data = await to_link(res) #type: ignore
    await callback.message.edit_text( #type: ignore
        text=text_reponse,
        reply_markup=SubMenu.links_keyboard(data.titles), #type: ignore
        parse_mode="MARKDOWN"
    )

@dp.callback_query(F.data.startswith("sub_"))
async def process_sub(callback: CallbackQuery):
    sub_id = callback.data.replace("sub_", "") #type: ignore
    user_id = str(callback.from_user.id)
    logger.info(f"ID : {user_id} | Нажал {callback.data}")
    res = await marzban_client.get_user(user_id)
    if res is None:
        await callback.message.edit_text( #type: ignore
            text="❌ Подписка не найдена",
            reply_markup=BackButton.back_subs()
        )    
    data = await to_link(res) #type: ignore
    links_marz = data.links #type: ignore
    uuid = await get_user_in_links(user_id=user_id)
    sub_url = f"{s.IN_SUB_LINK + uuid.uuid}" #type: ignore
    link = links_marz[int(sub_id)] #type: ignore
    text_response = f"""🔐 <b>Ваши подписки IV VPN</b>

📋 <b>Универсальная ссылка:</b>
<code>{sub_url}</code>

🔑 <b>Ключ конфигурации:</b>
<code>{link}</code>

💡 <i>Используйте универсальную ссылку для автоматического обновления серверов, или ключ для ручной настройки.</i>
"""
    await callback.message.edit_text( #type: ignore
        text=text_response,
        reply_markup=SubMenu.links_keyboard(links=data.titles), #type: ignore
        parse_mode="HTML"
    )