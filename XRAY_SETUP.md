# Инструкция по установке и настройке Xray Core

## 1. Удаление старой версии Xray

```bash
# Остановить Xray
sudo systemctl stop xray

# Удалить старую версию
sudo rm -f /usr/local/bin/xray
sudo rm -f /usr/local/etc/xray/config.json
sudo rm -rf /usr/local/etc/xray/*

# Удалить systemd service
sudo systemctl disable xray
sudo rm -f /etc/systemd/system/xray.service
sudo systemctl daemon-reload
```

## 2. Установка Xray Core

```bash
# Создать директорию для Xray
sudo mkdir -p /usr/local/bin
sudo mkdir -p /usr/local/etc/xray

# Скачать последнюю версию Xray
cd /tmp
wget https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip

# Распаковать
unzip Xray-linux-64.zip

# Скопировать в системную директорию
sudo cp xray /usr/local/bin/
sudo chmod +x /usr/local/bin/xray

# Проверить версию
/usr/local/bin/xray version
```

## 3. Создание базовой конфигурации Xray

Создайте файл `/usr/local/etc/xray/config.json` со следующей структурой:

```json
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none",
        "fallbacks": [
          {
            "dest": 80
          }
        ]
      },
      "streamSettings": {
        "network": "tcp",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/ssl/certs/cert.pem",
              "keyFile": "/etc/ssl/certs/key.pem"
            }
          ]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls"
        ]
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "settings": {}
    },
    {
      "protocol": "blackhole",
      "settings": {},
      "tag": "blocked"
    }
  ],
  "routing": {
    "rules": [
      {
        "type": "field",
        "ip": [
          "geoip:private"
        ],
        "outboundTag": "blocked"
      }
    ]
  }
}
```

## 4. Настройка SSL сертификатов

Если у вас нет SSL сертификатов, используйте Let's Encrypt:

```bash
# Установить certbot
sudo apt update
sudo apt install certbot -y

# Получить сертификат (замените your-domain.com на ваш домен)
sudo certbot certonly --standalone -d your-domain.com

# Создать симлинки (или скопировать файлы)
sudo mkdir -p /etc/ssl/certs
sudo ln -s /etc/letsencrypt/live/your-domain.com/fullchain.pem /etc/ssl/certs/cert.pem
sudo ln -s /etc/letsencrypt/live/your-domain.com/privkey.pem /etc/ssl/certs/key.pem
```

## 5. Создание systemd service

Создайте файл `/etc/systemd/system/xray.service`:

```ini
[Unit]
Description=Xray Service
Documentation=https://github.com/xtls
After=network.target nss-lookup.target

[Service]
User=nobody
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ExecStart=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json
Restart=on-failure
RestartPreventExitStatus=23
LimitNPROC=10000
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
```

Затем активируйте сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable xray
sudo systemctl start xray
sudo systemctl status xray
```

## 6. Проверка работы Xray

```bash
# Проверить статус
sudo systemctl status xray

# Проверить логи
sudo journalctl -u xray -f

# Проверить порты
sudo netstat -tlnp | grep xray
```

## 7. Настройка прав доступа для бота

Бот должен иметь права на чтение и запись конфигурационного файла:

```bash
# Добавить пользователя бота в группу (или использовать sudo)
sudo chown -R $USER:$USER /usr/local/etc/xray/config.json

# Или дать права на чтение/запись
sudo chmod 664 /usr/local/etc/xray/config.json

# Если бот работает от имени другого пользователя, настройте ACL
sudo setfacl -m u:bot_user:rw /usr/local/etc/xray/config.json
```

## 8. Проверка структуры конфигурации

Убедитесь, что в конфигурации Xray есть структура:
- `inbounds` - массив входящих соединений
- В каждом inbound должны быть `settings.clients` - массив клиентов

Бот автоматически добавляет клиентов в этот массив.

## Важные замечания

1. **Порты**: Убедитесь, что порты не заняты другими сервисами
2. **Firewall**: Откройте необходимые порты в firewall
3. **DNS**: Используйте DNS для домена (не IP адрес)
4. **SSL**: Обновите SSL сертификаты перед истечением срока действия

## Устранение проблем

Если Xray не запускается:

```bash
# Проверить синтаксис конфигурации
/usr/local/bin/xray -test -config /usr/local/etc/xray/config.json

# Проверить права доступа
ls -la /usr/local/etc/xray/config.json
ls -la /usr/local/bin/xray

# Проверить логи
sudo journalctl -u xray -n 50
```

Если бот не может изменить конфигурацию:

```bash
# Проверить права на файл
sudo ls -la /usr/local/etc/xray/config.json

# Дать права на запись
sudo chmod 666 /usr/local/etc/xray/config.json
# ИЛИ
sudo chown bot_user:bot_user /usr/local/etc/xray/config.json
```

