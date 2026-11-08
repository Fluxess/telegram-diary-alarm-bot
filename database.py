import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "diary_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        timezone TEXT DEFAULT 'Europe/Moscow',
        alarm_nagging INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Таблица задач / будильников
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        due_datetime TEXT NOT NULL,
        is_alarm INTEGER DEFAULT 1,
        is_completed INTEGER DEFAULT 0,
        snooze_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    
    # Таблица записей дневника (мысли, настроение, итоги дня)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diary_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT NOT NULL,
        mood TEXT,
        notes TEXT NOT NULL,
        gratitude TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# User methods
def get_or_create_user(user_id: int, username: str = "") -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, username, timezone) VALUES (?, ?, ?)", 
                       (user_id, username, 'Europe/Moscow'))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    user_dict = dict(row)
    conn.close()
    return user_dict

def set_user_timezone(user_id: int, timezone: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET timezone = ? WHERE user_id = ?", (timezone, user_id))
    conn.commit()
    conn.close()

# Task methods
def create_task(user_id: int, title: str, due_datetime: str, description: str = "", is_alarm: int = 1) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (user_id, title, description, due_datetime, is_alarm, is_completed)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (user_id, title, description, due_datetime, is_alarm))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def get_user_tasks(user_id: int, completed: Optional[int] = 0) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if completed is not None:
        cursor.execute("SELECT * FROM tasks WHERE user_id = ? AND is_completed = ? ORDER BY due_datetime ASC", (user_id, completed))
    else:
        cursor.execute("SELECT * FROM tasks WHERE user_id = ? ORDER BY due_datetime ASC", (user_id,))
    rows = cursor.fetchall()
    tasks = [dict(row) for row in rows]
    conn.close()
    return tasks

def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def complete_task(task_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET is_completed = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def delete_task(task_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def update_task_due(task_id: int, new_due_datetime: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET due_datetime = ?, snooze_count = snooze_count + 1 WHERE id = ?", (new_due_datetime, task_id))
    conn.commit()
    conn.close()

# Diary methods
def add_diary_entry(user_id: int, date: str, mood: str, notes: str, gratitude: str = "") -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO diary_entries (user_id, date, mood, notes, gratitude)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, date, mood, notes, gratitude))
    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return entry_id

def get_user_diary_entries(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diary_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    entries = [dict(row) for row in rows]
    conn.close()
    return entries
