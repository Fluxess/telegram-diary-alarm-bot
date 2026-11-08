import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event, Alarm
import urllib.parse

def generate_ics_file(task_id: int, title: str, due_dt_str: str, user_tz_str: str = "Europe/Moscow", description: str = "") -> str:
    """
    Генерирует .ics файл календаря с настроенным жестким будильником/напоминанием.
    """
    tz = ZoneInfo(user_tz_str)
    # due_dt_str: 'YYYY-MM-DD HH:MM'
    dt_local = datetime.strptime(due_dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    
    cal = Calendar()
    cal.add('prodid', '-//Telegram Diary Alarm Bot//mxm.dk//')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    
    event = Event()
    event.add('summary', f"⏰ {title}")
    event.add('description', description or f"Напоминание от Личного Дневника: {title}")
    event.add('dtstart', dt_local)
    event.add('dtend', dt_local + timedelta(minutes=15))
    event.add('dtstamp', datetime.now(tz))
    event['uid'] = f"task_{task_id}_{int(dt_local.timestamp())}@diarybot"
    
    # Добавляем Alarm в ics, чтобы системный календарь зазвонил
    alarm = Alarm()
    alarm.add('action', 'AUDIO')
    alarm.add('trigger', timedelta(minutes=0)) # прямо в момент события
    alarm.add('description', f"⏰ БУДИЛЬНИК: {title}")
    event.add_component(alarm)
    
    cal.add_component(event)
    
    os.makedirs("temp_ics", exist_ok=True)
    file_path = os.path.join("temp_ics", f"alarm_{task_id}.ics")
    with open(file_path, 'wb') as f:
        f.write(cal.to_ical())
        
    return file_path

def generate_google_calendar_url(title: str, due_dt_str: str, user_tz_str: str = "Europe/Moscow", description: str = "") -> str:
    """
    Генерирует ссылку для добавления в Google Calendar в 1 клик на Android/ПК/iOS.
    """
    tz = ZoneInfo(user_tz_str)
    dt_local = datetime.strptime(due_dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
    dt_end_utc = dt_utc + timedelta(minutes=30)
    
    fmt = "%Y%m%dT%H%M%SZ"
    dates = f"{dt_utc.strftime(fmt)}/{dt_end_utc.strftime(fmt)}"
    
    base = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    params = {
        "text": f"⏰ {title}",
        "dates": dates,
        "details": description or f"Напоминание из Telegram Diary: {title}",
    }
    return base + "&" + urllib.parse.urlencode(params)
