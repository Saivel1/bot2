from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from keyboards.deps import back
from config_data.config import settings

class MainKeyboard:
    
    @staticmethod
    def main_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Подписка и ссылки", callback_data="subs")],
            [InlineKeyboardButton(text="📱 Инструкция", callback_data="instruction")]
        ])


class Instruction:

    @staticmethod
    def web_app_keyboard(uuid):
        return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Инструкция по установке",
            web_app=WebAppInfo(url=f"https://9a453bca4387626f.ivvpn.world/vpn-guide/{uuid}")
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="start_menu")]
    ])