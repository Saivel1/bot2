from urllib.parse import unquote

# Название кнопок и колбэки
prices = [
    ("📅 50 ₽ • 1 месяц", 'pay_50'),
    ("📆 150 ₽ • 3 месяца", 'pay_150'),
    ("🗓 300 ₽ • 6 месяцев", 'pay_300'),
    ("📋 600 ₽ • 12 месяцев", 'pay_600')
]

# Цена и количество месяцев подписки за эту цену
add_monthes = {
    50: 1,
    150: 3,
    300: 6,
    600: 12
}

async def get_links(links: list):
    response = []
    for link in links:
        sta = link.find("#")
        encoded = link[sta+1:]
        text = unquote(encoded)
        response.append(text)
    return response