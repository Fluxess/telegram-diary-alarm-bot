import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db

logger = logging.getLogger(__name__)

# Хранит активные задачи проверки будильников
active_alarms = {}

async def alarm_checker_loop(bot: Bot):
    """
    Фоновый цикл проверки дедлайнов и будильников.
    Срабатывает каждую минуту или при наступлении времени.
    """
    logger.info("Будильник-планировщик запущен...")
    while True:
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            
            # Получаем все незавершенные задачи
            conn = db.get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.timezone 
                FROM tasks t 
                JOIN users u ON t.user_id = u.user_id 
                WHERE t.is_completed = 0
            """)
            tasks = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            for task in tasks:
                user_tz = ZoneInfo(task["timezone"] or "Europe/Moscow")
                due_dt = datetime.strptime(task["due_datetime"], "%Y-%m-%d %H:%M").replace(tzinfo=user_tz)
                now_user = datetime.now(user_tz)
                
                # Если время наступило (или прошло не более 10 минут назад)
                diff_sec = (now_user - due_dt).total_seconds()
                if 0 <= diff_sec <= 70:
                    # Запускаем звонок будильника
                    task_id = task["id"]
                    if task_id not in active_alarms:
                        active_alarms[task_id] = True
                        asyncio.create_task(trigger_alarm(bot, task))
                        
        except Exception as e:
            logger.error(f"Ошибка в alarm_checker_loop: {e}")
            
        await asyncio.sleep(30)

async def trigger_alarm(bot: Bot, task: dict):
    """
    Настойчивый будильник (Nagging): шлет громкие пуши и кнопки,
    пока пользователь не нажмет 'Сделано' или 'Отложить'.
    """
    task_id = task["id"]
    user_id = task["user_id"]
    title = task["title"]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено!", callback_data=f"alarm_done_{task_id}"),
            InlineKeyboardButton(text="⏳ +5 минут", callback_data=f"alarm_snooze_{task_id}_5")
        ],
        [
            InlineKeyboardButton(text="⏳ +15 минут", callback_data=f"alarm_snooze_{task_id}_15"),
            InlineKeyboardButton(text="🔕 Отключить звук", callback_data=f"alarm_mute_{task_id}")
        ]
    ])
    
    nagging_rounds = 0
    max_nagging = 5  # Напомнит до 5 раз каждые 45 секунд, если не подтверждено
    
    while task_id in active_alarms and nagging_rounds < max_nagging:
        fresh_task = db.get_task(task_id)
        if not fresh_task or fresh_task["is_completed"]:
            break
            
        try:
            msg_text = (
                f"🚨 <b>ВНИМАНИЕ! БУДИЛЬНИК / ДЕЛО</b> 🚨\n\n"
                f"📌 <b>{title}</b>\n"
                f"⏰ Время выполнения: <code>{fresh_task['due_datetime']}</code>\n\n"
                f"⚡ <i>Подтверди выполнение или отложи звонок!</i>"
            )
            await bot.send_message(
                chat_id=user_id,
                text=msg_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_notification=False
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление будильника: {e}")
            break
            
        nagging_rounds += 1
        await asyncio.sleep(45)
        
    if task_id in active_alarms:
        del active_alarms[task_id]
