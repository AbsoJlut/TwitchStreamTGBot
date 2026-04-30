# tg_to_discord_bridge.py
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


async def tg_to_discord(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()

    source_chat = str(cfg.get("TG_NEWS_SOURCE", "")).replace("@", "")
    webhook_url = cfg.get("DISCORD_NEWS_WEBHOOK")
    embed_color = int(str(cfg.get("DISCORD_EMBED_COLOR", "00BFFF")).replace("#", ""), 16)

    if not webhook_url:
        return

    msg = update.effective_message
    chat = update.effective_chat

    if not msg or not chat:
        return

    chat_id = str(chat.id)
    chat_username = chat.username or ""

    if chat_id != source_chat and chat_username != source_chat:
        return

    text = msg.text or msg.caption or ""

    # ❗ Фильтр: игнорируем мусор (эмодзи, стикеры и т.д.)
    if not text.strip() and not msg.photo:
        return

    if text.strip() and not msg.photo:
        cleaned = text.strip()
        has_letters_or_digits = any(ch.isalnum() for ch in cleaned)

        if not has_letters_or_digits:
            return

    # ❗ Фильтр по ключевым словам (например стримы)
    block_keywords = cfg.get("TG_FILTER_BLOCK", [])
    text_lower = text.lower()

    if any(word.lower() in text_lower for word in block_keywords):
        return

    # Ссылка на пост (если канал публичный)
    post_url = None
    if chat.username:
        post_url = f"https://t.me/{chat.username}/{msg.message_id}"

    embed = {
        "title": "📢 Новость из Telegram",
        "description": text if text.strip() else " ",
        "color": embed_color,
        "footer": {
            "text": "Пост из Telegram канала @kotya_lisichkina"
        }
    }

    if post_url:
        embed["url"] = post_url

    files = {}

    # 📷 Фото
    if msg.photo:
        photo = msg.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        photo_bytes = await tg_file.download_as_bytearray()

        files["file"] = (
            "telegram_photo.jpg",
            bytes(photo_bytes),
            "image/jpeg"
        )

        embed["image"] = {
            "url": "attachment://telegram_photo.jpg"
        }

    payload = {
        "embeds": [embed]
    }

    async with aiohttp.ClientSession() as session:
        if files:
            form = aiohttp.FormData()
            form.add_field("payload_json", json.dumps(payload, ensure_ascii=False))

            for field_name, file_data in files.items():
                filename, content, content_type = file_data
                form.add_field(
                    field_name,
                    content,
                    filename=filename,
                    content_type=content_type
                )

            await session.post(webhook_url, data=form)
        else:
            await session.post(webhook_url, json=payload)


def register_tg_to_discord_bridge(app: Application):
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, tg_to_discord))