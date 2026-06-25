"""Тест email-уведомлений через SMTP Яндекс"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Используй переменные из .env
SMTP_SERVER = "smtp.yandex.ru"
SMTP_PORT = 587
SMTP_USER = os.environ.get('SMTP_USER', 'trudnik@yandex.ru')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

def test_smtp_connection():
    """Проверка подключения к SMTP серверу"""
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        if SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
            print(f"[OK] SMTP подключение успешно: {SMTP_USER}")
            server.quit()
            return True
        else:
            print(f"[SKIP] SMTP_PASSWORD не задан в переменных окружения")
            server.quit()
            return False
    except Exception as e:
        print(f"[WARN] SMTP ошибка: {e}")
        return False

def test_send_email():
    """Отправка тестового email"""
    if not SMTP_PASSWORD:
        print("[SKIP] Невозможно отправить письмо: SMTP_PASSWORD не задан")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = SMTP_USER  # Отправляем себе
        msg['Subject'] = 'Трудник: тестовое уведомление'
        body = 'Это тестовое уведомление от приложения Трудник. Если вы видите это письмо — email-уведомления работают корректно.'
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("[OK] Тестовое письмо отправлено")
        return True
    except Exception as e:
        print(f"[WARN] Ошибка отправки: {e}")
        return False

if __name__ == '__main__':
    print("=" * 50)
    print("Тест Email-уведомлений Трудник")
    print("=" * 50)
    smtp_ok = test_smtp_connection()
    if smtp_ok:
        test_send_email()
    print("=" * 50)
