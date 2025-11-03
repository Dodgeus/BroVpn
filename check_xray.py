#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации Xray и настройки бота
"""

import os
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def check_xray_installation():
    """Проверить установку Xray"""
    print("=" * 60)
    print("Проверка установки Xray Core")
    print("=" * 60)
    
    xray_bin = os.getenv('XRAY_BIN_PATH', '/usr/local/bin/xray')
    
    if Path(xray_bin).exists():
        print(f"✅ Xray найден: {xray_bin}")
        try:
            result = subprocess.run([xray_bin, 'version'], capture_output=True, text=True)
            print(f"   Версия: {result.stdout.strip()}")
        except Exception as e:
            print(f"   ⚠️ Не удалось получить версию: {e}")
    else:
        print(f"❌ Xray не найден: {xray_bin}")
        print(f"   Установите Xray согласно инструкции в XRAY_SETUP.md")
        return False
    
    return True

def check_xray_config():
    """Проверить конфигурацию Xray"""
    print("\n" + "=" * 60)
    print("Проверка конфигурации Xray")
    print("=" * 60)
    
    xray_config = os.getenv('XRAY_CONFIG_PATH', '/usr/local/etc/xray/config.json')
    
    if not Path(xray_config).exists():
        print(f"❌ Файл конфигурации не найден: {xray_config}")
        print(f"   Создайте конфигурацию согласно инструкции в XRAY_SETUP.md")
        return False
    
    print(f"✅ Файл конфигурации найден: {xray_config}")
    
    # Проверяем права доступа
    stat = os.stat(xray_config)
    print(f"   Права: {oct(stat.st_mode)[-3:]}")
    print(f"   Владелец: {stat.st_uid}")
    
    # Проверяем структуру конфигурации
    try:
        with open(xray_config, 'r') as f:
            config = json.load(f)
        
        if 'inbounds' not in config:
            print("❌ Структура конфигурации неверна: отсутствует 'inbounds'")
            return False
        
        print(f"✅ Найдено inbounds: {len(config['inbounds'])}")
        
        # Проверяем наличие clients в первом inbound
        for i, inbound in enumerate(config['inbounds']):
            if 'settings' in inbound and 'clients' in inbound['settings']:
                clients_count = len(inbound['settings']['clients'])
                print(f"   Inbound {i}: порт {inbound.get('port', 'N/A')}, протокол {inbound.get('protocol', 'N/A')}")
                print(f"   Текущих клиентов: {clients_count}")
                return True
            else:
                print(f"   ⚠️ Inbound {i} не имеет settings.clients")
        
        print("❌ Не найдено ни одного inbound с settings.clients")
        print("   Убедитесь, что структура конфигурации правильная")
        return False
        
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка чтения конфигурации: {e}")
        return False

def check_xray_service():
    """Проверить статус сервиса Xray"""
    print("\n" + "=" * 60)
    print("Проверка сервиса Xray")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'xray'],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip() == 'active':
            print("✅ Сервис Xray активен")
        else:
            print(f"⚠️ Сервис Xray не активен: {result.stdout.strip()}")
            print("   Запустите: sudo systemctl start xray")
            
        # Проверяем статус
        result = subprocess.run(
            ['systemctl', 'status', 'xray', '--no-pager'],
            capture_output=True,
            text=True
        )
        print("\nСтатус сервиса:")
        print(result.stdout[:500])  # Первые 500 символов
        
        return True
        
    except FileNotFoundError:
        print("⚠️ systemctl не найден (возможно, не Linux система)")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки сервиса: {e}")
        return False

def check_env_config():
    """Проверить настройки в .env"""
    print("\n" + "=" * 60)
    print("Проверка настроек .env")
    print("=" * 60)
    
    required_vars = [
        'BOT_TOKEN',
        'XRAY_CONFIG_PATH',
        'XRAY_BIN_PATH',
        'XRAY_SERVER_ADDRESS',
        'XRAY_PROTOCOL'
    ]
    
    all_ok = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Скрываем токен
            if 'TOKEN' in var:
                display_value = value[:10] + '...' if len(value) > 10 else '***'
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: не установлен")
            all_ok = False
    
    # Проверяем опциональные переменные
    optional_vars = ['INITIAL_ADMIN_ID', 'XRAY_PORT_VLESS', 'XRAY_PORT_VMESS']
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚠️ {var}: не установлен (опционально)")
    
    return all_ok

def check_permissions():
    """Проверить права доступа"""
    print("\n" + "=" * 60)
    print("Проверка прав доступа")
    print("=" * 60)
    
    xray_config = os.getenv('XRAY_CONFIG_PATH', '/usr/local/etc/xray/config.json')
    
    if not Path(xray_config).exists():
        print("⚠️ Файл конфигурации не существует, пропускаем проверку прав")
        return True
    
    # Проверяем права на чтение
    if os.access(xray_config, os.R_OK):
        print("✅ Права на чтение: есть")
    else:
        print("❌ Права на чтение: нет")
        print("   Дайте права: sudo chmod 644 " + xray_config)
        return False
    
    # Проверяем права на запись
    if os.access(xray_config, os.W_OK):
        print("✅ Права на запись: есть")
    else:
        print("❌ Права на запись: нет")
        print("   Дайте права: sudo chmod 666 " + xray_config)
        print("   ИЛИ: sudo chown $USER:$USER " + xray_config)
        return False
    
    return True

def main():
    """Основная функция"""
    print("\n" + "=" * 60)
    print("Проверка конфигурации Xray и бота")
    print("=" * 60 + "\n")
    
    checks = [
        ("Переменные окружения", check_env_config),
        ("Установка Xray", check_xray_installation),
        ("Конфигурация Xray", check_xray_config),
        ("Сервис Xray", check_xray_service),
        ("Права доступа", check_permissions),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Ошибка при проверке {name}: {e}")
            results.append((name, False))
    
    # Итоговая сводка
    print("\n" + "=" * 60)
    print("Итоговая сводка")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ OK" if result else "❌ ОШИБКА"
        print(f"{status} - {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ Все проверки пройдены! Бот готов к работе.")
    else:
        print("\n❌ Некоторые проверки не пройдены. Исправьте ошибки и запустите проверку снова.")
        print("\n📖 Подробная инструкция: см. XRAY_SETUP.md")

if __name__ == '__main__':
    main()

