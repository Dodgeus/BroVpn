import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import json


class Database:
    def __init__(self, db_path: str = "vpn_bot.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referrer_code TEXT UNIQUE,
                used_promo_code TEXT,
                FOREIGN KEY (used_promo_code) REFERENCES users(referrer_code)
            )
        """)

        # Таблица подписок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                device_count INTEGER,
                price_paid REAL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Таблица устройств
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                device_name TEXT,
                config_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Таблица рефералов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id),
                UNIQUE(referrer_id, referred_id)
            )
        """)

        # Таблица администраторов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица заявок на подписку
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                device_count INTEGER,
                price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.commit()
        conn.close()

    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
        """Получить или создать пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            # Генерируем уникальный промокод
            referrer_code = self.generate_unique_code(user_id)
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, referrer_code)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, referrer_code))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()

        conn.close()

        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'created_at': user[3],
            'referrer_code': user[4],
            'used_promo_code': user[5]
        }

    def generate_unique_code(self, user_id: int) -> str:
        """Генерация уникального промокода"""
        # Используем комбинацию user_id и случайных символов
        import random
        import string
        code = f"REF{user_id}{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT referrer_code FROM users WHERE referrer_code = ?", (code,))
        if cursor.fetchone():
            conn.close()
            return self.generate_unique_code(user_id)  # Рекурсивно если код уже существует
        conn.close()
        return code

    def get_user_by_promo_code(self, promo_code: str) -> Optional[Dict]:
        """Получить пользователя по промокоду"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE referrer_code = ?", (promo_code,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return None

        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'created_at': user[3],
            'referrer_code': user[4],
            'used_promo_code': user[5]
        }

    def set_promo_code(self, user_id: int, promo_code: str) -> bool:
        """Установить промокод для пользователя"""
        referrer = self.get_user_by_promo_code(promo_code)
        if not referrer:
            return False
        
        if referrer['user_id'] == user_id:
            return False  # Нельзя использовать свой промокод
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET used_promo_code = ? WHERE user_id = ?", (promo_code, user_id))
        conn.commit()
        conn.close()

        # Записываем реферала
        self.add_referral(referrer['user_id'], user_id)
        return True

    def add_referral(self, referrer_id: int, referred_id: int):
        """Добавить реферала"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            """, (referrer_id, referred_id))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Уже существует
        finally:
            conn.close()

    def get_active_referrals_count(self, user_id: int) -> int:
        """Получить количество активных рефералов (с активной подпиской)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM referrals r
            JOIN subscriptions s ON r.referred_id = s.user_id
            WHERE r.referrer_id = ? AND s.is_active = 1
        """, (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_user_discount(self, user_id: int) -> float:
        """Получить скидку пользователя на основе рефералов"""
        active_referrals = self.get_active_referrals_count(user_id)
        # 15% за первого, +15% за каждого следующего, максимум 100%
        discount = min(15 + (active_referrals - 1) * 15, 100) if active_referrals > 0 else 0
        return discount / 100.0

    def get_referrer_discount(self, user_id: int) -> float:
        """Получить скидку для того, кто использует промокод другого пользователя"""
        user = self.get_or_create_user(user_id, None, None)
        # Проверяем, использует ли пользователь промокод другого пользователя
        # и есть ли у него активная подписка
        if user['used_promo_code']:
            subscription = self.get_active_subscription(user_id)
            if subscription:
                return 0.10  # 10% скидка для того, кто использует промокод и имеет активную подписку
        return 0.0

    def create_subscription(self, user_id: int, plan_type: str, device_count: int, price: float):
        """Создать подписку"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Деактивируем старые подписки
        cursor.execute("UPDATE subscriptions SET is_active = 0 WHERE user_id = ?", (user_id,))

        # Определяем длительность подписки
        days_map = {
            'month': 30,
            '3months': 90,
            '6months': 180,
            'year': 365
        }
        days = days_map.get(plan_type, 30)

        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)

        # Получаем активную подписку для продления от даты окончания
        active_sub = self.get_active_subscription(user_id)
        
        if active_sub:
            # Если есть активная подписка, продлеваем от даты окончания
            sub_end_date = datetime.fromisoformat(active_sub['end_date'])
            if sub_end_date > start_date:
                start_date = sub_end_date
            end_date = start_date + timedelta(days=days)

        cursor.execute("""
            INSERT INTO subscriptions (user_id, plan_type, start_date, end_date, device_count, price_paid, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (user_id, plan_type, start_date.isoformat(), end_date.isoformat(), device_count, price))
        conn.commit()
        conn.close()

    def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        """Получить активную подписку пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM subscriptions 
            WHERE user_id = ? AND is_active = 1
            ORDER BY end_date DESC LIMIT 1
        """, (user_id,))
        sub = cursor.fetchone()
        conn.close()

        if not sub:
            return None

        return {
            'id': sub[0],
            'user_id': sub[1],
            'plan_type': sub[2],
            'start_date': sub[3],
            'end_date': sub[4],
            'device_count': sub[5],
            'price_paid': sub[6],
            'is_active': sub[7]
        }

    def add_device(self, user_id: int, device_name: str, config_file: str):
        """Добавить устройство"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO devices (user_id, device_name, config_file)
            VALUES (?, ?, ?)
        """, (user_id, device_name, config_file))
        conn.commit()
        conn.close()

    def get_user_devices(self, user_id: int) -> List[Dict]:
        """Получить устройства пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE user_id = ?", (user_id,))
        devices = cursor.fetchall()
        conn.close()

        return [{
            'id': d[0],
            'user_id': d[1],
            'device_name': d[2],
            'config_file': d[3],
            'created_at': d[4]
        } for d in devices]

    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def add_admin(self, user_id: int):
        """Добавить администратора"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO admins (user_id) VALUES (?)", (user_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Уже существует
        finally:
            conn.close()

    def get_all_admins(self) -> List[int]:
        """Получить список всех администраторов"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins")
        admins = [row[0] for row in cursor.fetchall()]
        conn.close()
        return admins

    def create_pending_subscription(self, user_id: int, plan_type: str, device_count: int, price: float) -> int:
        """Создать заявку на подписку"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pending_subscriptions (user_id, plan_type, device_count, price)
            VALUES (?, ?, ?, ?)
        """, (user_id, plan_type, device_count, price))
        conn.commit()
        request_id = cursor.lastrowid
        conn.close()
        return request_id

    def get_pending_subscription(self, request_id: int) -> Optional[Dict]:
        """Получить заявку на подписку"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_subscriptions WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        conn.close()

        if not req:
            return None

        return {
            'id': req[0],
            'user_id': req[1],
            'plan_type': req[2],
            'device_count': req[3],
            'price': req[4],
            'created_at': req[5],
            'status': req[6]
        }

    def update_pending_subscription_status(self, request_id: int, status: str):
        """Обновить статус заявки"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pending_subscriptions SET status = ? WHERE id = ?
        """, (status, request_id))
        conn.commit()
        conn.close()

    def delete_device(self, device_id: int):
        """Удалить устройство по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
        conn.close()

    def delete_all_user_devices(self, user_id: int):
        """Удалить все устройства пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

