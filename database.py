import sqlite3
import time


DB_NAME = "bot.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users(
                       telegram_id TEXT PRIMARY KEY,
                        email TEXT,
                        app_password TEXT,
                        is_connected INTEGER DEFAULT 0
                        
                   )
                   """)
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS inbox_cooldown(
                       telegram_id TEXT PRIMARY KEY,
                       expiry REAL
                   )
                   """)
    conn.commit()
    conn.close()
    
def save_user(telegram_id, email, app_password, is_connected):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    
    cursor.execute("""
                   INSERT INTO users (
                       telegram_id,
                       email,
                       app_password,
                       is_connected
                   ) VALUES (?,?,?,?)
                   
                   ON CONFLICT(telegram_id) DO UPDATE SET
                   email=excluded.email,
                   app_password=excluded.app_password,
                   is_connected = excluded.is_connected """, (
                       telegram_id,
                       email,
                       app_password,
                       is_connected
                   ))
    
    conn.commit()
    conn.close()
    
def get_user(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    
    cursor.execute("""
                   SELECT email, app_password,is_connected
                   FROM users
                   WHERE telegram_id = ?
                   """, (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    return user


def is_connected(telegram_id):
    user = get_user(telegram_id)
    return user is not None and user [-1] == 1

def disconnect_user(telegram_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE users SET is_connected = 0 WHERE telegram_id = ?",(telegram_id,)
    )
    conn.commit()
    conn.close()

BASE = 60
MID = 120 
MAX = 300  
def set_inbox_cooldown(telegram_id, expiry):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
                   INSERT OR REPLACE INTO inbox_cooldown (telegram_id, expiry)
                   VALUES (?, ?)
                   """, (str(telegram_id), float(expiry)))
    
    conn.commit()
    conn.close()
    
def get_inbox_cooldown(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
                   SELECT expiry FROM inbox_cooldown
                   WHERE telegram_id = ?
                   """, (str(telegram_id),))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    return None

def clear_expired_cooldowns():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    
    cursor.execute("""
                   DELETE FROM inbox_cooldown
                   WHERE expiry < ?
                   """, (time.time(),))
    
    conn.commit()
    conn.close()
    
def get_remaining_cooldown(expiry: float):
    if not expiry:
        return 0
    
    remaining = expiry - time.time()
    return max(0, remaining)

def get_dynamic_cooldown(fail_count: int):
    if fail_count <= 1:
        return BASE
    if fail_count == 2:
        return MID
    else:
        return MAX
    
def create_expiry(seconds: float):
    import traceback
    print(f"DEBUG create_expiry called with: {seconds}")
    traceback.print_stack()  
    return time.time() + seconds

def remaining_time(expiry: float):
    return max(0, expiry - time.time())

def init_last_seen(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS last_seen (
            telegram_id TEXT PRIMARY KEY,
            message_id  TEXT
        )
    """)

def get_last_seen(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id FROM last_seen WHERE telegram_id = ?", (str(telegram_id),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_last_seen(telegram_id, message_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO last_seen (telegram_id, message_id)
        VALUES (?, ?)
    """, (str(telegram_id), message_id))
    conn.commit()
    conn.close()
    
def get_all_connected_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, email, app_password FROM users WHERE is_connected = 1")
    users = cursor.fetchall()
    conn.close()
    return users

def save_notif_email(notif_key, telegram_id, sender, subject, body, message_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notif_emails (
            notif_key  TEXT PRIMARY KEY,
            telegram_id TEXT,
            sender  TEXT,
            subject    TEXT,
            body       TEXT,
            message_id TEXT
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO notif_emails (notif_key, telegram_id, sender, subject, body, message_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (notif_key, str(telegram_id), sender, subject, body, message_id))
    conn.commit()
    conn.close()

def get_notif_email(notif_key):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, subject, body, message_id FROM notif_emails WHERE notif_key = ?", (notif_key,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            "from":       result[0],
            "subject":    result[1],
            "body":       result[2],
            "message_id": result[3]
        }
    return None

def get_notification_status(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            telegram_id        TEXT PRIMARY KEY,
            notifications      INTEGER DEFAULT 1,
            email_signature    TEXT DEFAULT ''
        )
    """)
    conn.commit()
    cursor.execute("SELECT notifications FROM user_settings WHERE telegram_id = ?", (str(telegram_id),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 1


def set_notification_status(telegram_id, status: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            telegram_id        TEXT PRIMARY KEY,
            notifications      INTEGER DEFAULT 1,
            email_signature    TEXT DEFAULT ''
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO user_settings (telegram_id, notifications, email_signature)
        VALUES (?, ?, COALESCE((SELECT email_signature FROM user_settings WHERE telegram_id = ?), ''))
    """, (str(telegram_id), status, str(telegram_id)))
    conn.commit()
    conn.close()


def get_signature(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email_signature FROM user_settings WHERE telegram_id = ?", (str(telegram_id),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""


def set_signature(telegram_id, signature: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_settings (telegram_id, notifications, email_signature)
        VALUES (?, COALESCE((SELECT notifications FROM user_settings WHERE telegram_id = ?), 1), ?)
    """, (str(telegram_id), str(telegram_id), signature))
    conn.commit()
    conn.close()