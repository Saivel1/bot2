from aiogram import F, types
from aiogram.filters import Command
from bot_instance import dp
from keyboards.markup import Admin
from aiogram.types import CallbackQuery
from logger_setup import logger
from misc.utils import get_user, create_user
from marz.backend import MarzbanClient
from config_data.config import settings as s



@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id #type: ignore
    logger.debug(f"ID : {user_id} | Ввёл команду /id")
    if user_id != 482410857:
        logger.info(f'User {user_id} попытался запросить админ команду')
        return
    
    await message.answer(
        text='Админ команды',
        reply_markup=Admin.main_keyboard()
    )

@dp.callback_query(F.data == 'admin_menu')
async def cb_admin(callback: CallbackQuery):
    user_id = callback.from_user.id #type: ignore
    logger.debug(f"ID : {user_id} | Ввёл команду /id")
    if user_id != 482410857:
        logger.info(f'User {user_id} попытался запросить админ команду')
        await callback.answer()
        return
    
    await callback.message.edit_text( #type: ignore
        text='Админ команды',
        reply_markup=Admin.main_keyboard()
    )
    

@dp.callback_query(F.data == 'health')
async def health_check(callback: CallbackQuery):
    pan1 = MarzbanClient(url=s.DNS1_URL)
    pan2 = MarzbanClient(url=s.DNS2_URL)

    res_1 = await pan1.health_check_custom()
    res_2 = await pan2.health_check_custom()

    ANS_TEXT = f"""
Проверка досутпности:

Ответь от панели1:
({s.DNS1_URL})

{res_1}

Ответь от панели2:
({s.DNS2_URL})

{res_2}
"""


    await callback.message.edit_text( #type: ignore
        text=ANS_TEXT,
        reply_markup=Admin.back()
    )

@dp.callback_query(F.data == 'users_cnt')
async def users_cnt(callback: CallbackQuery):
    client = MarzbanClient(url=s.M_DIGITAL_URL)
    users = await client.get_users()
    if users is None:
        users = dict()
        users['total'] = 'Ошибка'

    ANS_TEXT = f"""
Количество пользователей: {users['total']}
"""
    

    await callback.message.edit_text( #type: ignore
        text=ANS_TEXT,
        reply_markup=Admin.back()
    )