from yookassa import Payment, Configuration
import uuid
import json
import logging
from config_data.config import settings
from logger_setup import logger

Configuration.account_id = settings.ACCOUNT_ID
Configuration.secret_key = settings.SECRET_KEY


class PaymentYoo:
    def __init__(self):
        self.id = None
        self.link = None

    async def create_payment(self, amount: int, plan: str, email: str):
        payment_id = uuid.uuid4()
        try:
            payment = Payment.create({
                "amount": {
                    "value": amount,
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/ivvpnbot"
                },
                "capture": True,
                "description": "Подписка на VPN. В боте @ivvpnbot",
                "receipt": {
                    "customer": {
                            "email": email # Обязательно для отправки чека
                        },
                        "items": [
                            {
                                "description": plan,
                                "quantity": 1.0,
                                "amount": {
                                    "value": amount,
                                    "currency": "RUB"
                                },
                                "vat_code": "2" # Код НДС, например "2" для "без НДС"
                            }
                        ]
                }
            }, payment_id)
            payment_data = json.loads(payment.json())
            self.id = payment_data['id']
            self.link = payment.confirmation.confirmation_url # type: ignore
            return (self.link, self.id)
        except Exception as e:
            logger.warning(f'Ошибка создания платежа: {e}')

        return None