# backend_context.py
import aiohttp
import asyncio
from config_data.config import settings as s
from logger_setup import logger
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json

MARZ_DATA = (s.M_DIGITAL_U, s.M_DIGITAL_P, s.M_DIGITAL_URL)


class MarzbanClient:
    """Клиент с синглтоном ПО URL"""
    
    _instances = {}  # Словарь: {url: instance}
    
    def __new__(cls, url: str):
        # Создаём отдельный инстанс для каждого URL
        if url not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[url] = instance
        return cls._instances[url]
    
    def __init__(self, url: str):
        if self._initialized:
            return
        
        self.user = s.M_DIGITAL_U
        self.password = s.M_DIGITAL_P
        self.base_url = url
        self.headers = {"accept": "application/json"}
        self._token = None
        self._token_expires_at = None
        self._session = None
        self._initialized = True
        logger.info(f"MarzbanClient создан для: {self.base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def _ensure_token(self):
        """Проверить и обновить токен при необходимости"""
        # Если токен валиден - ничего не делаем
        # if self._token and self._token_expires_at and datetime.now() < self._token_expires_at:
        #     return
        
        # Получаем новый токен
        try:
            session = await self._get_session()
            
            data = {
                "username": self.user,
                "password": self.password
            }
            url = f"{self.base_url}/api/admin/token"
            logger.debug(f'Это url {url}')

            async with session.post(
                url=url,
                data=data
            ) as response:
                if response.status == 200:
                    json_data = await response.json()
                    self._token = json_data.get("access_token")
                    self.headers["Authorization"] = f"Bearer {self._token}"
                    # Токен действителен 30 дней
                    self._token_expires_at = datetime.now() + timedelta(days=29)
                    logger.debug(f"Токен получен: {self._token[:10]}...")
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка авторизации: {response.status}, {error_text}")
                    raise Exception(f"Auth failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Ошибка при получении токена: {e}")
            raise
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе"""
        try:
            await self._ensure_token()
            session = await self._get_session()
            
            async with session.get(
                url=f"{self.base_url}/api/user/{user_id}",
                headers=self.headers
            ) as response:
                if response.status in (200, 201):
                    json_data = await response.json()
                    logger.debug(f"Пользователь {user_id} получен в функции get_user")
                    return json_data
                else:
                    logger.warning(f"Ошибка в получении пользователя {user_id}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при получении пользователя {user_id}: {e}")
            return None
    
    async def modify_user(self, user_id: str, expire: int):
        """Изменить данные пользователя"""
        try:
            await self._ensure_token()
            session = await self._get_session()
            
            data = {"expire": expire}
            
            async with session.put(
                url=f"{self.base_url}/api/user/{user_id}",
                headers=self.headers,
                json=data
            ) as response:
                
                if response.status in (200, 201):
                    json_data = await response.json()
                    logger.debug(f"Пользователь {user_id} изменён")
                    return json_data
                else:
                    logger.warning(f"Ошибка в редактировании пользователя {user_id}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при редактировании пользователя {user_id}: {e}")
            return None
    
    async def create_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Создать нового пользователя"""
        try:
            await self._ensure_token()
            session = await self._get_session()
            
            username = str(username)
            
            data = {
                "username": username,
                "proxies": {
                    "vless": {
                        "flow": "xtls-rprx-vision"
                    }
                },
                "inbounds": {
                    "vless": ["VLESS TCP VISION REALITY", "NODE1_REALITY"]
                }
            }
            
            async with session.post(
                url=f"{self.base_url}/api/user",
                headers=self.headers,
                json=data
            ) as response:
                if response.status in (200, 201):
                    json_data = await response.json()
                    json_str = json.dumps(json_data)

                    logger.debug(f"Пользователь {username} создан: {json_str[:25]}")
                    return json_data
                else:
                    error_text = await response.text()
                    logger.warning(f"Ошибка в создании пользователя: {response.status}, {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при создании пользователя {username}: {e}")
            return None
    
    async def create_user_options(self, username: str, id: str | None = None, inbounds: list | None = None, expire: int | None = None) -> Optional[Dict[str, Any]]:
        """Создать нового пользователя"""
        try:
            await self._ensure_token()
            session = await self._get_session()
            
            username = str(username)

            data = {
                "username": username,
                "proxies": {
                    "vless": {
                        "flow": "xtls-rprx-vision"
                    }
                },
                "inbounds": {
                    "vless": []
                }
            }

            if id:
                data["proxies"]['vless']['id'] = id
            
            if inbounds:
                data["inbounds"]['vless'].extend(inbounds)
            
            if expire:
                data['expire'] = expire
            
            async with session.post(
                url=f"{self.base_url}/api/user",
                headers=self.headers,
                json=data
            ) as response:
                
                if response.status in (200, 201):
                    json_data = await response.json()
                    json_str = json.dumps(json_data)

                    logger.debug(f"Пользователь {username} создан: {json_str[:25]}")
                    return json_data
                else:
                    error_text = await response.text()
                    logger.warning(f"Ошибка в создании пользователя: {response.status}, {error_text}")
                    return {"status": 409}
                    
        except Exception as e:
            logger.error(f"Исключение при создании пользователя {username}: {e}")
            return None

    async def delete_user(self, username: str) -> bool:
        """Удалить пользователя"""
        try:
            await self._ensure_token()
            session = await self._get_session()
            
            async with session.delete(
                url=f"{self.base_url}/api/user/{username}",
                headers=self.headers
            ) as response:
                
                if response.status in (200, 204):
                    logger.debug(f"Пользователь {username} удалён")
                    return True
                else:
                    logger.warning(f"Ошибка при удалении пользователя {username}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Исключение при удалении пользователя {username}: {e}")
            return False
    
    async def close(self):
        """Закрыть сессию (вызывать при завершении приложения)"""
        if self._session and not self._session.closed:
            await self._session.close()
            await asyncio.sleep(0.1)
            logger.info("Сессия MarzbanClient закрыта")


# Singleton instance
marzban_client = MarzbanClient(s.M_DIGITAL_URL)