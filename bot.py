from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, WebAppInfo, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters, CallbackQueryHandler
import sqlite3, secrets, time, asyncio, os, json
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROK_API_KEY   = os.environ.get("GROK_API_KEY")
WEB_APP_URL    = "https://steady-brioche-e0b7ee.netlify.app/"
PORT           = int(os.environ.get("PORT", 8080))

STARS_1     = 25
STARS_5     = 100
STARS_MONTH = 220

WHITELIST = {"riavlw"}

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

PROMPTS = {
    "email": """Ты — официальный эксперт предметной комиссии ЕГЭ по английскому языку 2026 года (письменная часть), прошедший обучение по «Методическим материалам» ФИПИ (Вербицкая М.В. и др.).
Ты оцениваешь электронные личные письма (Задание 37) ТОЧНО ТАК ЖЕ, КАК РЕАЛЬНЫЙ ЭКСПЕРТ, строго по критериям и логике методички.

ОБЯЗАТЕЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ ОЦЕНИВАНИЯ:

1. Определи тип задания: «Это Задание 37 (электронное личное письмо)».
2. Подсчёт объёма. Норма: 100–140 слов. Допустимо: 90–154 слова.
3. Критерии Задания 37 (максимум 6 баллов): К1 (0–2), К2 (0–2), К3 (0–2)
4. Итоговый балл: X/6
5. Комментарий: оценка, ошибки с цитатами, рекомендации, итог.

Пиши по-русски. Оцени это письмо:\n\n""",

    "essay": """Ты — официальный эксперт предметной комиссии ЕГЭ по английскому языку 2026 года (письменная часть), прошедший обучение по «Методическим материалам» ФИПИ (Вербицкая М.В. и др.).
Ты оцениваешь работы ТОЧНО ТАК ЖЕ, КАК РЕАЛЬНЫЕ ЭКСПЕРТЫ в проверках 2026 года.

ОБЯЗАТЕЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ:
1. Тип задания: Задание 38.
2. Объём: норма 200–250 слов, допустимо 180–275. Меньше 180 → 0 баллов.
3. Критерии К1(0–3), К2(0–3), К3(0–3), К4(0–3), К5(0–2). Макс 14 баллов.
4. Итог: X/14
5. Комментарий: оценка по критериям, ошибки с цитатами, рекомендации.

Пиши по-русски. Оцени эту работу:\n\n""",

    "composition": """Ты — официальный эксперт предметной комиссии ЕГЭ по русскому языку 2026 года (задание 27).
ОБЯЗАТЕЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ:
1. Объём: норма 150+ слов. Меньше 150 → 0 баллов.
2. Критерии К1–К10, макс 22 балла. Если К1=0 → К2=0 и К3=0.
3. Итог: X/22
4. Комментарий: баллы по критериям, все ошибки с цитатами, рекомендации.

Пиши по-русски. Проверь это сочинение:\n\n"""
}

# ── База данных ──
def init_db():
    con = sqlite3.connect("users.db")
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT,
        free_used INTEGER DEFAULT 0, paid_checks INTEGER DEFAULT 0,
        subscription_until INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY, user_id INTEGER,
        created_at INTEGER, used INTEGER DEFAULT 0)""")
    con.commit(); con.close()

def get_user(user_id, username=None):
    con = sqlite3.connect("users.db")
    row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        con.execute("INSERT INTO users VALUES (?,?,0,0,0)", (user_id, username))
        con.commit()
        row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return {"user_id":row[0],"username":row[1],"free_used":row[2],"paid_checks":row[3],"subscription_until":row[4]}

def use_free_check(user_id):
    con = sqlite3.connect("users.db")
    con.execute("UPDATE users SET free_used=1 WHERE user_id=?", (user_id,)); con.commit(); con.close()

def add_paid_checks(user_id, count):
    con = sqlite3.connect("users.db")
    con.execute("UPDATE users SET paid_checks=paid_checks+? WHERE user_id=?", (count,user_id)); con.commit(); con.close()

def use_paid_check(user_id):
    con = sqlite3.connect("users.db")
    con.execute("UPDATE users SET paid_checks=paid_checks-1 WHERE user_id=?", (user_id,)); con.commit(); con.close()

def add_subscription(user_id, days=30):
    con = sqlite3.connect("users.db")
    now = int(time.time())
    row = con.execute("SELECT subscription_until FROM users WHERE user_id=?", (user_id,)).fetchone()
    current = row[0] if row and row[0] > now else now
    new_until = current + days * 86400
    con.execute("UPDATE users SET subscription_until=? WHERE user_id=?", (new_until, user_id)); con.commit(); con.close()
    return new_until

def create_token(user_id):
    token = secrets.token_hex(16)
    con = sqlite3.connect("users.db")
    con.execute("INSERT INTO tokens VALUES (?,?,?,0)", (token, user_id, int(time.time()))); con.commit(); con.close()
    return token

def consume_token(token):
    """Проверяет и сжигает токен. Возвращает user_id или None."""
    con = sqlite3.connect("users.db")
    row = con.execute("SELECT user_id, used, created_at FROM tokens WHERE token=?", (token,)).fetchone()
    if not row:
        con.close(); return None
    user_id, used, created_at = row
    if used or (int(time.time()) - created_at > 1800):
        con.close(); return None
    con.execute("UPDATE tokens SET used=1 WHERE token=?", (token,)); con.commit(); con.close()
    return user_id

def validate_token(token):
    """Только проверяет, не сжигает — для /check_token."""
    con = sqlite3.connect("users.db")
    row = con.execute("SELECT used, created_at FROM tokens WHERE token=?", (token,)).fetchone()
    con.close()
    if not row: return False
    used, created_at = row
    return not used and (int(time.time()) - created_at <= 1800)

def is_whitelisted(username):
    return bool(username) and username.lower() in {w.lower() for w in WHITELIST}

def has_subscription(data):
    return data["subscription_until"] > int(time.time())

def has_access(data):
    return has_subscription(data) or data["paid_checks"] > 0

def webapp_keyboard(token):
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✍️ Открыть проверку", web_app=WebAppInfo(url=f"{WEB_APP_URL}?token={token}"))]],
        resize_keyboard=True, one_time_keyboard=False)

def payment_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💫 1 проверка — {STARS_1} Stars", callback_data="buy_stars_1")],
        [InlineKeyboardButton(f"💫 5 проверок — {STARS_5} Stars", callback_data="buy_stars_5")],
        [InlineKeyboardButton(f"💫 Месяц безлимит — {STARS_MONTH} Stars", callback_data="buy_stars_month")],
        [InlineKeyboardButton("💳 Оплата картой (скоро)", callback_data="buy_card")],
    ])

async def give_access(update, context, data, is_whitelist=False):
    user_id = data["user_id"]
    if is_whitelist or has_subscription(data):
        token = create_token(user_id)
        sub_text = ""
        if has_subscription(data):
            days_left = (data["subscription_until"] - int(time.time())) // 86400
            sub_text = f"📅 Подписка активна ещё {days_left} дн.\n\n"
        await update.message.reply_text(f"{sub_text}Нажми кнопку ниже 👇", reply_markup=webapp_keyboard(token))
        return
    token = create_token(user_id)
    use_paid_check(user_id)
    remaining = data["paid_checks"] - 1
    await update.message.reply_text(
        f"✅ Осталось проверок после этой: {remaining}\n\nНажми кнопку 👇",
        reply_markup=webapp_keyboard(token))
    if remaining == 0:
        asyncio.create_task(remove_keyboard_later(context, user_id))

async def remove_keyboard_later(context, chat_id):
    await asyncio.sleep(1860)
    await context.bot.send_message(chat_id=chat_id, text="⏰ Проверки закончились. Купи ещё → /buy", reply_markup=ReplyKeyboardRemove())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    data = get_user(user.id, username)
    if is_whitelisted(username):
        await give_access(update, context, data, is_whitelist=True); return
    if not data["free_used"]:
        token = create_token(user.id)
        use_free_check(user.id)
        await update.message.reply_text("👋 Привет! Тебе доступна 1 бесплатная проверка.\n\nНажми кнопку ниже 👇", reply_markup=webapp_keyboard(token))
        asyncio.create_task(remove_keyboard_later(context, user.id)); return
    if has_access(data):
        await give_access(update, context, data); return
    await update.message.reply_text("🔒 Доступ закончился.\n\nВыбери способ оплаты:", reply_markup=payment_menu())

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери способ оплаты:", reply_markup=payment_menu())

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username or "")
    if is_whitelisted(user.username or ""):
        await update.message.reply_text("👑 У тебя безлимитный доступ."); return
    if has_subscription(data):
        days_left = (data["subscription_until"] - int(time.time())) // 86400
        await update.message.reply_text(f"📅 Подписка активна ещё {days_left} дн."); return
    await update.message.reply_text(f"📊 Проверок осталось: {data['paid_checks']}\n\nКупить ещё → /buy")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invoices = {
        "buy_stars_1":     ("1 проверка ЕГЭ",  "Одна проверка по критериям ЕГЭ 2026",       "stars_1",     STARS_1),
        "buy_stars_5":     ("5 проверок ЕГЭ",  "Пять проверок по критериям ЕГЭ 2026",       "stars_5",     STARS_5),
        "buy_stars_month": ("Месяц безлимит",   "Безлимитные проверки на 30 дней",           "stars_month", STARS_MONTH),
    }
    if query.data in invoices:
        title, desc, payload, price = invoices[query.data]
        await context.bot.send_invoice(chat_id=query.message.chat_id, title=title, description=desc,
            payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(title, price)])
    elif query.data == "buy_card":
        await query.message.reply_text("💳 Оплата картой появится совсем скоро!\nПока можно оплатить через Telegram Stars 💫")

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    if payload == "stars_month":
        until = add_subscription(user_id, 30)
        from datetime import datetime
        token = create_token(user_id)
        await update.message.reply_text(
            f"✅ Подписка активна до {datetime.fromtimestamp(until).strftime('%d.%m.%Y')}!\n\nНажми кнопку 👇",
            reply_markup=webapp_keyboard(token))
    else:
        count = 5 if payload == "stars_5" else 1
        add_paid_checks(user_id, count)
        data = get_user(user_id)
        token = create_token(user_id)
        use_paid_check(user_id)
        remaining = data["paid_checks"] - 1
        await update.message.reply_text(
            f"✅ Оплата прошла! Куплено: {count} пр.\nОсталось после этой: {remaining}\n\nНажми кнопку 👇",
            reply_markup=webapp_keyboard(token))
        if remaining == 0:
            asyncio.create_task(remove_keyboard_later(context, user_id))

# ── HTTP эндпоинты ──
async def handle_check_token(request):
    if request.method == "OPTIONS":
        return web.Response(status=200, headers=CORS_HEADERS)
    token = request.rel_url.query.get("token", "")
    valid = validate_token(token) if token else False
    return web.json_response({"ok": valid}, headers=CORS_HEADERS)

async def handle_proxy(request):
    if request.method == "OPTIONS":
        return web.Response(status=200, headers=CORS_HEADERS)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad json"}, status=400, headers=CORS_HEADERS)

    token = body.get("token", "")
    work_type = body.get("type", "")
    text = body.get("text", "")
    photo = body.get("photo")  # base64 или null

    # Сжигаем токен — с этого момента он недействителен
    user_id = consume_token(token)
    if not user_id:
        return web.json_response({"error": "invalid_token"}, status=403, headers=CORS_HEADERS)

    prompt = PROMPTS.get(work_type)
    if not prompt:
        return web.json_response({"error": "unknown_type"}, status=400, headers=CORS_HEADERS)

    # Формируем сообщение для xAI
    if photo:
        user_content = [
            {"type": "image_url", "image_url": {"url": photo}},
            {"type": "text", "text": "Вот фото задания.\n\n" + prompt + text}
        ]
    else:
        user_content = prompt + text

    import aiohttp as aiohttp_client
    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROK_API_KEY}"},
                json={
                    "model": "grok-3",
                    "messages": [
                        {"role": "system", "content": "Ты опытный преподаватель, проверяющий работы по ЕГЭ. Отвечай структурированно и по делу."},
                        {"role": "user", "content": user_content}
                    ]
                },
                timeout=aiohttp_client.ClientTimeout(total=180)
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    return web.json_response({"error": f"xAI error: {err[:200]}"}, status=502, headers=CORS_HEADERS)
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]
                return web.json_response({"answer": answer}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=CORS_HEADERS)

async def run_web():
    app = web.Application()
    app.router.add_get("/check_token", handle_check_token)
    app.router.add_route("OPTIONS", "/check_token", handle_check_token)
    app.router.add_post("/proxy", handle_proxy)
    app.router.add_route("OPTIONS", "/proxy", handle_proxy)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Web server started on port {PORT}")

async def main():
    init_db()
    await run_web()
    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("buy", buy))
    tg_app.add_handler(CommandHandler("balance", balance))
    tg_app.add_handler(CallbackQueryHandler(handle_callback))
    tg_app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    tg_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling()
        await asyncio.Event().wait()

asyncio.run(main())
