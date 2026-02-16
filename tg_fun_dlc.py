# tg_fun_dlc.py
import json
import logging
import asyncio
import random
from html import escape
from typing import Dict, Optional, List, Tuple, Callable
from telegram.error import TimedOut, RetryAfter, NetworkError

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters,
)

log = logging.getLogger("tg_fun_dlc")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.request").setLevel(logging.WARNING)


async def safe_edit_text(
    msg: Message,
    text: str,
    *,
    parse_mode: ParseMode | None = None,
    timeout: float = 20.0,
    max_retries: int = 3
) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            await msg.edit_text(text, parse_mode=parse_mode, timeout=timeout)
            return
        except RetryAfter as e:
            # Flood control — подождать требуемое время
            await asyncio.sleep(getattr(e, "retry_after", 1.0))
        except TimedOut:
            # сетевой таймаут — подождать чуть-чуть и повторить
            await asyncio.sleep(0.5 * attempt)
        except NetworkError:
            await asyncio.sleep(0.5 * attempt)
    # если так и не получилось — пробросим последнее исключение
    await msg.edit_text(text, parse_mode=parse_mode, timeout=timeout)
    
# ----------------- утилиты -----------------
def escape_md2(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    for ch in ['\\','_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
        text = text.replace(ch, f"\\{ch}")
    return text.strip()

def _load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def _normalize_lines(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        text = "\n".join(map(str, v))
    else:
        text = str(v)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
    
def _is_cancel_protected(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    protected: set = context.application.bot_data.setdefault("CANCEL_PROTECTED_USERS", set())
    return user_id in protected



# ----------------- настройки -----------------
ROLL_ANIM_FRAMES = ["🎲", "🎲🎲", "🎲🎲🎲"]
ROLL_ANIM_DELAY = 0.3

# ----------------- roll core -----------------
def _get_roll_result(user_id: int, sides: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    lucky: set = context.application.bot_data.setdefault("ROLL_LUCKY_USERS", set())
    unlucky: set = context.application.bot_data.setdefault("ROLL_UNLUCKY_USERS", set())
    if user_id in lucky:
        return sides
    if user_id in unlucky:
        return 1
    return random.randint(1, sides)

# ----------------- /roll -----------------
async def cmd_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    sides = 20
    if args:
        try:
            sides = int(args[0])
        except Exception:
            pass
    if sides not in (4, 6, 10, 20, 100) or sides < 2:
        await update.message.reply_text("Использование: !кубик [4|6|10|20|100]. По умолчанию 20.")
        return

    msg = await update.message.reply_text("Бросаю кубик...")
    for frame in ROLL_ANIM_FRAMES:
        await asyncio.sleep(ROLL_ANIM_DELAY)
        await msg.edit_text(frame)

    result = _get_roll_result(update.effective_user.id, sides, context)
    if result == sides:
        final = f"🎉 Критическая удача! Выпало число: {result}"
    elif result == 1:
        final = f"💥 Критическая неудача! Выпало число: {result}"
    else:
        final = f"Выпало число: {result}"
    await msg.edit_text(final)

# ----------------- /roll_battle -----------------
# def _duels(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, dict]:
    # return context.application.bot_data.setdefault("FUN_DUELS", {})

# def _duel_kb() -> InlineKeyboardMarkup:
    # return InlineKeyboardMarkup([[InlineKeyboardButton("Принять", callback_data="duel_accept")]])

# async def cmd_roll_battle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /roll_battle @user [sides]
    # if not context.args and not update.message.reply_to_message:
        # await update.message.reply_text("Использование: !дуэль @user [4|6|10|20|100] или ответом на сообщение. По умолчанию 20.")
        # return

    # opponent = None
    # if update.message.entities:
        # for e in update.message.entities:
            # if e.type == "text_mention" and e.user:
                # opponent = e.user
                # break
    # if not opponent and update.message.reply_to_message and update.message.reply_to_message.from_user:
        # opponent = update.message.reply_to_message.from_user

    # sides = 20
    # try:
        # maybe = int(context.args[-1])
        # if maybe in (4, 6, 10, 20, 100):
            # sides = maybe
    # except Exception:
        # pass

    # if opponent is None:
        # await update.message.reply_text("Отметь оппонента через ответ на его сообщение или text_mention.")
        # return
    # if opponent.is_bot or opponent.id == update.effective_user.id:
        # await update.message.reply_text("❌ Выбери другого пользователя (не бота и не себя).")
        # return

    # text = (
        # f"🎯 {opponent.mention_html()} , {update.effective_user.mention_html()} вызывает тебя на дуэль (D{sides})!\n"
        # f"Нажми <b>Принять</b>, чтобы бросить кубик!"
    # )
    # m = await update.message.reply_html(text, reply_markup=_duel_kb())

    # _duels(context)[m.message_id] = {
        # "chat_id": m.chat_id,
        # "message_id": m.message_id,
        # "challenger_id": update.effective_user.id,
        # "opponent_id": opponent.id,
        # "sides": sides,
        # "state": "waiting",
    # }

# async def cb_duel_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # q = update.callback_query
    # await q.answer()
    # duels = _duels(context)
    # msg: Message = q.message
    # d = duels.get(msg.message_id)
    # if not d:
        # return

    # if q.from_user.id != d["opponent_id"]:
        # await q.answer("Ты не участник этой дуэли.", show_alert=True)
        # return
    # if d.get("state") != "waiting":
        # return
    # d["state"] = "running"

    # challenger_id = d["challenger_id"]
    # opponent_id   = d["opponent_id"]
    # sides         = d["sides"]

    # for frame in ROLL_ANIM_FRAMES:
        # await asyncio.sleep(ROLL_ANIM_DELAY)
        # await msg.edit_text(
            # f"{(await context.bot.get_chat_member(msg.chat_id, challenger_id)).user.mention_html()} бросает кубик...\n{frame}",
            # parse_mode=ParseMode.HTML
        # )

    # c_res = _get_roll_result(challenger_id, sides, context)
    # await msg.edit_text(
        # f"{(await context.bot.get_chat_member(msg.chat_id, challenger_id)).user.mention_html()} бросил кубик: <b>{c_res}</b>\n\n"
        # f"{(await context.bot.get_chat_member(msg.chat_id, opponent_id)).user.mention_html()} готовится...",
        # parse_mode=ParseMode.HTML
    # )
    # await asyncio.sleep(1)

    # for frame in ROLL_ANIM_FRAMES:
        # await asyncio.sleep(ROLL_ANIM_DELAY)
        # await msg.edit_text(
            # f"{(await context.bot.get_chat_member(msg.chat_id, opponent_id)).user.mention_html()} бросает кубик...\n{frame}",
            # parse_mode=ParseMode.HTML
        # )

    # o_res = _get_roll_result(opponent_id, sides, context)

    # result = (
        # f"⚔️ <b>Результаты дуэли (D{sides}):</b>\n"
        # f"{(await context.bot.get_chat_member(msg.chat_id, challenger_id)).user.mention_html()}: <b>{c_res}</b>\n"
        # f"{(await context.bot.get_chat_member(msg.chat_id, opponent_id)).user.mention_html()}: <b>{o_res}</b>\n"
    # )
    # if c_res > o_res:
        # result += f"\n🏆 Победил {(await context.bot.get_chat_member(msg.chat_id, challenger_id)).user.mention_html()}!"
    # elif c_res < o_res:
        # result += f"\n🏆 Победил {(await context.bot.get_chat_member(msg.chat_id, opponent_id)).user.mention_html()}!"
    # else:
        # result += "\n🤝 Ничья!"

    # await msg.edit_text(result, parse_mode=ParseMode.HTML, reply_markup=None)
    # d["state"] = "done"

# ----------------- /chik (с кастомным эмодзи) -----------------
# async def cmd_chik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # первый аргумент — эмодзи пользователя; по умолчанию парашют
    # parachute = (context.args[0] if context.args else "🪂").strip()

    # rows, cols = 10, 11
    # current_row = 0
    # current_col = random.randint(1, cols - 2)
    # direction = random.choice([-1, 1])

    # pool_start = random.randint(1, cols - 4)
    # pool_end = pool_start + 3

    # msg = await update.message.reply_text("Проверка снаряжения...")

    # trajectory: List[Tuple[int, int]] = []
    # for _ in range(rows):
        # field = [["⬛"] * cols for _ in range(rows)]
        # for i in range(pool_start, pool_end):
            # field[rows - 1][i] = "🌊"
        # field[current_row][current_col] = parachute

        # display = "\n".join("".join(r) for r in field)
        # HTML <pre> позволяет не экранировать эмодзи/символы
        # await msg.edit_text(f"<pre>{escape(display)}</pre>", parse_mode=ParseMode.HTML)
        # await safe_edit_text(msg, f"<pre>{escape(display)}</pre>", parse_mode=ParseMode.HTML, timeout=20.0)
        # await asyncio.sleep(0.3)

        # trajectory.append((current_row, current_col))
        # current_row += 1
        # current_col += direction
        # if current_col <= 0 or current_col >= cols - 1:
            # direction *= -1
            # current_col = max(1, min(cols - 2, current_col))
        # if random.random() < 0.25:
            # direction = random.choice([-1, 0, 1])

    # final_col = trajectory[-1][1]
    # final_field = [["⬛"] * cols for _ in range(rows)]
    # for i in range(pool_start, pool_end):
        # final_field[rows - 1][i] = "🌊"

    # if pool_start <= final_col < pool_end:
        # final_field[rows - 1][final_col] = "🏊"
        # display = "\n".join("".join(r) for r in final_field)
        # await safe_edit_text(msg, f"<pre>{escape(display)}</pre>\n🏊 Отличный прыжок! Приземление в бассейн! 🎯", parse_mode=ParseMode.HTML, timeout=20.0)
    # else:
        # final_field[rows - 1][final_col] = "💥"
        # display = "\n".join("".join(r) for r in final_field)
        # await safe_edit_text(msg, f"<pre>{escape(display)}</pre>\n💥 О нет! Промахнулся мимо бассейна! 💀", parse_mode=ParseMode.HTML, timeout=20.0)

# ----------------- /отмена -----------------
async def cmd_cancel_rp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    base = "Действие отменено."
    # Если команда отправлена ответом на сообщение — проверяем адресата
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
        # Блокируем отмену для защищённых пользователей
        if _is_cancel_protected(context, target.id):
            await update.message.reply_html(
                f"⛔ <b>Нельзя отменять действия в отношении</b> {target.mention_html()}."
            )
            return
        await update.message.reply_html(
            f"❌ <b>{base}</b>\n(Отменено по отношению к {target.mention_html()})"
        )
    else:
        await update.message.reply_html(f"❌ <b>{base}</b>")



# ----------------- /отпиздить -----------------
def _fight_templates() -> List[str]:
    return [
        "{author} жестко атаковал {target}! 👊💥",
        "{author} налетел на {target} с кулаками! 🥊",
        "{author} прописал {target} под дых! 🤜🤛",
        "{author} разнёс {target} в клочья! 💣",
        "{author} не пожалел {target}! 🪓"
    ]

async def cmd_fight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = None
    if update.message.entities:
        for e in update.message.entities:
            if e.type == "text_mention" and e.user:
                target = e.user
                break
    if not target and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    if not target:
        me = await context.bot.get_me()
        target = me

    if target.id == update.effective_user.id:
        await update.message.reply_text("Ты не можешь атаковать самого себя! 😅")
        return

    templates = _fight_templates()
    tpl = random.choice(templates)
    text = tpl.format(
        author=update.effective_user.mention_html(),
        target=target.mention_html()
    )

    await update.message.reply_html(f"<b>Драка! 🔥</b>\n\n{text}")

# ----------------- /hug -----------------
def _hugs_store(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, str]:
    return context.application.bot_data.setdefault("HUG_LAST", {})

def _hug_templates() -> List[str]:
    return [
        "{author} крепко обнимает {target}! 🥰",
        "{author} посылает {target} тёплые обнимашки! 🤗",
        "{author} дарит {target} нежные объятия! 💖",
        "{author} обнимает {target} со всей душой! 😊",
        "{author} и {target} обнимаются, как лучшие друзья! 🫂",
    ]

async def cmd_hug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = None
    if update.message.entities:
        for e in update.message.entities:
            if e.type == "text_mention" and e.user:
                target = e.user
                break
    if not target and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    if not target:
        me = await context.bot.get_me()
        target = me

    if target.id == update.effective_user.id:
        await update.message.reply_text("Ты не можешь обнять самого себя! 😅 Обними бота или другого пользователя! 🤗")
        return

    templates = _hug_templates()
    last = _hugs_store(context)
    prev = last.get(update.effective_user.id)
    available = [t for t in templates if t != prev] or templates
    tpl = random.choice(available)
    last[update.effective_user.id] = tpl

    text = tpl.format(
        author=update.effective_user.mention_html(),
        target=target.mention_html()
    )

    m = await update.message.reply_html(f"<b>Обнимашки! 🤗</b>\n\n{text}")
    store = context.application.bot_data.setdefault("HUG_MSG", {})
    store[m.message_id] = {"author_id": update.effective_user.id, "target_id": target.id}

async def cb_hug_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    info = context.application.bot_data.setdefault("HUG_MSG", {}).get(q.message.message_id)
    if not info:
        return
    if q.from_user.id != info["target_id"]:
        await q.answer("Только тот, кого обняли, может ответить обнимашкой!", show_alert=True)
        return
    if info.get("replied"):
        await q.answer("Ты уже ответил обнимашкой! 🤗", show_alert=True)
        return
    info["replied"] = True

    templates = _hug_templates()
    reply_text = random.choice(templates).format(
        author=(await context.bot.get_chat_member(q.message.chat_id, info["target_id"])).user.mention_html(),
        target=(await context.bot.get_chat_member(q.message.chat_id, info["author_id"])).user.mention_html(),
    )
    await q.message.reply_html(f"<b>Ответные обнимашки! 💞</b>\n\n{reply_text}")

# ----------------- /love -----------------
def _load_love_special_pairs(context: ContextTypes.DEFAULT_TYPE) -> set[Tuple[int,int]]:
    return context.application.bot_data.setdefault("LOVE_SPECIAL_PAIRS", set())

async def cmd_love(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = None
    if update.message.entities:
        for e in update.message.entities:
            if e.type == "text_mention" and e.user:
                target = e.user
                break
    if not target and update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user

    if not target:
        await update.message.reply_text("Использование: ответь на сообщение пользователя командой !лю, либо упомяни его.")
        return
    if target.id == update.effective_user.id:
        await update.message.reply_text("Ты не можешь измерить любовь к самому себе! Но мы уверены, что ты замечательный человек ❤️")
        return

    pairs = _load_love_special_pairs(context)
    if (update.effective_user.id, target.id) in pairs:
        love = 100
    else:
        love = random.randint(1, 100)

    bar_len = 10
    filled = int((love / 100) * bar_len)
    bar = "💖" * filled + "🖤" * (bar_len - filled)

    await update.message.reply_html(
        f"💘 <b>Измеритель любви</b>\n"
        f"{update.effective_user.mention_html()} любит {target.mention_html()} на <b>{love}%</b>\n{bar}"
    )

# ----------------- алиасы (! и /кириллица) -----------------
# Мапа строим ПОСЛЕ определения функций
FUN_ALIASES: Dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE], asyncio.Future]] = {
    "!кубик": cmd_roll,
    # "!дуэль": cmd_roll_battle,
    # "!чик":   cmd_chik,
    "!обнять": cmd_hug,
    "!лю":    cmd_love,
    "/кубик": cmd_roll,
    # "/дуэль": cmd_roll_battle,
    # "/чик":   cmd_chik,
    "/обнять": cmd_hug,
    "/лю":    cmd_love,
    "!атака": cmd_fight,
    "/атака": cmd_fight,
    "!отмена": cmd_cancel_rp,
    "/отмена": cmd_cancel_rp,  # если хочешь, чтобы работало и со слэшом по-русски
}

async def fun_alias_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    parts = update.message.text.strip().split()
    cmd = parts[0].lower()
    func = FUN_ALIASES.get(cmd)
    if not func:
        return
    context.args = parts[1:]
    await func(update, context)

# ----------------- регистрация/запуск -----------------
def _register_fun_handlers(app: Application) -> None:
    # Латинские «официальные» команды (подсветка и автодополнение в Telegram)
    app.add_handler(CommandHandler("roll",         cmd_roll))
    # app.add_handler(CommandHandler("roll_battle",  cmd_roll_battle))
    # app.add_handler(CallbackQueryHandler(cb_duel_accept, pattern="^duel_accept$"))

    # app.add_handler(CommandHandler("chik",         cmd_chik))
    app.add_handler(CommandHandler("hug",          cmd_hug))
    app.add_handler(CallbackQueryHandler(cb_hug_reply, pattern="^hug_reply$"))
    app.add_handler(CommandHandler("love",         cmd_love))
    app.add_handler(CommandHandler("ataka", cmd_fight))
    app.add_handler(CommandHandler("otmena", cmd_cancel_rp))


    # Алиасы: «!команды» и кириллические «/команды»
    app.add_handler(MessageHandler(filters.TEXT, fun_alias_router))

async def start_fun_dlc(app: Optional[Application] = None) -> Application:
    """
    Если передан app (уже работающее Application — напр., из tg_group_dlc),
    просто зарегистрируем команды в нём и НИЧЕГО не запускаем.
    Если app не передан — создадим своё приложение и запустим polling.
    """
    cfg = _load_config()
    token = cfg["TELEGRAM_TOKEN"]

    cancel_protected = set(map(int, cfg.get("CANCEL_PROTECTED_USERS", [])))
    lucky_ids = set(map(int, cfg.get("ROLL_LUCKY_USERS", [])))
    unlucky_ids = set(map(int, cfg.get("ROLL_UNLUCKY_USERS", [])))
    love_pairs = {tuple(map(int, p)) for p in cfg.get("LOVE_SPECIAL_PAIRS", [])}

    if app is None:
        app = ApplicationBuilder().token(token).build()
        app.bot_data["ROLL_LUCKY_USERS"] = lucky_ids
        app.bot_data["ROLL_UNLUCKY_USERS"] = unlucky_ids
        app.bot_data["LOVE_SPECIAL_PAIRS"] = love_pairs
        app.bot_data["CANCEL_PROTECTED_USERS"] = cancel_protected

        _register_fun_handlers(app)

        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            poll_interval=0.0,
            timeout=50.0,
            drop_pending_updates=True
        )
        log.info("FUN DLC запущен как отдельное приложение")
        return app
    else:
        app.bot_data.setdefault("ROLL_LUCKY_USERS", set()).update(lucky_ids)
        app.bot_data.setdefault("ROLL_UNLUCKY_USERS", set()).update(unlucky_ids)
        app.bot_data.setdefault("LOVE_SPECIAL_PAIRS", set()).update(love_pairs)
        app.bot_data.setdefault("CANCEL_PROTECTED_USERS", set()).update(cancel_protected)

        _register_fun_handlers(app)
        return app
