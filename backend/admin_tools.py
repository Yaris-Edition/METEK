#!/usr/bin/env python3
"""
Служебные команды администратора.

  python3 admin_tools.py password   — спросит новый пароль, выведет строку ADMIN_PASS_HASH=...
  python3 admin_tools.py mailtest   — отправит тестовое письмо по настройкам из config.env
  python3 admin_tools.py totp       — сгенерирует секрет TOTP, выведет ADMIN_TOTP_SECRET=...,
                                      покажет QR в терминале и сохранит data/totp-qr.png
                                      (отсканировать в Google Authenticator или Яндекс Ключ)

Полученные строки вписать в backend/config.env и перезапустить бэкенд.
"""
import getpass
import sys
from pathlib import Path


def cmd_password() -> None:
    import bcrypt
    p1 = getpass.getpass("Новый пароль: ")
    p2 = getpass.getpass("Ещё раз: ")
    if p1 != p2:
        sys.exit("Пароли не совпадают")
    if len(p1) < 12:
        sys.exit("Минимум 12 символов — это единственный вход в админку")
    print("\nВпиши в config.env:\n")
    print("ADMIN_PASS_HASH=" + bcrypt.hashpw(p1.encode()[:72], bcrypt.gensalt(rounds=12)).decode())


def cmd_totp() -> None:
    import pyotp
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name="upload", issuer_name="МЕТЭК Сочи")
    print("\nВпиши в config.env:\n")
    print("ADMIN_TOTP_SECRET=" + secret)
    print("\nОтсканируй QR в Google Authenticator / Яндекс Ключ (или введи секрет вручную):\n")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
        out = Path(__file__).parent / "data" / "totp-qr.png"
        out.parent.mkdir(exist_ok=True)
        qr.make_image().save(out)
        print(f"\nPNG сохранён: {out}  — удали после настройки телефона!")
    except ImportError:
        print(uri)
    print("\nПроверка: текущий код =", pyotp.TOTP(secret).now())


def cmd_mailtest() -> None:
    import app  # подхватит config.env
    missing = [k for k, v in (("SMTP_HOST", app.SMTP_HOST), ("SMTP_USER", app.SMTP_USER),
                              ("SMTP_PASS", app.SMTP_PASS), ("MAIL_TO", app.MAIL_TO)) if not v]
    if missing:
        sys.exit("В config.env не заполнено: " + ", ".join(missing))
    print(f"Шлю через {app.SMTP_HOST}:{app.SMTP_PORT} от {app.MAIL_FROM} → {', '.join(app.MAIL_TO)} …")
    try:
        app._send_order_mail(0, "Тестовая заявка", "+79000000000")
    except Exception as e:
        sys.exit(f"ОШИБКА: {type(e).__name__}: {e}\n"
                 "535 — неверный пароль приложения или не включён IMAP в настройках ящика;\n"
                 "553 — MAIL_FROM должен совпадать с SMTP_USER;\n"
                 "timeout — порт закрыт файрволом или неверный SMTP_HOST.")
    print("Отправлено. Проверь ящик — тема «Заказ на обратный звонок №0».")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"password": cmd_password, "totp": cmd_totp, "mailtest": cmd_mailtest}.get(cmd, lambda: sys.exit(__doc__))()
