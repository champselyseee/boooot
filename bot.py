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

RUB_1     = 27
RUB_5     = 110
RUB_MONTH = 210

WHITELIST = {"riavlw"}

YUKASSA_SHOP_ID = os.environ.get("YUKASSA_SHOP_ID", "")
YUKASSA_SECRET  = os.environ.get("YUKASSA_SECRET", "")

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

2. Подсчёт объёма. Норма: 100–140 слов. Допустимо: 90–154 слова. Если меньше 90 или больше 154 — сразу укажи и объясни последствия.

3. Критерии Задания 37 (максимум 6 баллов):

К1 «Решение коммуникативной задачи» (0–2) — строго 6 аспектов:
1. Ответ на первый вопрос из письма-стимула
2. Ответ на второй вопрос из письма-стимула
3. Ответ на третий вопрос из письма-стимула
4. Три вопроса по теме, указанной в задании (все ли заданы и по правильной теме)
5. Нормы вежливости (благодарность / положительные эмоции + надежда на будущие контакты)
6. Стилевое оформление (обращение, завершающая фраза, подпись — неофициальный стиль)
Для каждого аспекта: + / ± / – + точная цитата + короткое объяснение.

К2 «Организация текста» (0–2)
К3 «Языковое оформление текста» (0–2)

4. Итоговый балл: X/6

5. Комментарий (обязательно):
1️⃣ Оценка: балл по каждому критерию + итог
2️⃣ Ошибки: разбор по аспектам К1, затем К2–К3 с цитатами
3️⃣ Рекомендации: конкретные советы
4️⃣ Итог: краткое резюме

Пиши по-русски, официальным но понятным языком.
Теперь оцени это письмо:\n\n""",

    "essay": """Ты — официальный эксперт предметной комиссии ЕГЭ по английскому языку 2026 года (письменная часть), прошедший обучение по «Методическим материалам» ФИПИ (Вербицкая М.В. и др.).
Ты оцениваешь работы ТОЧНО ТАК ЖЕ, КАК РЕАЛЬНЫЕ ЭКСПЕРТЫ в проверках 2026 года (примеры: Camping in Zetland — 9/14, Dream job — 14/14, Why people travel in Zetland — слабое содержание).
ОБЯЗАТЕЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ (никогда не нарушай):

Определи тип задания
«Это Задание 38 (письменное высказывание с элементами рассуждения)».
Подсчёт объёма
Норма 200–250 слов. Допустимо 180–275 слов.
Меньше 180 слов → всё задание 0 баллов.
Больше 275 слов → проверяешь только первые 250 слов.
Критерии Задания 38 (макс. 14 баллов)
К1 «Решение коммуникативной задачи» (0–3) — строго 6 аспектов:
Вступление: тема проекта, источник данных (pie chart / table) + точная цель опроса (survey question). Если цель опроса не отражена или сильно искажена — ± или –.
2–3 основных факта с точными процентами.
1–2 сравнения + комментарий/объяснение (почему так, по мнению автора).
Проблема, которая может возникнуть в контексте темы проекта + реалистичное и логически связанное предложение решения. Проблема/решение должны быть напрямую связаны с темой (не «для бизнесменов», если тема — туризм).
Мнение автора + объяснение важности / ценности темы проекта (не просто «I like it»).
Стиль (нейтральный / формально-нейтральный).
Для каждого аспекта: + / ± / – + точная цитата + короткое объяснение.
К2 «Организация текста» (0–3)
К3 «Лексика» (0–3)
К4 «Грамматика» (0–3)
К5 «Орфография и пунктуация» (0–2)
Если К1 = 0 → всё задание = 0 баллов.

Реальная логика эксперта 2026 (обновлённая версия после анализа работ):
К1 — самый важный и строгий критерий. Эксперт сначала полностью оценивает все 6 аспектов.
Аспект 1 почти всегда получает ± или –, если нет точной формулировки цели опроса из задания. Даже близкая формулировка темы проекта без точной цели опроса снижает балл.
Называние неверного источника данных («table» вместо «pie-chart» и наоборот) — серьёзная фактическая ошибка, которая снижает К1 (аспект 1) и косвенно К2.
Аспект 4: решение должно быть реалистичным и конкретным для данной темы. Слишком общие решения часто получают ±.
Аспект 5: мнение должно объяснять ценность именно темы проекта, а не просто называть любимый вариант.
Сильное содержание (К1 = 3) → эксперт очень лоялен к языку: даже 3–4 мелкие ошибки позволяют ставить высокие баллы за К3, К4, К5 (как в примере Dream job 14/14).
Слабое содержание (К1 = 1 или 2) → язык проверяется значительно жёстче.
При сильном К1 мелкие опечатки почти не влияют. Систематические ошибки в ключевых словах темы заметно снижают К3 и К5.
Сравнения без объяснения «почему так» или с грубыми грамматическими ошибками часто получают ±.
К2 обычно высокий при логичном делении на абзацы и наличии связок, но фактические неточности могут снижать до 2.
Не будь сильно требовательным к лексике, если она совсем-совсем бедная — действуй как и действовал. Также не будь сильно требовательным к части с проблемой и решением — в этом вопросе стоит быть мягче.

Итоговый балл:
ИТОГ: X баллов из 14
Комментарий для ученика/учителя (обязательно):
1️⃣ Оценка: балл по каждому критерию К1–К5 + итог
2️⃣ Ошибки: разбор по аспектам К1, затем К2–К5 с цитатами
3️⃣ Рекомендации: конкретные советы по улучшению
4️⃣ Итог: краткое резюме

Пиши по-русски, официальным, но понятным языком. Используй термины методички: «аспект не раскрыт», «неточно», «не связано с темой проекта», «стилистически неудачно», «логическая заминка», «слабое решение».
Теперь оцени эту работу:\n\n""",

    "composition": """Ты — официальный эксперт предметной комиссии ЕГЭ по русскому языку 2026 года (задание 27), прошедший обучение по методическим материалам ФИПИ.
Ты оцениваешь работу ТОЧНО ТАК ЖЕ, как реальные эксперты на проверке.

ОБЯЗАТЕЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ:

1. Определи, есть ли работа. Если текста нет / он не по заданию → 0 по всем критериям.

2. Подсчёт объёма. Норма: 150+ слов. Если <150 слов → 0 баллов за всё.

3. Оцени по критериям К1–К10 (макс. 22 балла)

КРИТИЧЕСКОЕ ПРАВИЛО: Если К1 = 0 → автоматически К2 = 0 и К3 = 0.

К1 — Позиция автора (0–1): сформулирована ли чётко позиция автора по проблеме. Если искажена / отсутствует → 0. Для каждого: + / ± / – + точная цитата + объяснение.

К2 — Комментарий (0–3). Строго проверяются: пример 1 из текста, пояснение к нему, пример 2, пояснение, смысловая связь + её анализ. Если нет пояснения — пример НЕ засчитывается. Если это пересказ — 0. Для каждого элемента: + / ± / – + цитата + объяснение.

К3 — Позиция ученика + аргумент (0–2): есть ли чёткая позиция, есть ли аргумент (не из комиксов, игр и т.п.).

К4 — Фактическая точность (0–1)
К5 — Логика (0–2)
К6 — Этические нормы (0–1)
К7 — Орфография (0–3)
К8 — Пунктуация (0–3)
К9 — Грамматика (0–3)
К10 — Речь (0–3)

РЕАЛЬНАЯ ЛОГИКА ЭКСПЕРТА:
— К1 — ключевой, оценивается первым. Основные ошибки: подмена проблемы, искажение позиции автора, «автор рассказывает историю» вместо мысли.
— К2: пересказ = 0, нет пояснения = нет примера, связь без анализа = снижение.
— К3: «я согласен» без аргумента = 1 или 0.
— Если содержание сильное → эксперт мягче к языку. Если слабое → язык проверяется жёстче.
— Повторы, бедная речь, канцелярит → снижают К10.

ВЫВОД (обязательно):
1. Баллы по каждому критерию с кратким объяснением и цитатами.
2. Перечень всех ошибок: орфография, пунктуация, грамматика, речевые.
3. Итоговый балл: X/22.
4. Комментарий: что сделано хорошо, 3 главные причины потери баллов, как выйти на 22/22 конкретно.

Пиши по-русски, строго, но понятно. Используй формулировки: «аспект не раскрыт», «искажена позиция автора», «это пересказ», «нет пояснения», «логическая ошибка».

Теперь проверь следующее сочинение:\n\n`"""
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

def payment_menu(highlight=None):
    def mark(key, text):
        return ("✅ " if highlight == key else "") + text
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mark("s1",    f"⭐ 1 проверка — {STARS_1} Stars"),      callback_data="buy_stars_1")],
        [InlineKeyboardButton(mark("s5",    f"⭐ 5 проверок — {STARS_5} Stars"),      callback_data="buy_stars_5")],
        [InlineKeyboardButton(mark("smon",  f"⭐ Безлимит/мес — {STARS_MONTH} Stars"), callback_data="buy_stars_month")],
        [InlineKeyboardButton("──── или картой ────",                                  callback_data="noop")],
        [InlineKeyboardButton(mark("r1",    f"💳 1 проверка — {RUB_1} ₽"),            callback_data="buy_rub_1")],
        [InlineKeyboardButton(mark("r5",    f"💳 5 проверок — {RUB_5} ₽"),            callback_data="buy_rub_5")],
        [InlineKeyboardButton(mark("rmon",  f"💳 Безлимит/мес — {RUB_MONTH} ₽"),     callback_data="buy_rub_month")],
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
    elif query.data == "noop":
        return

    elif query.data in ("buy_rub_1", "buy_rub_5", "buy_rub_month"):
        rub_map = {
            "buy_rub_1":     ("r1",   "1 проверка — 27 руб",      RUB_1,   "rub_1"),
            "buy_rub_5":     ("r5",   "5 проверок — 110 руб",     RUB_5,   "rub_5"),
            "buy_rub_month": ("rmon", "Безлимит/мес — 230 руб",   RUB_MONTH, "rub_month"),
        }
        key, label, amount, pl = rub_map[query.data]

        if not YUKASSA_SHOP_ID or not YUKASSA_SECRET:
            await query.message.reply_text(
                "💳 Выбран тариф: " + label + "\n\nОплата картой скоро будет доступна!\nПока можно оплатить через Telegram Stars ⭐",
                reply_markup=payment_menu(highlight=key)
            )
            return

        import aiohttp as _h, uuid
        async with _h.ClientSession() as s:
            async with s.post(
                "https://api.yookassa.ru/v3/payments",
                auth=_h.BasicAuth(YUKASSA_SHOP_ID, YUKASSA_SECRET),
                headers={"Idempotence-Key": str(uuid.uuid4()), "Content-Type": "application/json"},
                json={
                    "amount": {"value": str(amount) + ".00", "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": "https://t.me/"},
                    "capture": True,
                    "description": label,
                    "metadata": {"user_id": str(query.from_user.id), "payload": pl}
                }
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    pay_url = d["confirmation"]["confirmation_url"]
                    await query.message.reply_text(
                        "💳 " + label,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить картой", url=pay_url)]])
                    )
                else:
                    err = await r.text()
                    await query.message.reply_text("❌ Ошибка: " + err[:200])

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
                    "model": ""model": "grok-4.20-0309-reasoning",",
                    "messages": [
                        {"role": "system", "content": "Ты опытный преподаватель, проверяющий работы по ЕГЭ. Отвечай структурированно и по делу."},
                        {"role": "user", "content": user_content}
                    ]
                },
                timeout=aiohttp_client.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    return web.json_response({"error": f"xAI error: {err[:200]}"}, status=502, headers=CORS_HEADERS)
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]
                return web.json_response({"answer": answer}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=CORS_HEADERS)

async def handle_yukassa_webhook(request):
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400)
    if body.get("event") != "payment.succeeded":
        return web.Response(status=200)
    meta    = body.get("object", {}).get("metadata", {})
    user_id = int(meta.get("user_id", 0))
    pl      = meta.get("payload", "")
    if not user_id or not pl:
        return web.Response(status=200)
    from telegram import Bot
    bot = Bot(token=TELEGRAM_TOKEN)
    if pl == "rub_month":
        add_subscription(user_id, 30)
        token = create_token(user_id)
        await bot.send_message(chat_id=user_id, text="✅ Оплата прошла! Безлимит на 30 дней активирован. Нажми кнопку 👇", reply_markup=webapp_keyboard(token))
    else:
        count = 5 if pl == "rub_5" else 1
        add_paid_checks(user_id, count)
        token = create_token(user_id)
        use_paid_check(user_id)
        remaining = get_user(user_id)["paid_checks"] - 1
        await bot.send_message(chat_id=user_id, text="✅ Оплата прошла! Куплено " + str(count) + " пр. Осталось: " + str(remaining) + " Нажми кнопку 👇", reply_markup=webapp_keyboard(token))
    return web.Response(status=200)

async def run_web():
    app = web.Application()
    app.router.add_get("/check_token", handle_check_token)
    app.router.add_route("OPTIONS", "/check_token", handle_check_token)
    app.router.add_post("/proxy", handle_proxy)
    app.router.add_route("OPTIONS", "/proxy", handle_proxy)
    app.router.add_post("/yukassa/webhook", handle_yukassa_webhook)
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
