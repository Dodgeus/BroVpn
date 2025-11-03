import os
import logging
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from database import Database
from pricing import Pricing
from config_generator import ConfigGenerator

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация
db = Database()
pricing = Pricing()
config_gen = ConfigGenerator()

# Состояния для FSM
class States:
    WAITING_PLAN = "waiting_plan"
    WAITING_DEVICES = "waiting_devices"
    WAITING_PROMO = "waiting_promo"
    WAITING_DEVICE_NAME = "waiting_device_name"


def get_back_button():
    """Получить кнопку 'Назад'"""
    return InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    
    # Проверяем и добавляем начального администратора
    initial_admin_id = os.getenv('INITIAL_ADMIN_ID')
    if initial_admin_id:
        try:
            admin_id = int(initial_admin_id)
            db.add_admin(admin_id)
            logger.info(f"Добавлен начальный администратор: {admin_id}")
        except ValueError:
            logger.error(f"Неверный формат INITIAL_ADMIN_ID: {initial_admin_id}")
    
    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню"""
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    subscription = db.get_active_subscription(user_id)
    
    # Формируем сообщение
    message = "🔐 *VPN Подписка*\n\n"
    
    if subscription:
        end_date = datetime.fromisoformat(subscription['end_date'])
        days_left = (end_date - datetime.now()).days
        message += f"📅 *Подписка активна до:* {end_date.strftime('%d.%m.%Y')}\n"
        message += f"⏰ *Осталось дней:* {days_left}\n"
        message += f"📱 *Устройств:* {subscription['device_count']}\n"
    else:
        message += "❌ *Подписка не активна*\n"
    
    if user_data['referrer_code']:
        message += f"\n🎁 *Ваш промокод:* `{user_data['referrer_code']}`\n"
        message += "Поделитесь им с друзьями и получайте скидки!\n"
    
    # Inline кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("📋 Оформить/Продлить подписку", callback_data="start_subscription")],
        [InlineKeyboardButton("📥 Скачать конфигурацию", callback_data="download_configs")],
        [InlineKeyboardButton("🎫 Ввести/Изменить промокод", callback_data="enter_promo")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    # Проверяем состояние FSM
    user_state = context.user_data.get('state')
    
    if user_state == States.WAITING_DEVICES:
        await handle_device_count(update, context)
    elif user_state == States.WAITING_PROMO:
        # Проверяем, идет ли оформление подписки или просто изменение промокода
        if 'plan_type' in context.user_data:
            # Оформление подписки
            await handle_promo_code(update, context)
        else:
            # Изменение промокода из меню
            await handle_promo_code_change(update, context)
    elif user_state == States.WAITING_DEVICE_NAME:
        await handle_device_name(update, context)
    else:
        # Если нет состояния, показываем главное меню
        await show_main_menu(update, context)


async def start_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать процесс оформления подписки"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("📅 Месяц - 120₽", callback_data="plan_month"),
            InlineKeyboardButton("📅 3 месяца - 300₽", callback_data="plan_3months")
        ],
        [
            InlineKeyboardButton("📅 6 месяцев - 550₽", callback_data="plan_6months"),
            InlineKeyboardButton("📅 Год - 1000₽", callback_data="plan_year")
        ],
        [get_back_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите тарифный план:",
        reply_markup=reply_markup
    )


async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора тарифа"""
    query = update.callback_query
    await query.answer()
    
    plan_type = query.data.replace("plan_", "")
    context.user_data['plan_type'] = plan_type
    
    keyboard = [[get_back_button()]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Введите количество устройств (от 1 до 10):",
        reply_markup=reply_markup
    )
    context.user_data['state'] = States.WAITING_DEVICES


async def handle_device_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода количества устройств"""
    try:
        device_count = int(update.message.text)
        if device_count < 1 or device_count > 10:
            keyboard = [[get_back_button()]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Количество устройств должно быть от 1 до 10. Попробуйте снова:",
                reply_markup=reply_markup
            )
            return
        
        context.user_data['device_count'] = device_count
        
        # Спрашиваем промокод
        keyboard = [
            [InlineKeyboardButton("Пропустить", callback_data="skip_promo")],
            [get_back_button()]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Введите промокод (если есть) или нажмите 'Пропустить':",
            reply_markup=reply_markup
        )
        context.user_data['state'] = States.WAITING_PROMO
        
    except ValueError:
        keyboard = [[get_back_button()]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Пожалуйста, введите число от 1 до 10:",
            reply_markup=reply_markup
        )


async def handle_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода промокода при оформлении подписки"""
    promo_code = update.message.text.upper().strip()
    user_id = update.effective_user.id
    
    # Проверяем промокод
    if db.get_user_by_promo_code(promo_code):
        if db.set_promo_code(user_id, promo_code):
            await update.message.reply_text(f"✅ Промокод {promo_code} применен!")
        else:
            await update.message.reply_text("❌ Нельзя использовать свой промокод.")
    else:
        await update.message.reply_text("❌ Промокод не найден. Продолжаем без промокода.")
    
    context.user_data['state'] = None
    await show_subscription_summary(update, context)


async def handle_promo_code_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изменения промокода из меню"""
    promo_code = update.message.text.upper().strip()
    user_id = update.effective_user.id
    
    # Проверяем промокод
    if db.get_user_by_promo_code(promo_code):
        if db.set_promo_code(user_id, promo_code):
            await update.message.reply_text(
                f"✅ Промокод {promo_code} применен!\n\n"
                "Скидка будет применена при следующем оформлении или продлении подписки."
            )
        else:
            await update.message.reply_text("❌ Нельзя использовать свой промокод.")
    else:
        await update.message.reply_text("❌ Промокод не найден.")
    
    context.user_data['state'] = None
    await show_main_menu(update, context)


async def skip_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить ввод промокода"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Промокод не использован.")
    context.user_data['state'] = None
    await show_subscription_summary(update, context)


async def show_subscription_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать итоговую информацию о подписке"""
    user_id = update.effective_user.id
    plan_type = context.user_data.get('plan_type')
    device_count = context.user_data.get('device_count')
    
    if not plan_type or not device_count:
        keyboard = [[get_back_button()]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(
                "❌ Ошибка: данные подписки не найдены. Начните заново.",
                reply_markup=reply_markup
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Ошибка: данные подписки не найдены. Начните заново.",
                reply_markup=reply_markup
            )
        return
    
    user_data = db.get_or_create_user(user_id)
    
    # Для расчета скидок
    has_active_sub = db.get_active_subscription(user_id) is not None
    user_discount = db.get_user_discount(user_id) if has_active_sub else 0.0
    
    # Скидка для того, кто использует промокод
    referrer_discount = 0.0
    if user_data['used_promo_code']:
        referrer_discount = 0.10
    
    base_price = pricing.calculate_base_price(plan_type, device_count)
    final_price, discount_amount = pricing.calculate_final_price(base_price, user_discount, referrer_discount)
    
    plan_name = pricing.get_plan_name(plan_type)
    
    message = f"📋 *Итоговая информация о подписке:*\n\n"
    message += f"📅 Тариф: {plan_name}\n"
    message += f"📱 Устройств: {device_count}\n"
    message += f"💰 Базовая цена: {base_price}₽\n"
    
    discount_info = []
    if referrer_discount > 0:
        discount_info.append(f"Скидка за промокод: {referrer_discount*100:.0f}%")
    if user_discount > 0:
        active_refs = db.get_active_referrals_count(user_id)
        discount_info.append(f"Скидка за рефералов ({active_refs}): {user_discount*100:.0f}%")
    
    if discount_info:
        message += f"🎁 {' + '.join(discount_info)}\n"
        message += f"💸 Скидка: {discount_amount}₽\n"
    
    message += f"\n💵 *Итого к оплате: {final_price}₽*\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data="paid_subscription")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_subscription")],
        [get_back_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['final_price'] = final_price
    context.user_data['plan_type'] = plan_type
    context.user_data['device_count'] = device_count
    
    if update.callback_query:
        await update.callback_query.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)


async def paid_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь подтвердил оплату - создаем заявку для админа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    plan_type = context.user_data.get('plan_type')
    device_count = context.user_data.get('device_count')
    final_price = context.user_data.get('final_price')
    
    if not plan_type or not device_count or not final_price:
        await query.edit_message_text("❌ Ошибка: данные подписки не найдены.")
        return
    
    # Создаем заявку на подписку
    request_id = db.create_pending_subscription(user_id, plan_type, device_count, final_price)
    
    # Получаем информацию о пользователе
    user_data = db.get_or_create_user(user_id)
    user = update.effective_user
    plan_name = pricing.get_plan_name(plan_type)
    
    # Отправляем заявку всем администраторам
    admins = db.get_all_admins()
    
    if admins:
        admin_message = f"🔔 *Новая заявка на подписку*\n\n"
        admin_message += f"📋 ID заявки: #{request_id}\n"
        admin_message += f"👤 Пользователь: {user.first_name or 'Не указано'}\n"
        admin_message += f"🆔 User ID: {user_id}\n"
        if user.username:
            admin_message += f"📱 Username: @{user.username}\n"
        admin_message += f"\n📅 Тариф: {plan_name}\n"
        admin_message += f"📱 Устройств: {device_count}\n"
        admin_message += f"💵 Сумма: {final_price}₽\n"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{request_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_count = 0
        for admin_id in admins:
            try:
                await context.bot.send_message(
                    admin_id,
                    admin_message,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения админу {admin_id}: {e}")
        
        if sent_count == 0:
            logger.warning("Заявка создана, но не отправлена ни одному администратору!")
            await query.edit_message_text(
                "⚠️ Заявка создана, но администраторы не настроены.\n\n"
                "Обратитесь к администратору для активации подписки."
            )
            return
    else:
        logger.warning("Нет администраторов в системе!")
        await query.edit_message_text(
            "⚠️ Заявка создана, но администраторы не настроены.\n\n"
            "Обратитесь к администратору для активации подписки."
        )
        return
    
    # Очищаем данные
    context.user_data.clear()
    
    await query.edit_message_text(
        "✅ Заявка отправлена администратору!\n\n"
        "Ожидайте подтверждения. Вы получите уведомление после одобрения заявки."
    )
    await show_main_menu(update, context)


async def approve_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобрить заявку на подписку"""
    query = update.callback_query
    await query.answer()
    
    if not db.is_admin(query.from_user.id):
        await query.answer("❌ У вас нет прав администратора!", show_alert=True)
        return
    
    request_id = int(query.data.split("_")[1])
    pending_sub = db.get_pending_subscription(request_id)
    
    if not pending_sub:
        await query.edit_message_text("❌ Заявка не найдена.")
        return
    
    if pending_sub['status'] != 'pending':
        await query.edit_message_text(f"❌ Заявка уже обработана (статус: {pending_sub['status']})")
        return
    
    # Создаем подписку
    db.create_subscription(
        pending_sub['user_id'],
        pending_sub['plan_type'],
        pending_sub['device_count'],
        pending_sub['price']
    )
    
    # Обновляем статус заявки
    db.update_pending_subscription_status(request_id, 'approved')
    
    # Уведомляем пользователя
    try:
        plan_name = pricing.get_plan_name(pending_sub['plan_type'])
        await context.bot.send_message(
            pending_sub['user_id'],
            f"✅ *Ваша заявка одобрена!*\n\n"
            f"📅 Тариф: {plan_name}\n"
            f"📱 Устройств: {pending_sub['device_count']}\n"
            f"💵 Сумма: {pending_sub['price']}₽\n\n"
            f"Подписка активирована!",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await query.edit_message_text(
        f"✅ Заявка #{request_id} одобрена!\n\n"
        f"Пользователь уведомлен."
    )


async def reject_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонить заявку на подписку"""
    query = update.callback_query
    await query.answer()
    
    if not db.is_admin(query.from_user.id):
        await query.answer("❌ У вас нет прав администратора!", show_alert=True)
        return
    
    request_id = int(query.data.split("_")[1])
    pending_sub = db.get_pending_subscription(request_id)
    
    if not pending_sub:
        await query.edit_message_text("❌ Заявка не найдена.")
        return
    
    if pending_sub['status'] != 'pending':
        await query.edit_message_text(f"❌ Заявка уже обработана (статус: {pending_sub['status']})")
        return
    
    # Обновляем статус заявки
    db.update_pending_subscription_status(request_id, 'rejected')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            pending_sub['user_id'],
            "❌ Ваша заявка на подписку отклонена.\n\n"
            "Если у вас есть вопросы, свяжитесь с поддержкой."
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await query.edit_message_text(
        f"❌ Заявка #{request_id} отклонена.\n\n"
        f"Пользователь уведомлен."
    )


async def cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена оформления подписки"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    await query.edit_message_text("❌ Оформление подписки отменено.")
    await show_main_menu(update, context)


async def download_configs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачать конфигурационные файлы"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    subscription = db.get_active_subscription(user_id)
    
    if not subscription:
        keyboard = [[get_back_button()]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❌ У вас нет активной подписки.",
            reply_markup=reply_markup
        )
        return
    
    devices = db.get_user_devices(user_id)
    
    if not devices:
        keyboard = [[get_back_button()]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "У вас пока нет устройств. Хотите запросить конфигурацию?\n"
            "Введите название устройства:",
            reply_markup=reply_markup
        )
        context.user_data['state'] = States.WAITING_DEVICE_NAME
        return
    
    # Отправляем все конфигурационные файлы
    keyboard = [[get_back_button()]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📥 Отправляю ваши конфигурации...",
        reply_markup=reply_markup
    )
    
    for device in devices:
        config_json = device['config_file']
        config_link = config_gen.get_config_file(config_json)
        
        if config_link:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📱 *Конфигурация: {device['device_name']}*\n\n"
                         f"`{config_link}`\n\n"
                         "Скопируйте эту ссылку и импортируйте в ваш VPN клиент.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки конфигурации: {e}")
    
    await context.bot.send_message(
        chat_id=user_id,
        text="✅ Все конфигурации отправлены!",
        reply_markup=reply_markup
    )


async def handle_device_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка имени устройства"""
    device_name = update.message.text
    user_id = update.effective_user.id
    subscription = db.get_active_subscription(user_id)
    
    if not subscription:
        await update.message.reply_text("❌ У вас нет активной подписки.")
        context.user_data['state'] = None
        await show_main_menu(update, context)
        return
    
    # Проверяем количество устройств
    devices = db.get_user_devices(user_id)
    if len(devices) >= subscription['device_count']:
        await update.message.reply_text(
            f"❌ Вы достигли лимита устройств ({subscription['device_count']}).\n"
            "Для добавления устройства продлите подписку с увеличенным количеством."
        )
        context.user_data['state'] = None
        await show_main_menu(update, context)
        return
    
    # Показываем процесс генерации
    msg = await update.message.reply_text("🔄 Генерирую конфигурацию Xray...")
    
    # Генерируем конфигурацию
    config_json = config_gen.generate_config(user_id, device_name)
    
    if config_json:
        db.add_device(user_id, device_name, config_json)
        
        # Получаем ссылку для отправки
        config_link = config_gen.get_config_file(config_json)
        
        if config_link:
            # Отправляем конфигурацию
            try:
                await msg.edit_text(
                    f"✅ *Конфигурация для устройства '{device_name}' создана!*\n\n"
                    f"`{config_link}`\n\n"
                    "Скопируйте эту ссылку и импортируйте в ваш VPN клиент.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки конфигурации: {e}")
                await msg.edit_text("❌ Ошибка отправки конфигурации.")
        else:
            await msg.edit_text("❌ Ошибка генерации ссылки для импорта.")
    else:
        await msg.edit_text("❌ Ошибка генерации конфигурации Xray.")
    
    context.user_data['state'] = None
    await show_main_menu(update, context)


async def enter_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить промокод"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    
    message = "Введите промокод для применения скидки:\n\n"
    if user_data['used_promo_code']:
        message += f"Текущий промокод: {user_data['used_promo_code']}\n"
        message += "Вы можете ввести новый промокод для замены.\n"
    
    keyboard = [[get_back_button()]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)
    context.user_data['state'] = States.WAITING_PROMO


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о поддержке"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "💬 *Поддержка*\n\n"
        "Если у вас возникли вопросы или проблемы, свяжитесь с нами:\n\n"
        "📧 Email: support@vpn.example.com\n"
        "📱 Telegram: @vpn_support\n\n"
        "Мы работаем 24/7 и всегда готовы помочь!"
    )
    
    keyboard = [[get_back_button()]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов"""
    query = update.callback_query
    
    if query.data == "back_to_main":
        await show_main_menu(update, context)
    elif query.data == "start_subscription":
        await start_subscription(update, context)
    elif query.data.startswith("plan_"):
        await handle_plan_selection(update, context)
    elif query.data == "skip_promo":
        await skip_promo(update, context)
    elif query.data == "paid_subscription":
        await paid_subscription(update, context)
    elif query.data == "cancel_subscription":
        await cancel_subscription(update, context)
    elif query.data == "download_configs":
        await download_configs(update, context)
    elif query.data == "enter_promo":
        await enter_promo(update, context)
    elif query.data == "support":
        await show_support(update, context)
    elif query.data.startswith("approve_"):
        await approve_subscription(update, context)
    elif query.data.startswith("reject_"):
        await reject_subscription(update, context)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для добавления администратора"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /addadmin <user_id>")
        return
    
    try:
        new_admin_id = int(context.args[0])
        db.add_admin(new_admin_id)
        await update.message.reply_text(f"✅ Пользователь {new_admin_id} добавлен как администратор.")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")


def main():
    """Основная функция запуска бота"""
    token = os.getenv('BOT_TOKEN')
    
    if not token:
        logger.error("BOT_TOKEN не установлен! Проверьте файл .env")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
