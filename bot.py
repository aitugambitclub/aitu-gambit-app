"""
Скелет Telegram-бота для клуба AITU.
Стек: Python + aiogram 3.x
Функции в этом файле: /start, ввод корп. почты, отправка кода, проверка кода.
Дальше (профиль, кнопка открытия Mini App с игрой) — добавим следующим шагом.

Установка:
    pip install aiogram asyncpg python-dotenv

Переменные окружения (.env):
    BOT_TOKEN=...              # токен от @BotFather
    DATABASE_URL=...           # строка подключения к Postgres (Supabase)
    EMAIL_API_KEY=...          # ключ Resend/SendGrid для отправки писем
    MINI_APP_URL=https://...   # ссылка на твой Mini App (когда будет готов)
"""

import asyncio
import os
import random
import re
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://example.com")
CORP_EMAIL_RE = re.compile(r"^[0-9]{6}@astanait\.edu\.kz$")  # подгони под реальный формат

router = Router()


class Auth(StatesGroup):
    waiting_email = State()
    waiting_code = State()


# ---------- вспомогательные функции (замени заглушки на реальные) ----------

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "aitugambitclub@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")  # 16-значный пароль приложения


async def send_verification_email(email: str, code: str) -> None:
    """
    Отправка кода подтверждения через Gmail SMTP + App Password.
    Если письма будут улетать в спам на @astanait.edu.kz — тогда переходим
    на Resend/SendGrid (у них выше репутация отправителя), но для старта
    и теста этого достаточно.
    """
    import smtplib
    import socket
    from email.mime.text import MIMEText

    msg = MIMEText(f"Твой код подтверждения для AITU Gambit: {code}\n\nКод действует 10 минут.")
    msg["Subject"] = "Код подтверждения — AITU Gambit"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = email

    class SMTP_SSL_IPv4(smtplib.SMTP_SSL):
        """Railway не умеет в IPv6 — форсим IPv4-адрес, TLS-хендшейк всё равно
        идёт по правильному hostname (smtp.gmail.com), так что сертификат ок."""
        def _get_socket(self, host, port, timeout):
            addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            sock = socket.create_connection(addr_info[0][4], timeout)
            return self.context.wrap_socket(sock, server_hostname=self._host)

    def _send() -> None:
        with SMTP_SSL_IPv4("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

    # smtplib синхронный — уводим в отдельный поток, чтобы не блокировать бота
    await asyncio.to_thread(_send)


async def save_code(db, telegram_id: int, email: str, code: str) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.execute(
        "INSERT INTO email_verification_codes (telegram_id, email, code, expires_at) "
        "VALUES ($1, $2, $3, $4)",
        telegram_id, email, code, expires,
    )


async def check_code(db, telegram_id: int, code: str) -> bool:
    row = await db.fetchrow(
        "SELECT id, email FROM email_verification_codes "
        "WHERE telegram_id=$1 AND code=$2 AND used=FALSE AND expires_at > now() "
        "ORDER BY created_at DESC LIMIT 1",
        telegram_id, code,
    )
    if not row:
        return False
    await db.execute("UPDATE email_verification_codes SET used=TRUE WHERE id=$1", row["id"])
    await db.execute(
        "INSERT INTO users (telegram_id, corp_email, is_verified) VALUES ($1, $2, TRUE) "
        "ON CONFLICT (telegram_id) DO UPDATE SET is_verified=TRUE",
        telegram_id, row["email"],
    )
    return True


# ---------- хендлеры ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db) -> None:
    existing = await db.fetchrow(
        "SELECT is_verified FROM users WHERE telegram_id=$1", message.from_user.id
    )
    if existing and existing["is_verified"]:
        kb = InlineKeyboardBuilder()
        kb.button(text="Открыть клуб", web_app=WebAppInfo(url=MINI_APP_URL))
        await message.answer("С возвращением! Открывай приложение:", reply_markup=kb.as_markup())
        return

    await message.answer(
        "Привет! Это клуб AITU. Чтобы попасть внутрь, подтверди свою "
        "университетскую почту (формат: 000000@astanait.edu.kz).\n\n"
        "Просто пришли её сюда сообщением."
    )
    await state.set_state(Auth.waiting_email)


@router.message(Auth.waiting_email)
async def got_email(message: Message, state: FSMContext, db) -> None:
    email = message.text.strip().lower()
    if not CORP_EMAIL_RE.match(email):
        await message.answer(
            "Похоже, это не университетская почта. Формат: 000000@astanait.edu.kz. Попробуй ещё раз."
        )
        return

    code = f"{random.randint(0, 999999):06d}"
    await save_code(db, message.from_user.id, email, code)
    await send_verification_email(email, code)
    await state.update_data(email=email)
    await state.set_state(Auth.waiting_code)
    await message.answer("Отправил код на почту. Пришли его сюда (действует 10 минут).")


@router.message(Auth.waiting_code)
async def got_code(message: Message, state: FSMContext, db) -> None:
    code = message.text.strip()
    ok = await check_code(db, message.from_user.id, code)
    if not ok:
        await message.answer("Код неверный или истёк. Попробуй /start заново.")
        return

    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="Заполнить профиль", web_app=WebAppInfo(url=f"{MINI_APP_URL}/profile"))
    await message.answer(
        "Почта подтверждена! Дальше — настрой профиль (юзернейм, имя, курс, специальность):",
        reply_markup=kb.as_markup(),
    )


async def main() -> None:
    import asyncpg

    # statement_cache_size=0 нужен из-за PgBouncer в transaction-mode (Supabase pooler)
    db_pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], statement_cache_size=0)

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        await dp.start_polling(bot, db=db_pool)  # db прокидывается во все хендлеры как аргумент
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())