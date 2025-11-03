import os
import json
from typing import Optional
from datetime import datetime
from xray_manager import XrayConfigGenerator, XrayManager


class ConfigGenerator:
    """Класс для генерации конфигурационных файлов VPN"""
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = config_dir
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # Инициализация Xray менеджера
        xray_config_path = os.getenv('XRAY_CONFIG_PATH', '/usr/local/etc/xray/config.json')
        xray_bin_path = os.getenv('XRAY_BIN_PATH', '/usr/local/bin/xray')
        
        self.xray_manager = XrayManager(xray_config_path, xray_bin_path)
        self.xray_config = XrayConfigGenerator(self.xray_manager)
    
    def generate_config(self, user_id: int, device_name: str) -> Optional[str]:
        """Генерация конфигурационного файла для устройства
        
        Returns:
            JSON строка с конфигурацией или None
        """
        try:
            # Генерируем конфигурацию через Xray
            config_json = self.xray_config.generate_config_for_device(user_id, device_name)
            
            if not config_json:
                return None
            
            # Сохраняем в файл для истории
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{user_id}_{device_name}_{timestamp}.json"
            filepath = os.path.join(self.config_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(config_json)
            
            return config_json
            
        except Exception as e:
            print(f"Error generating config: {e}")
            return None
    
    def get_config_file(self, config_json: str) -> Optional[str]:
        """Получить конфигурацию в виде строки для отправки
        
        Args:
            config_json: JSON строка с конфигурацией
        
        Returns:
            Строка конфигурации для импорта
        """
        try:
            if not config_json:
                return None
            
            config_data = json.loads(config_json)
            
            # Генерируем ссылку для импорта в зависимости от протокола
            if config_data['protocol'] == 'vless':
                config = self.xray_manager.generate_vless_config(
                    uuid=config_data['uuid'],
                    server_address=config_data['server_address'],
                    port=config_data['port'],
                    encryption="auto",
                    flow="xtls-rprx-vision",
                    device_name="Device"
                )
            elif config_data['protocol'] == 'vmess':
                config = self.xray_manager.generate_vmess_config(
                    uuid=config_data['uuid'],
                    server_address=config_data['server_address'],
                    port=config_data['port'],
                    device_name="Device"
                )
            elif config_data['protocol'] == 'trojan':
                config = self.xray_manager.generate_trojan_config(
                    password=config_data['uuid'],
                    server_address=config_data['server_address'],
                    port=config_data['port'],
                    device_name="Device"
                )
            elif config_data['protocol'] == 'ss':
                config = self.xray_manager.generate_shadowsocks_config(
                    password=config_data['uuid'],
                    method="aes-256-gcm",
                    server_address=config_data['server_address'],
                    port=config_data['port'],
                    device_name="Device"
                )
            else:
                return None
            
            return config
            
        except Exception as e:
            print(f"Error reading config: {e}")
            return None
    
    def delete_config(self, email: str) -> bool:
        """Удалить конфигурацию устройства"""
        return self.xray_config.delete_config_for_device(email)

