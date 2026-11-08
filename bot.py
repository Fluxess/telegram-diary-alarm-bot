import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, FSInputFile, WebAppInfo
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import database as db
import calendar_sync
import scheduler
import webapp_server

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment or .env file!")
PROXY_URL = os.getenv("PROXY_URL", None) # Например: "http://127.0.0.1:10809" или "socks5://127.0.0.1:10808"
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", 8080))
WEBAPP_URL = os.getenv("WEBAPP_URL", f"http://localhost:{WEBAPP_PORT}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

# FSM Состояния
class TaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_time = State()

class DiaryStates(StatesGroup):
    waiting_for_mood = State()
    waiting_for_notes = State()
    waiting_for_gratitude = State()

class SettingsStates(StatesGroup):
    waiting_for_timezone = State()

# Главное меню клавиатура
def get_main_menu(webapp_url: str):
    kb = [
        [
            InlineKeyboardButton(text="⏰ Поставить Будильник / Дело", callback_data="btn_add_task"),
            InlineKeyboardButton(text="📋 Мои дела", callback_data="btn_list_tasks")
        ],
        [
            InlineKeyboardButton(text="📖 Дневник дня (мысли/итоги)", callback_data="btn_add_diary"),
            InlineKeyboardButton(text="✨ Записи дневника", callback_data="btn_list_diary")
        ]
    ]
    
    # Telegram разрешает WebApp кнопки ТОЛЬКО с протоколом https://
    if webapp_url and webapp_url.startswith("https://"):
        kb.append([
            InlineKeyboardButton(text="📱 Открыть Web App", web_app=WebAppInfo(url=webapp_url)),
            InlineKeyboardButton(text="⚙️ Часовой пояс", callback_data="btn_settings_tz")
        ])
    else:
        kb.append([
            InlineKeyboardButton(text="⚙️ Часовой пояс", callback_data="btn_settings_tz")
        ])
        
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username or "")
    
    welcome_text = (
        f"👋 <b>Добро пожаловать в твой личный Дневник & Будильник!</b>\n\n"
        f"Я помогу держать фокус, не пропустить важные дела и фиксировать мысли каждого дня.\n\n"
        f"🌍 Твой текущий часовой пояс: <code>{user['timezone']}</code>\n\n"
        f"<b>Что умеет бот:</b>\n"
        f"• ⏰ <b>Будильник дел</b> с настойчивым повтором каждые 45 секунд, пока ты не подтвердишь выполнение\n"
        f"• 📲 <b>Синхронизация</b> — файл <code>.ics</code> и Google Calendar для настоящего звука будильника на телефоне\n"
        f"• 📖 <b>Дневник дня</b> — фиксация настроения, мыслей и благодарностей\n"
        f"• 📱 <b>Web App</b> — наглядный интерактивный интерфейс прямо внутри Telegram"
    )
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu(WEBAPP_URL))

# Настройка таймзоны
@dp.callback_query(F.data == "btn_settings_tz")
async def cb_settings_tz(callback: CallbackQuery, state: FSMContext):
    tz_buttons = [
        [InlineKeyboardButton(text="Москва (UTC+3)", callback_data="tz_set_Europe/Moscow")],
        [InlineKeyboardButton(text="Калининград (UTC+2)", callback_data="tz_set_Europe/Kaliningrad")],
        [InlineKeyboardButton(text="Самара (UTC+4)", callback_data="tz_set_Europe/Samara")],
        [InlineKeyboardButton(text="Екатеринбург (UTC+5)", callback_data="tz_set_Asia/Yekaterinburg")],
        [InlineKeyboardButton(text="Омск (UTC+6)", callback_data="tz_set_Asia/Omsk")],
        [InlineKeyboardButton(text="Красноярск / Новосибирск (UTC+7)", callback_data="tz_set_Asia/Krasnoyarsk")],
        [InlineKeyboardButton(text="Иркутск (UTC+8)", callback_data="tz_set_Asia/Irkutsk")],
        [InlineKeyboardButton(text="Владивосток (UTC+10)", callback_data="tz_set_Asia/Vladivostok")],
        [InlineKeyboardButton(text="✏️ Ввести свой город/пояс", callback_data="tz_set_custom")],
        [InlineKeyboardButton(text="« Назад", callback_data="btn_back_main")]
    ]
    await callback.message.edit_text(
        "🌍 <b>Выбери свой часовой пояс</b>, чтобы будильники звонили ровно по твоему времени:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=tz_buttons)
    )

@dp.callback_query(F.data.startswith("tz_set_"))
async def cb_tz_selected(callback: CallbackQuery, state: FSMContext):
    tz_val = callback.data.replace("tz_set_", "")
    if tz_val == "custom":
        await callback.message.edit_text(
            "Напиши свой часовой пояс в формате базы данных IANA (например: <code>Europe/Kyiv</code>, <code>Asia/Almaty</code>, <code>Asia/Tashkent</code>):",
            parse_mode="HTML"
        )
        await state.set_state(SettingsStates.waiting_for_timezone)
        return
        
    db.set_user_timezone(callback.from_user.id, tz_val)
    await callback.message.edit_text(
        f"✅ Часовой пояс успешно сохранен: <b>{tz_val}</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu(WEBAPP_URL)
    )

@dp.message(SettingsStates.waiting_for_timezone)
async def process_custom_tz(message: Message, state: FSMContext):
    tz_str = message.text.strip()
    try:
        ZoneInfo(tz_str)
        db.set_user_timezone(message.from_user.id, tz_str)
        await message.answer(f"✅ Часовой пояс установлен: <b>{tz_str}</b>", parse_mode="HTML", reply_markup=get_main_menu(WEBAPP_URL))
        await state.clear()
    except Exception:
        await message.answer("⚠️ Неверный формат часового пояса. Попробуй еще раз (например <code>Asia/Tbilisi</code> или <code>Europe/Minsk</code>):", parse_mode="HTML")

# Возврат в главное меню
@dp.callback_query(F.data == "btn_back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "⚡ <b>Главное меню</b>\nВыбери необходимое действие:",
        parse_mode="HTML",
        reply_markup=get_main_menu(WEBAPP_URL)
    )

# --- ДОБАВЛЕНИЕ ЗАДАЧИ / БУДИЛЬНИКА ---
@dp.callback_query(F.data == "btn_add_task")
async def cb_add_task(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 <b>Что нужно сделать?</b>\nВведи краткое название дела или будильника (например: <i>Выпить витамины</i>, <i>Созвон по проекту</i>):",
        parse_mode="HTML"
    )
    await state.set_state(TaskStates.waiting_for_title)

@dp.message(TaskStates.waiting_for_title)
async def process_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    
    # Подсказка текущего времени пользователя
    user = db.get_or_create_user(message.from_user.id)
    user_tz = ZoneInfo(user['timezone'])
    now_str = datetime.now(user_tz).strftime("%H:%M")
    today_str = datetime.now(user_tz).strftime("%Y-%m-%d")
    
    await message.answer(
        f"⏰ <b>Когда напомнить?</b> (Сейчас: <code>{now_str}</code>)\n\n"
        f"Форматы:\n"
        f"• Только время сегодня: <code>15:30</code> или <code>09:00</code>\n"
        f"• Дата и время: <code>{today_str} 18:00</code>\n"
        f"• Через сколько минут: <code>+10m</code> или <code>+1h</code>",
        parse_mode="HTML"
    )
    await state.set_state(TaskStates.waiting_for_time)

@dp.message(TaskStates.waiting_for_time)
async def process_task_time(message: Message, state: FSMContext):
    time_text = message.text.strip().lower()
    data = await state.get_data()
    title = data["title"]
    user_id = message.from_user.id
    user = db.get_or_create_user(user_id)
    tz = ZoneInfo(user["timezone"])
    now = datetime.now(tz)
    
    due_dt = None
    
    # Обработка +10m, +1h
    if time_text.startswith("+"):
        m = re.match(r"\+(\d+)([mh])", time_text)
        if m:
            val, unit = int(m.group(1)), m.group(2)
            if unit == "m":
                due_dt = now + timedelta(minutes=val)
            elif unit == "h":
                due_dt = now + timedelta(hours=val)
    elif re.match(r"^\d{1,2}:\d{2}$", time_text):
        h, m = map(int, time_text.split(":"))
        due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if due_dt <= now:
            due_dt += timedelta(days=1)
    elif re.match(r"^\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}$", time_text):
        try:
            due_dt = datetime.strptime(time_text, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        except Exception:
            pass
            
    if not due_dt:
        await message.answer("⚠️ Не удалось распознать время. Укажи, например: <code>18:30</code> или <code>+15m</code>:", parse_mode="HTML")
        return
        
    due_str = due_dt.strftime("%Y-%m-%d %H:%M")
    task_id = db.create_task(user_id, title, due_str, is_alarm=1)
    
    # Создаем .ics файл и ссылку на Google Календарь
    ics_path = calendar_sync.generate_ics_file(task_id, title, due_str, user["timezone"])
    gcal_url = calendar_sync.generate_google_calendar_url(title, due_str, user["timezone"])
    
    success_text = (
        f"✅ <b>Будильник установлен!</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"⏰ Время: <b>{due_str}</b> ({user['timezone']})\n\n"
        f"🔔 Бот начнет настойчиво напоминать точно в срок.\n"
        f"📲 <i>Хочешь, чтобы зазвонил системный будильник телефона? Нажми кнопку ниже:</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Добавить в Google Календарь", url=gcal_url)],
        [InlineKeyboardButton(text="📲 Скачать .ICS (iOS/Android)", callback_data=f"send_ics_{task_id}")],
        [InlineKeyboardButton(text="« В главное меню", callback_data="btn_back_main")]
    ])
    
    await message.answer(success_text, parse_mode="HTML", reply_markup=kb)
    await state.clear()

# Отправка .ics файла
@dp.callback_query(F.data.startswith("send_ics_"))
async def cb_send_ics(callback: CallbackQuery):
    task_id = int(callback.data.replace("send_ics_", ""))
    task = db.get_task(task_id)
    if not task:
        await callback.answer("Дело не найдено", show_alert=True)
        return
    user = db.get_or_create_user(callback.from_user.id)
    ics_path = calendar_sync.generate_ics_file(task_id, task["title"], task["due_datetime"], user["timezone"])
    
    await callback.message.answer_document(
        FSInputFile(ics_path, filename=f"alarm_{task_id}.ics"),
        caption="📲 Открой этот файл на телефоне, чтобы событие и будильник добавились в системный календарь!"
    )
    await callback.answer()

# --- СПИСОК ЗАДАЧ ---
@dp.callback_query(F.data == "btn_list_tasks")
async def cb_list_tasks(callback: CallbackQuery):
    tasks = db.get_user_tasks(callback.from_user.id, completed=0)
    if not tasks:
        await callback.message.edit_text(
            "🎉 <b>Список дел пуст!</b> Все выполнено или еще ничего не запланировано.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить дело", callback_data="btn_add_task")],
                [InlineKeyboardButton(text="« Назад", callback_data="btn_back_main")]
            ])
        )
        return
        
    text = "📋 <b>Твои активные дела & будильники:</b>\n\n"
    buttons = []
    for t in tasks[:8]:
        text += f"• <b>{t['title']}</b> — ⏰ <code>{t['due_datetime']}</code>\n"
        buttons.append([
            InlineKeyboardButton(text=f"✅ Сделано: {t['title'][:15]}", callback_data=f"alarm_done_{t['id']}"),
            InlineKeyboardButton(text="❌", callback_data=f"del_task_{t['id']}")
        ])
        
    buttons.append([InlineKeyboardButton(text="« Главное меню", callback_data="btn_back_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# Удаление задачи
@dp.callback_query(F.data.startswith("del_task_"))
async def cb_del_task(callback: CallbackQuery):
    task_id = int(callback.data.replace("del_task_", ""))
    db.delete_task(task_id)
    await callback.answer("Дело удалено")
    await cb_list_tasks(callback)

# --- УПРАВЛЕНИЕ БУДИЛЬНИКОМ (Сделано / Отложить) ---
@dp.callback_query(F.data.startswith("alarm_done_"))
async def cb_alarm_done(callback: CallbackQuery):
    task_id = int(callback.data.replace("alarm_done_", ""))
    db.complete_task(task_id)
    if task_id in scheduler.active_alarms:
        del scheduler.active_alarms[task_id]
    await callback.message.edit_text(
        "🎉 <b>Отлично сработано!</b> Дело помечено как выполненное. Фокус держится!",
        parse_mode="HTML",
        reply_markup=get_main_menu(WEBAPP_URL)
    )
    await callback.answer("Выполнено!")

@dp.callback_query(F.data.startswith("alarm_snooze_"))
async def cb_alarm_snooze(callback: CallbackQuery):
    _, _, task_id_str, mins_str = callback.data.split("_")
    task_id = int(task_id_str)
    mins = int(mins_str)
    
    task = db.get_task(task_id)
    if task:
        user = db.get_or_create_user(callback.from_user.id)
        tz = ZoneInfo(user["timezone"])
        new_due = datetime.now(tz) + timedelta(minutes=mins)
        new_due_str = new_due.strftime("%Y-%m-%d %H:%M")
        db.update_task_due(task_id, new_due_str)
        if task_id in scheduler.active_alarms:
            del scheduler.active_alarms[task_id]
            
        await callback.message.edit_text(
            f"⏳ Будильник отложен на <b>+{mins} минут</b> (до <code>{new_due_str}</code>).",
            parse_mode="HTML",
            reply_markup=get_main_menu(WEBAPP_URL)
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("alarm_mute_"))
async def cb_alarm_mute(callback: CallbackQuery):
    task_id = int(callback.data.replace("alarm_mute_", ""))
    if task_id in scheduler.active_alarms:
        del scheduler.active_alarms[task_id]
    await callback.message.edit_text(
        "🔕 Звуковой повтор остановлен для этого дела.",
        reply_markup=get_main_menu(WEBAPP_URL)
    )
    await callback.answer()

# --- ВЕДЕНИЕ ДНЕВНИКА ---
@dp.callback_query(F.data == "btn_add_diary")
async def cb_add_diary(callback: CallbackQuery, state: FSMContext):
    mood_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Супер", callback_data="mood_🔥"),
            InlineKeyboardButton(text="😊 Хорошо", callback_data="mood_😊"),
            InlineKeyboardButton(text="😐 Нормально", callback_data="mood_😐")
        ],
        [
            InlineKeyboardButton(text="😴 Усталость", callback_data="mood_😴"),
            InlineKeyboardButton(text="🌧️ Грустно", callback_data="mood_🌧️"),
            InlineKeyboardButton(text="🤯 Стресс", callback_data="mood_🤯")
        ],
        [InlineKeyboardButton(text="« Отмена", callback_data="btn_back_main")]
    ])
    await callback.message.edit_text(
        "📖 <b>Дневник дня: Шаг 1/3</b>\nКак твоё настроение сейчас?",
        parse_mode="HTML",
        reply_markup=mood_kb
    )

@dp.callback_query(F.data.startswith("mood_"))
async def cb_select_mood(callback: CallbackQuery, state: FSMContext):
    mood = callback.data.replace("mood_", "")
    await state.update_data(mood=mood)
    await callback.message.edit_text(
        f"Выбрано настроение: {mood}\n\n"
        f"<b>Шаг 2/3: Мысли & Итоги дня</b>\n"
        f"Напиши, что сегодня произошло важного, какие мысли или инсайты посетили тебя:",
        parse_mode="HTML"
    )
    await state.set_state(DiaryStates.waiting_for_notes)

@dp.message(DiaryStates.waiting_for_notes)
async def process_diary_notes(message: Message, state: FSMContext):
    await state.update_data(notes=message.text.strip())
    await message.answer(
        "<b>Шаг 3/3: Практика благодарности</b> 🙏\n"
        "За что ты благодарен сегодняшнему дню или себе? (Или отправь '-', чтобы пропустить):",
        parse_mode="HTML"
    )
    await state.set_state(DiaryStates.waiting_for_gratitude)

@dp.message(DiaryStates.waiting_for_gratitude)
async def process_diary_gratitude(message: Message, state: FSMContext):
    gratitude = message.text.strip()
    if gratitude == "-":
        gratitude = ""
        
    data = await state.get_data()
    user = db.get_or_create_user(message.from_user.id)
    tz = ZoneInfo(user["timezone"])
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    
    db.add_diary_entry(
        user_id=message.from_user.id,
        date=today_str,
        mood=data["mood"],
        notes=data["notes"],
        gratitude=gratitude
    )
    
    await message.answer(
        "✨ <b>Запись сохранена в твой личный дневник!</b>\nТы всегда можешь пересмотреть её в Web App или через меню.",
        parse_mode="HTML",
        reply_markup=get_main_menu(WEBAPP_URL)
    )
    await state.clear()

# Просмотр дневника
@dp.callback_query(F.data == "btn_list_diary")
async def cb_list_diary(callback: CallbackQuery):
    entries = db.get_user_diary_entries(callback.from_user.id, limit=5)
    if not entries:
        await callback.message.edit_text(
            "📖 В дневнике пока нет записей. Создай первую прямо сейчас!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Написать запись", callback_data="btn_add_diary")],
                [InlineKeyboardButton(text="« Назад", callback_data="btn_back_main")]
            ])
        )
        return
        
    text = "📖 <b>Последние записи дневника:</b>\n\n"
    for e in entries:
        text += f"📅 <b>{e['date']}</b> {e['mood']}\n"
        text += f"💭 <i>{e['notes']}</i>\n"
        if e['gratitude']:
            text += f"🙏 Благодарность: {e['gratitude']}\n"
        text += "───────────────\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Новая запись", callback_data="btn_add_diary")],
        [InlineKeyboardButton(text="« Главное меню", callback_data="btn_back_main")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# Основная точка запуска бота и сервера веб-приложения
async def main():
    db.init_db()
    logger.info("База данных SQLite инициализирована.")
    
    # Запускаем локальный веб-сервер для Web App
    app = webapp_server.create_webapp()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=os.getenv("WEBAPP_HOST", "0.0.0.0"), port=WEBAPP_PORT)
    await site.start()
    logger.info(f"Web App сервер запущен на порту {WEBAPP_PORT}")
    
    # Запуск фонового будильника
    asyncio.create_task(scheduler.alarm_checker_loop(bot))
    
    logger.info("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
