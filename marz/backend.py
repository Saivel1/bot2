# backend_context.py
import aiohttp
import asyncio
from config_data.config import settings as s
from logger_setup import logger
from typing import Optional, Dict, Any
import json
from functools import wraps
import ssl

def retry_on_failure(max_attempts=3, delay=1):
    """Декоратор для retry"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Retry {attempt + 1}/{max_attempts}: {e}")
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logger.error(f"Все попытки исчерпаны: {e}")
                        raise
            return None
        return wrapper
    return decorator



class MarzbanClient:
    """Клиент с синглтоном ПО URL"""
    
    def __init__(self, url: str):
        self.user = s.M_DIGITAL_U
        self.password = s.M_DIGITAL_P
        self.base_url = url
        self.timeout = aiohttp.ClientTimeout(total=30)
    
    
    async def _get_token(self) -> str:
        """Получить токен (каждый раз новый)"""
        data = {
            "username": self.user,
            "password": self.password
        }
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(timeout=self.timeout, connector=connector) as session:
            async with session.post(
                url=f"{self.base_url}/api/admin/token",
                data=data
            ) as response:
                response.raise_for_status()
                json_data = await response.json()
                return json_data["access_token"]
    

    
    @retry_on_failure(max_attempts=3, delay=2)
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе"""
    
        try:
            token = await self._get_token()
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
            }

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    url=f"{self.base_url}/api/user/{user_id}",
                    headers=headers,
                    ssl=False
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
    
    @retry_on_failure(max_attempts=3, delay=2)
    async def modify_user(self, user_id: str, expire: int):
        """Изменить данные пользователя"""
        try:
            token = await self._get_token()
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
            }

            connector = aiohttp.TCPConnector(ssl=False)
            
            data = {"expire": expire}
            
            async with aiohttp.ClientSession(timeout=self.timeout, connector=connector) as session:
                async with session.put(
                    url=f"{self.base_url}/api/user/{user_id}",
                    headers=headers,
                    json=data,
                    ssl=False
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
    

    @retry_on_failure(max_attempts=3, delay=2)
    async def create_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Создать нового пользователя"""
        try:
            token = await self._get_token()
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
            }
            

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
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    url=f"{self.base_url}/api/user",
                    headers=headers,
                    json=data, 
                    ssl=False
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
    
    @retry_on_failure(max_attempts=3, delay=2)
    async def create_user_options(self, username: str, id: str | None = None, inbounds: list | None = None, expire: int | None = None) -> Optional[Dict[str, Any]]:
        """Создать нового пользователя"""
        try:
            token = await self._get_token()
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
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
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    url=f"{self.base_url}/api/user",
                    headers=headers,
                    json=data,
                    ssl=False
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


    @retry_on_failure(max_attempts=3, delay=2)
    async def delete_user(self, username: str) -> bool:
        """Удалить пользователя"""
        try:
            token = await self._get_token()
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.delete(
                    url=f"{self.base_url}/api/user/{username}",
                    headers=headers,
                    ssl=False
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