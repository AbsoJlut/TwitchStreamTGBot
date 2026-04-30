import json
import logging
import random
logging.getLogger("httpx").setLevel(logging.WARNING)             # HTTP‑клиент PTB 21
logging.getLogger("telegram.request").setLevel(logging.WARNING)  # слой запросов PTB
from typing import List, Optional, Dict

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.error import Forbidden
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters, ChatMemberHandler
)

log = logging.getLogger("tg_group_dlc")

# ---------- утилиты ----------
def escape_md2(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    for ch in ['\\','_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
        text = text.replace(ch, f"\\{ch}")
    return text.strip()

def _load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def _resolve_group_id(cfg: dict) -> Optional[int]:
    # Приватная группа, где включено приветствие
    if "DLC_GROUP_ID" in cfg:
        try:
            return int(cfg["DLC_GROUP_ID"])
        except Exception:
            log.error("config.json: DLC_GROUP_ID должен быть числом (chat_id вида -100...)")
            return None
    return None

def _deeplink(username: str, payload: str) -> str:
    # Откроет ЛС с ботом и передаст /start <payload>
    return f"https://t.me/{username}?start={payload}"

def _welcome_text(mention: str, chat_title: str) -> str:
    return (
        "*Привяу\\! Новенький влетел в чат — {m}* ✨\n\n"
        "Добро пожаловать в *{c}*\\.\n"
        "_Загляни в правила и чувствуй себя как дома\\!_"
    ).format(m=mention, c=escape_md2(chat_title or "наш чат"))

def _farewell_text(
    mention: str,
    chat_title: str,
    *,
    context: ContextTypes.DEFAULT_TYPE,
    scope: str = "global"
) -> str:
    """
    Генерирует текст прощания без повторов подряд.
    Работает по принципу shuffle-bag:
      • 3 варианта перемешиваются;
      • выдаются по одному;
      • когда кончаются — мешок пересоздаётся.
    scope — ключ пространства (например chat:ID), чтобы у каждого чата был свой цикл.
    """

    # Хранение состояний (мешков) в bot_data
    bag_store = context.application.bot_data.setdefault("FAREWELL_BAGS", {})
    bag = bag_store.get(scope)

    # Если мешка нет — создаём новый и перемешиваем
    if not bag:
        bag = [
            "Чат потерял ценные мозговые мощности\\. {m} отключился от нашего коллективного разума\\.",
            "Внимание\\! {m} выгрузился из матрицы нашего чата\\. Система дала сбой, или это был сознательный выбор\\?",
            "{m} вышел из чата\\. Начинаем операцию \"Скучаем, но делаем вид, что не очень\"\\."
        ]
        random.shuffle(bag)

    # Достаём первый вариант
    template = bag.pop(0)

    # Сохраняем обновлённый мешок или сбрасываем (если пустой)
    bag_store[scope] = bag or None

    # Финальное форматирование
    return template.format(
        m=mention,
        c=escape_md2(chat_title or "нашем чате")
    )


def _normalize_lines(v) -> str:
    """Принимает str или list[str], приводит к строке с нормальными переносами."""
    if v is None:
        return ""
    if isinstance(v, list):
        text = "\n".join(map(str, v))
    else:
        text = str(v)
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # Windows -> \n
    text = text.replace("\\n", "\n")                       # литералы "\n" -> перенос
    return text

# ---------- клавиатуры ----------
def _build_group_welcome_kb(bot_username: str, streamer: Optional[str], links: Dict[str, str]) -> InlineKeyboardMarkup:
    # В ГРУППЕ «Правила/Ссылки» — deep‑link в ЛС (не спамим в общий чат)
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📜 Правила", url=_deeplink(bot_username, "rules")),
            InlineKeyboardButton("🔗 Ссылки",  url=_deeplink(bot_username, "links")),
        ]
    ]
    row: List[InlineKeyboardButton] = []
    if streamer:
        row.append(InlineKeyboardButton("🎮 Twitch", url=f"https://www.twitch.tv/{streamer}"))
    if "Boosty" in links:
        row.append(InlineKeyboardButton("💛 Boosty", url=links["Boosty"]))
    if row:
        buttons.append(row)
    row = []
    if "Discord" in links:
        row.append(InlineKeyboardButton("💬 Discord", url=links["Discord"]))
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def _build_pm_menu_inline(streamer: Optional[str], links: Dict[str, str]) -> InlineKeyboardMarkup:
    # В ЛИЧКЕ: меню на inline‑кнопках (callback — бот отвечает тут же)
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📜 Правила", callback_data="rules_pm"),
            InlineKeyboardButton("🔗 Ссылки",  callback_data="links_pm"),
        ]
    ]
    row: List[InlineKeyboardButton] = []
    if streamer:
        row.append(InlineKeyboardButton("🎮 Twitch", url=f"https://www.twitch.tv/{streamer}"))
    if "Boosty" in links:
        row.append(InlineKeyboardButton("💛 Boosty", url=links["Boosty"]))
    if row:
        buttons.append(row)
    row = []
    if "Discord" in links:
        row.append(InlineKeyboardButton("💬 Discord", url=links["Discord"]))
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def _build_pm_reply_kb() -> ReplyKeyboardMarkup:
    # Reply‑клавиатура в ЛС, отправляет САМУ КОМАНДУ (/rules, /links)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("/rules"), KeyboardButton("/links")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def _build_links_command_kb(links: Dict[str, str]) -> InlineKeyboardMarkup:
    """Кнопки для команды /links (ОТДЕЛЬНЫЕ от SOCIAL_LINKS)."""
    # по одной кнопке в строке, чтобы красиво и кликабельно
    buttons = [[InlineKeyboardButton(name, url=url)] for name, url in links.items()]
    return InlineKeyboardMarkup(buttons)

# ---------- фолбэк‑приветствие через статус (если отключены join‑сервиски) ----------
# Универсальный обработчик chat_member — заменяет отдельные welcome/farewell
async def chat_member_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cmu = update.chat_member
    if not cmu:
        return

    chat = cmu.chat
    target_id = context.bot_data.get("group_id")
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) or chat.id != target_id:
        return

    # безопасный доступ к статусам (на случай, если что-то неожиданное)
    old_status = getattr(getattr(cmu, "old_chat_member", None), "status", None)
    new_status = getattr(getattr(cmu, "new_chat_member", None), "status", None)

    # логируем для отладки — очень помогает понять, какие апдейты приходят
    log.info("chat_member update: chat=%s old=%s new=%s", chat.id, old_status, new_status)

    # достаём пользователя: сначала new, потом old (в зависимости от типа апдейта)
    user = None
    if getattr(cmu, "new_chat_member", None) and getattr(cmu.new_chat_member, "user", None):
        user = cmu.new_chat_member.user
    elif getattr(cmu, "old_chat_member", None) and getattr(cmu.old_chat_member, "user", None):
        user = cmu.old_chat_member.user

    if not user:
        log.debug("chat_member: user not found in update; skipping")
        return

    # опционально: не шлём уведомления об уходе/входе для ботов
    if user.is_bot:
        log.debug("chat_member: ignored bot user=%s", user.id)
        return

    mention = f"@{escape_md2(user.username)}" if user.username else escape_md2(
        f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or "друг"
    )

    # joined: left/kicked -> member/administrator
    joined = (old_status in ("left", "kicked")) and (new_status in ("member", "administrator"))
    if joined:
        text = _welcome_text(mention, chat.title or "наш чат")
        kb = _build_group_welcome_kb(
            context.bot_data["bot_username"],
            context.bot_data.get("streamer"),
            context.bot_data.get("social_links") or {}
        )
        log.info("Приветствие: user=%s chat=%s", user.id, chat.id)
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                reply_markup=kb
            )
        except Forbidden:
            log.warning("Cannot send welcome: Forbidden for user=%s chat=%s", user.id, chat.id)
        except Exception as e:
            log.exception("Error sending welcome message: %s", e)
        return

    # left: member/administrator -> left/kicked
    left = (old_status in ("member", "administrator")) and (new_status in ("left", "kicked"))
    if left:
        text = _farewell_text(
            mention,
            chat.title or "наш чат",
            context=context,
            scope=f"chat:{chat.id}"  # мешочек на каждый чат
        )
        log.info("Прощание: user=%s chat=%s old=%s new=%s", user.id, chat.id, old_status, new_status)
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Forbidden:
            log.warning("Cannot send farewell: Forbidden for user=%s chat=%s", user.id, chat.id)
        except Exception as e:
            log.exception("Error sending farewell message: %s", e)
        return

    # остальные переходы — просто лог
    log.debug("chat_member: ignored transition for user=%s old=%s new=%s", user.id, old_status, new_status)



# ---------- отправка контента в ЛС ----------
async def _send_rules_pm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    rules = context.bot_data.get("rules_text")
    norm = _normalize_lines(rules)
    text = escape_md2(norm) if norm else "Правила пока не заданы\\.\nДобавь `DLC_RULES` в config\\.json\\."
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=_build_pm_reply_kb()
    )

async def _send_links_pm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Используем отдельный набор ссылок для /links
    links_cmd = context.bot_data.get("links_command") or {}
    if not links_cmd:
        await context.bot.send_message(
            chat_id=user_id,
            text="Отдельные ссылки не настроены\\. Заполни *LINKS_COMMAND* в config\\.json\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_build_pm_reply_kb()
        )
        return

    # добавляем пустую строку после заголовка
    lines = ["ПОЛЕЗНЫЕ ССЫЛКИ:\n"]
    for name, url in links_cmd.items():
        lines.append(f"• [{escape_md2(name)}]({url})")

    await context.bot.send_message(
        chat_id=user_id,
        text="\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )


# ---------- команды (ГЛОБАЛЬНЫЕ) ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start [rules|links]
    • если есть payload — сразу шлём соответствующий контент в ЛС;
    • при первом /start без payload — приветствие + мини‑/help + клавиатура.
    """
    args = context.args or []
    payload = args[0].lower() if args else ""
    user_id = update.effective_user.id

    if payload == "rules":
        await _send_rules_pm(user_id, context)
        return
    if payload == "links":
        await _send_links_pm(user_id, context)
        return

    app_data = context.application.bot_data
    welcomed = app_data.setdefault("welcomed_users", set())
    first_time = user_id not in welcomed
    if first_time:
        welcomed.add(user_id)

    kb_inline = _build_pm_menu_inline(context.bot_data.get("streamer"), context.bot_data.get("social_links") or {})
    kb_reply  = _build_pm_reply_kb()

    await update.message.reply_text(
        "Привяу\\! Это личка бота\\. Ниже — меню быстрых кнопок и команды в клавиатуре:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=kb_inline,
        disable_web_page_preview=True
    )

    if first_time:
        text = (
            "<b>Команды</b>\n"
                "\n"
            "• /rules — показать правила\n"
            "• /links — полезные ссылки\n"
            "• /help — эта справка\n"
            "• !кубик — бросок кубика\n"
            # "• !дуэль — дуэль кубиками (алиас)\n"
            "• !обнять — обнимашка\n"
            # "• !чик — прыжок в бассейн (алиас)\n"
            "• !лю — измеритель любви\n"
            "• !атака — применить силу\n"
            "• !отмена — отменить действие пользователя\n"
        )
        # reply_markup оставить как есть (клавиатура пригодится)
        await update.message.reply_html(
            text,
            reply_markup=kb_reply,
            disable_web_page_preview=True
        )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong 🏓")

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"chat_id: `{update.effective_chat.id}`\nuser_id: `{update.effective_user.id}`",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Команды</b>\n"
        "\n"
        "• /rules — показать правила\n"
        "• /links — полезные ссылки\n"
        "• /help — эта справка\n"
        "• !кубик — бросок кубика\n"
        # "• !дуэль — дуэль кубиками\n"
        "• !обнять — обнимашка\n"
        # "• !чик — прыжок в бассейн\n"
        "• !лю — измеритель любви\n"
        "• !атака — применить силу\n"
        "• !отмена — отменить действие пользователя\n"
    )
    await update.message.reply_html(text, disable_web_page_preview=True)

async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Работает везде: в ЛС отвечаем тут же, в чатах — шлём в ЛС пользователю
    if update.effective_chat.type == ChatType.PRIVATE:
        await _send_rules_pm(update.effective_chat.id, context)
    else:
        try:
            await _send_rules_pm(update.effective_user.id, context)
            await update.message.reply_text("Правила отправила в личку ✅")
        except Forbidden:
            username = context.bot_data["bot_username"]
            await update.message.reply_text(f"Открой ЛС со мной: {_deeplink(username, 'rules')}")

async def cmd_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type == ChatType.PRIVATE:
        await _send_links_pm(update.effective_chat.id, context)
    else:
        try:
            await _send_links_pm(update.effective_user.id, context)
            await update.message.reply_text("Ссылки отправила в личку ✅")
        except Forbidden:
            username = context.bot_data["bot_username"]
            await update.message.reply_text(f"Открой ЛС со мной: {_deeplink(username, 'links')}")

async def cmd_welcome_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Превью приветствия (в любом чате и в ЛС)
    user = update.effective_user
    mention = f"@{escape_md2(user.username)}" if user.username else escape_md2(
        f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or "друг"
    )
    text = _welcome_text(mention, update.effective_chat.title or "наш чат")
    if update.effective_chat.type == ChatType.PRIVATE:
        kb = _build_pm_menu_inline(context.bot_data.get("streamer"), context.bot_data.get("social_links") or {})
    else:
        kb = _build_group_welcome_kb(
            context.bot_data["bot_username"],
            context.bot_data.get("streamer"),
            context.bot_data.get("social_links") or {}
        )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=kb
    )
    
# ---------- callbacks (только ЛС) ----------
async def cb_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка inline-кнопок в ЛС: rules_pm / links_pm."""
    query = update.callback_query
    if not query:
        return
    # Быстрый отклик, чтобы Telegram не показывал "часики"
    await query.answer()

    # В группе таких callback-кнопок нет — игнор
    if query.message and query.message.chat and query.message.chat.type != ChatType.PRIVATE:
        return

    data = (query.data or "").lower()
    if data == "rules_pm":
        await _send_rules_pm(query.from_user.id, context)
        await query.answer("Правила отправлены ✅", show_alert=False)
    elif data == "links_pm":
        await _send_links_pm(query.from_user.id, context)
        await query.answer("Ссылки отправлены ✅", show_alert=False)


# ---------- приветствие новых участников (message‑путь) ----------
async def welcome_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.new_chat_members:
        return

    target_id = context.bot_data.get("group_id")
    if msg.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) or msg.chat.id != target_id:
        return

    welcomes: List[str] = []
    for user in msg.new_chat_members:
        mention = f"@{escape_md2(user.username)}" if user.username else escape_md2(
            f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or "друг"
        )
        welcomes.append(_welcome_text(mention, msg.chat.title))

    kb = _build_group_welcome_kb(
        context.bot_data["bot_username"],
        context.bot_data.get("streamer"),
        context.bot_data.get("social_links") or {}
    )
    await context.bot.send_message(
        chat_id=msg.chat.id,
        text="\n\n".join(welcomes),
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=kb
    )

# ---------- точка входа ----------
async def start_group_dlc() -> Application | None:
    """
    Создаём и запускаем PTB‑приложение в режиме polling.
    Возвращаем Application (чтобы при желании остановить на shutdown)
    или None — если не настроен chat_id.
    """
    cfg = _load_config()
    token = cfg["TELEGRAM_TOKEN"]
    group_id = _resolve_group_id(cfg)
    if group_id is None:
        log.warning("DLC отключён: не задан DLC_GROUP_ID в config.json")
        return None

    social_links: Dict[str, str] = cfg.get("SOCIAL_LINKS", {})
    links_command: Dict[str, str] = cfg.get("LINKS_COMMAND", {})  # НОВОЕ: отдельные ссылки для /links
    rules_text: Optional[str] = cfg.get("DLC_RULES")
    streamer: Optional[str] = cfg.get("STREAMER")

    app = ApplicationBuilder().token(token).build()
    app.bot_data["group_id"] = group_id
    app.bot_data["social_links"] = social_links
    app.bot_data["links_command"] = links_command  # сохраняем отдельно
    app.bot_data["rules_text"] = rules_text
    app.bot_data["streamer"] = streamer

    # username бота для deep‑link в групповой клавиатуре
    me = await app.bot.get_me()
    app.bot_data["bot_username"] = me.username

    # handlers
    # app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_members))
    app.add_handler(ChatMemberHandler(chat_member_status_handler, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("ping",   cmd_ping))
    app.add_handler(CommandHandler("id",     cmd_id))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("rules",  cmd_rules))
    app.add_handler(CommandHandler("links",  cmd_links))
    app.add_handler(CommandHandler("welcome_preview", cmd_welcome_preview))  # скрытая тест‑команда
    app.add_handler(CallbackQueryHandler(cb_buttons))

    # запуск (неблокирующий)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=["message", "channel_post", "chat_member", "callback_query"],
        poll_interval=0.0,
        timeout=50.0,
        drop_pending_updates=True
    )
    log.info(f"DLC запущен для группы {group_id}")
    return app
