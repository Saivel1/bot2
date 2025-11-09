from aiogram import F
from bot_instance import dp
from aiogram.types import CallbackQuery
from logger_setup import logger
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from misc.utils import get_user_in_links
from keyboards.markup import Instruction



@dp.callback_query(F.data == "instruction")
async def instriction_menu(callback: CallbackQuery):
    user_id = callback.from_user.id #type: ignore
    logger.info(f"ID : {user_id} | Нажал кнопку инстуркция")

    user = await get_user_in_links(user_id=user_id)
    if not user:
        await callback.answer("Нужно преобрести подписку или активировать пробный период")
        return

    uuid = user.uuid
    await callback.message.edit_text( #type:ignore
        "🪞 Нажмите на кнопку ниже для просмотра инструкции:",
        reply_markup=Instruction.web_app_keyboard(uuid=uuid)
    )