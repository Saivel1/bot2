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
    

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        max_attempts = 5
        delay = 0.5
        
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.request(
                        method,
                        f"{self.base_url}{endpoint}",
                        **kwargs
                    ) as response:
                        # Успех
                        if response.status in (200, 201, 204):
                            if method == "DELETE":
                                return {"success": True}
                            return await response.json()
                        
                        # 404 от Xray fallback - retry!
                        elif response.status == 404 and attempt < max_attempts - 1:
                            body = await response.text()
                            # Проверяем, это fallback или реальный 404
                            if 'kittenx' in body or 'Not Found' in body:
                                logger.warning(f"Xray fallback, retry {attempt + 1}/{max_attempts}")
                                await asyncio.sleep(delay * (attempt + 1))
                                continue
                            else:
                                return None
                        
                        # Серверные ошибки - retry
                        elif 500 <= response.status < 600 and attempt < max_attempts - 1:
                            logger.warning(f"Retry {attempt + 1}/{max_attempts}: {response.status}")
                            await asyncio.sleep(delay * (attempt + 1))
                            continue
                        
                        else:
                            logger.warning(f"Ошибка {response.status}")
                            return None
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_attempts - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_attempts}: {e}")
                    await asyncio.sleep(delay * (attempt + 1))
                else:
                    logger.error(f"Все попытки исчерпаны: {e}")
                    return None
        
        return None
    
    async def _get_token(self) -> str:
        """Получить токен с retry"""
        max_attempts = 5
        delay = 0.5
        
        data = {
            "username": self.user,
            "password": self.password
        }
        
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(
                        url=f"{self.base_url}/api/admin/token",
                        data=data
                    ) as response:
                        if response.status == 200:
                            json_data = await response.json()
                            return json_data["access_token"]
                        elif attempt < max_attempts - 1:
                            logger.warning(f"Token retry {attempt + 1}: статус {response.status}")
                            await asyncio.sleep(delay * (attempt + 1))
                            continue
                        else:
                            raise Exception(f"Failed to get token: {response.status}")
            
            except aiohttp.ClientError as e:
                if attempt < max_attempts - 1:
                    logger.warning(f"Token retry {attempt + 1}: {e}")
                    await asyncio.sleep(delay * (attempt + 1))
                else:
                    logger.error(f"Не удалось получить токен после {max_attempts} попыток")
                    raise
        
        raise Exception("Failed to get token")
    

    
    # @retry_on_failure(max_attempts=3, delay=2)
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        token = await self._get_token()
        headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}"
        }
        return await self._make_request(method="GET", endpoint=f"/api/user/{user_id}", headers=headers)

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
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.put(
                    url=f"{self.base_url}/api/user/{user_id}",
                    headers=headers,
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