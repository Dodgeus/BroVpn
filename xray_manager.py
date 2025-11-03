import os
import json
import subprocess
import logging
import uuid
import base64
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class XrayManager:
    """Класс для управления Xray Core конфигурациями"""
    
    def __init__(self, 
                 xray_config_path: str = "/usr/local/etc/xray/config.json",
                 xray_bin_path: str = "/usr/local/bin/xray"):
        """
        Args:
            xray_config_path: Путь к конфигурационному файлу Xray
            xray_bin_path: Путь к исполняемому файлу Xray
        """
        self.xray_config_path = xray_config_path
        self.xray_bin_path = xray_bin_path
        
        # Настройки по умолчанию
        self.xray_interface = "panel"
        self.xray_tag = "api"
        
    def reload_xray(self) -> bool:
        """Перезагрузить конфигурацию Xray"""
        try:
            result = subprocess.run(
                ["systemctl", "reload", "xray"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info("Xray перезагружен успешно")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка перезагрузки Xray: {e}")
            # Пробуем альтернативный метод
            try:
                result = subprocess.run(
                    ["killall", "-HUP", "xray"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info("Xray перезагружен через killall")
                return True
            except subprocess.CalledProcessError as e2:
                logger.error(f"Ошибка перезагрузки Xray через killall: {e2}")
                return False
    
    def add_user(self, email: str, uuid: str, encryption: str = "auto") -> Dict:
        """
        Добавить пользователя в Xray через API
        
        Args:
            email: Email пользователя (обычно используется user_id для идентификации)
            uuid: UUID клиента
            encryption: Метод шифрования (auto, aes-128-gcm, aes-256-gcm и т.д.)
        
        Returns:
            Словарь с результатом операции
        """
        try:
            # Используем Xray API для добавления пользователя
            # Структура команды зависит от вашей настройки Xray
            command = [
                self.xray_bin_path,
                "-c", self.xray_config_path
            ]
            
            # Читаем текущую конфигурацию
            with open(self.xray_config_path, 'r') as f:
                config = json.load(f)
            
            # Добавляем нового пользователя
            if 'inbounds' not in config:
                logger.error("Структура конфигурации Xray неверна")
                return {'success': False, 'error': 'Invalid config structure'}
            
            # Ищем inbound с клиентами
            for inbound in config['inbounds']:
                if 'settings' in inbound and 'clients' in inbound['settings']:
                    # Проверяем, нет ли уже такого пользователя
                    existing_users = [c.get('email') for c in inbound['settings']['clients']]
                    if email in existing_users:
                        logger.warning(f"Пользователь {email} уже существует")
                        return {'success': False, 'error': 'User already exists'}
                    
                    # Добавляем нового клиента
                    new_client = {
                        "id": uuid,
                        "email": email,
                        "flow": "",
                        "encryption": encryption
                    }
                    inbound['settings']['clients'].append(new_client)
                    break
            
            # Сохраняем обновленную конфигурацию
            with open(self.xray_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Перезагружаем Xray
            if self.reload_xray():
                logger.info(f"Пользователь {email} успешно добавлен")
                return {'success': True, 'email': email, 'uuid': uuid}
            else:
                logger.error("Не удалось перезагрузить Xray")
                return {'success': False, 'error': 'Failed to reload Xray'}
                
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return {'success': False, 'error': str(e)}
    
    def remove_user(self, email: str) -> bool:
        """
        Удалить пользователя из Xray
        
        Args:
            email: Email пользователя для удаления
        
        Returns:
            True если успешно, False если ошибка
        """
        try:
            # Читаем текущую конфигурацию
            with open(self.xray_config_path, 'r') as f:
                config = json.load(f)
            
            # Удаляем пользователя
            if 'inbounds' not in config:
                logger.error("Структура конфигурации Xray неверна")
                return False
            
            user_removed = False
            for inbound in config['inbounds']:
                if 'settings' in inbound and 'clients' in inbound['settings']:
                    clients = inbound['settings']['clients']
                    # Удаляем пользователя по email
                    inbound['settings']['clients'] = [
                        c for c in clients if c.get('email') != email
                    ]
                    if len(inbound['settings']['clients']) < len(clients):
                        user_removed = True
                        break
            
            if not user_removed:
                logger.warning(f"Пользователь {email} не найден")
                return False
            
            # Сохраняем обновленную конфигурацию
            with open(self.xray_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Перезагружаем Xray
            if self.reload_xray():
                logger.info(f"Пользователь {email} успешно удален")
                return True
            else:
                logger.error("Не удалось перезагрузить Xray")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя: {e}")
            return False
    
    def generate_vless_config(self, 
                             uuid: str, 
                             server_address: str, 
                             port: int,
                             encryption: str = "auto",
                             flow: str = "",
                             device_name: str = "Device") -> str:
        """
        Генерация VLESS конфигурации для клиента
        
        Args:
            uuid: UUID клиента
            server_address: Адрес сервера
            port: Порт сервера
            encryption: Метод шифрования
            flow: Flow параметр (для xtls-rprx-vision)
            device_name: Название устройства
        
        Returns:
            VLESS ссылка для импорта в клиент
        """
        if flow:
            config = f"vless://{uuid}@{server_address}:{port}?encryption={encryption}&flow={flow}&security=tls&sni={server_address}&fp=chrome&pbk=&sid=&spx=&type=tcp&headerType=none#XRay_{device_name}"
        else:
            config = f"vless://{uuid}@{server_address}:{port}?encryption={encryption}&security=tls&sni={server_address}&fp=chrome&pbk=&sid=&spx=&type=tcp&headerType=none#XRay_{device_name}"
        
        return config
    
    def generate_vmess_config(self,
                             uuid: str,
                             server_address: str,
                             port: int,
                             alter_id: int = 0,
                             device_name: str = "Device") -> str:
        """
        Генерация VMESS конфигурации для клиента
        
        Args:
            uuid: UUID клиента
            server_address: Адрес сервера
            port: Порт сервера
            alter_id: Alter ID
            device_name: Название устройства
        
        Returns:
            VMESS ссылка для импорта в клиент
        """
        vmess_config = {
            "v": "2",
            "ps": f"XRay_{device_name}",
            "add": server_address,
            "port": port,
            "id": uuid,
            "aid": alter_id,
            "scy": "auto",
            "net": "tcp",
            "type": "none",
            "host": "",
            "path": "",
            "tls": "tls",
            "sni": server_address,
            "alpn": "",
            "fp": "chrome"
        }
        
        # Кодируем в base64
        json_str = json.dumps(vmess_config)
        config_base64 = base64.b64encode(json_str.encode()).decode()
        return f"vmess://{config_base64}"
    
    def generate_trojan_config(self,
                              password: str,
                              server_address: str,
                              port: int,
                              device_name: str = "Device") -> str:
        """
        Генерация Trojan конфигурации для клиента
        
        Args:
            password: Пароль клиента
            server_address: Адрес сервера
            port: Порт сервера
            device_name: Название устройства
        
        Returns:
            Trojan ссылка для импорта в клиент
        """
        config = f"trojan://{password}@{server_address}:{port}?sni={server_address}&allowInsecure=0&fp=chrome&type=tcp&headerType=none#XRay_{device_name}"
        return config
    
    def generate_shadowsocks_config(self,
                                   password: str,
                                   method: str,
                                   server_address: str,
                                   port: int,
                                   device_name: str = "Device") -> str:
        """
        Генерация Shadowsocks конфигурации для клиента
        
        Args:
            password: Пароль клиента
            method: Метод шифрования
            server_address: Адрес сервера
            port: Порт сервера
            device_name: Название устройства
        
        Returns:
            Shadowsocks ссылка для импорта в клиент
        """
        # Кодируем ss:// метод:пароль@адрес:порт
        ss_string = f"{method}:{password}@{server_address}:{port}"
        ss_base64 = base64.b64encode(ss_string.encode()).decode()
        config = f"ss://{ss_base64}#XRay_{device_name}"
        return config


class XrayConfigGenerator:
    """Класс для генерации конфигураций Xray на основе настроек"""
    
    def __init__(self, xray_manager: XrayManager):
        self.xray_manager = xray_manager
        
        # Настройки сервера из переменных окружения
        self.server_address = os.getenv('XRAY_SERVER_ADDRESS', 'your-server.com')
        self.server_port_vless = int(os.getenv('XRAY_PORT_VLESS', '443'))
        self.server_port_vmess = int(os.getenv('XRAY_PORT_VMESS', '8443'))
        self.server_port_trojan = int(os.getenv('XRAY_PORT_TROJAN', '8444'))
        self.server_port_ss = int(os.getenv('XRAY_PORT_SS', '8445'))
        self.protocol = os.getenv('XRAY_PROTOCOL', 'vless')  # vless, vmess, trojan, ss
    
    def generate_config_for_device(self, user_id: int, device_name: str) -> Optional[str]:
        """
        Генерирует полную конфигурацию для устройства
        
        Args:
            user_id: ID пользователя
            device_name: Название устройства
        
        Returns:
            Строка с конфигурацией или None при ошибке
        """
        try:
            # Генерируем уникальные идентификаторы для устройства
            device_uuid = str(uuid.uuid4())
            email = f"{user_id}_{device_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Добавляем пользователя в Xray
            result = self.xray_manager.add_user(email, device_uuid)
            
            if not result.get('success'):
                logger.error(f"Не удалось добавить пользователя: {result.get('error')}")
                return None
            
            # Генерируем конфигурацию в зависимости от протокола
            if self.protocol == 'vless':
                config = self.xray_manager.generate_vless_config(
                    uuid=device_uuid,
                    server_address=self.server_address,
                    port=self.server_port_vless,
                    encryption="auto",
                    flow="xtls-rprx-vision",
                    device_name=device_name
                )
            elif self.protocol == 'vmess':
                config = self.xray_manager.generate_vmess_config(
                    uuid=device_uuid,
                    server_address=self.server_address,
                    port=self.server_port_vmess,
                    device_name=device_name
                )
            elif self.protocol == 'trojan':
                config = self.xray_manager.generate_trojan_config(
                    password=device_uuid,
                    server_address=self.server_address,
                    port=self.server_port_trojan,
                    device_name=device_name
                )
            elif self.protocol == 'ss':
                config = self.xray_manager.generate_shadowsocks_config(
                    password=device_uuid,
                    method="aes-256-gcm",
                    server_address=self.server_address,
                    port=self.server_port_ss,
                    device_name=device_name
                )
            else:
                logger.error(f"Неизвестный протокол: {self.protocol}")
                return None
            
            # Сохраняем информацию о конфигурации
            config_data = {
                'email': email,
                'uuid': device_uuid,
                'protocol': self.protocol,
                'created_at': datetime.now().isoformat(),
                'server_address': self.server_address,
                'port': self.server_port_vless if self.protocol == 'vless' else 
                        self.server_port_vmess if self.protocol == 'vmess' else
                        self.server_port_trojan if self.protocol == 'trojan' else
                        self.server_port_ss
            }
            
            return json.dumps(config_data)
            
        except Exception as e:
            logger.error(f"Ошибка генерации конфигурации: {e}")
            return None
    
    def delete_config_for_device(self, email: str) -> bool:
        """
        Удаляет конфигурацию устройства из Xray
        
        Args:
            email: Email устройства для удаления
        
        Returns:
            True если успешно, False если ошибка
        """
        return self.xray_manager.remove_user(email)

