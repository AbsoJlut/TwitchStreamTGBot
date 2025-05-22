import json
import logging
import asyncio
import os
import signal
import locale
from datetime import datetime, timezone
import pytz
from twitchAPI.twitch import Twitch
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    logger.warning("Локаль ru_RU.UTF-8 не найдена, текст будет на английском")



def escape_markdown_v2(text):
    if not isinstance(text, str):
        text = str(text)
    special_chars = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text.strip()

def format_duration(seconds, always_show_hours=False):
    minutes = seconds // 60
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if always_show_hours or hours > 0:
        return f"{hours} ч {remaining_minutes} мин"
    return f"{minutes} мин"


try:
    with open('config.json') as f:
        config = json.load(f)
except Exception as e:
    logger.error(f"Ошибка при чтении config.json: {e}")
    raise

required_keys = ['TWITCH_CLIENT_ID', 'TWITCH_CLIENT_SECRET', 'TELEGRAM_TOKEN', 'CHANNEL_ID', 'STREAMER']
for key in required_keys:
    if key not in config:
        raise KeyError(f"Отсутствует ключ в конфиге: {key}")

TWITCH_CLIENT_ID = config['TWITCH_CLIENT_ID']
TWITCH_CLIENT_SECRET = config['TWITCH_CLIENT_SECRET']
TELEGRAM_TOKEN = config['TELEGRAM_TOKEN']
CHANNEL_ID = config['CHANNEL_ID']
STREAMER = config['STREAMER']
ALWAYS_SHOW_HOURS = config.get('ALWAYS_SHOW_HOURS', False)
SOCIAL_LINKS = config.get('SOCIAL_LINKS', {})

START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
message_id = None
is_streaming = False
last_message_text = None
last_stream_data = None

async def get_twitch_client():
    try:
        twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
        await twitch.authenticate_app([])
        logger.info("Успешная аутентификация Twitch")
        return twitch
    except Exception as e:
        logger.error(f"Twitch auth error: {e}")
        return None

async def get_stream_info(twitch):
    try:
        async for stream in twitch.get_streams(user_login=[STREAMER]):
            return {
                'title': stream.title,
                'game_name': stream.game_name,
                'thumbnail_url': stream.thumbnail_url.format(width=1920, height=1080),
                'started_at': stream.started_at,
                'viewer_count': stream.viewer_count
            }
        return None
    except Exception as e:
        logger.error(f"Twitch stream error: {e}")
        return None

async def send_or_update_message(bot, stream_info, is_ended=False):
    global message_id, last_message_text, last_stream_data

    try:
        now = datetime.now(timezone.utc)
        duration_seconds = int((now - stream_info['started_at']).total_seconds())

        current_stream_data = {
            'title': stream_info['title'],
            'game_name': stream_info['game_name'],
            'viewer_count': stream_info['viewer_count'],
            'thumbnail_url': stream_info['thumbnail_url'],
            'started_at': stream_info['started_at'],
            'duration_minutes': duration_seconds // 60
        }

        if not is_ended:
            if current_stream_data == last_stream_data:
                return
            last_stream_data = current_stream_data

        caption_lines = []

        if is_ended:
            caption_lines = [
                f"*🎬 {escape_markdown_v2(stream_info['title'])}*",
                "",
                f"*Игра*: *{escape_markdown_v2(stream_info['game_name'])}*",
                f"*Продолжительность*: *{escape_markdown_v2(format_duration(duration_seconds, ALWAYS_SHOW_HOURS))}*",
                "",
                "*Соцсети:*"
            ]
            for name, url in SOCIAL_LINKS.items():
                caption_lines.append(f"[{escape_markdown_v2(name)}]({url})")
            caption_lines.append(f"[Twitch](https://www.twitch.tv/{STREAMER})")
            caption_lines.append("")
            caption_lines.append("_🩶 Спасибо за компанию, приходи еще\\!_")
            reply_markup = None
        else:
            caption_lines = [
                f"*{escape_markdown_v2('Привяу, Котя запустила стрим:')}*",
                "",
                f"_🎬 {escape_markdown_v2(stream_info['title'])}_",
                "",
                f"*Игра*: *{escape_markdown_v2(stream_info['game_name'])}*",
                f"*Зрители*: *{escape_markdown_v2(stream_info['viewer_count'])}*",
                f"*Продолжительность*: *{escape_markdown_v2(format_duration(duration_seconds, ALWAYS_SHOW_HOURS))}*",
                "",
                "*Соцсети:*"
            ]
            for name, url in SOCIAL_LINKS.items():
                caption_lines.append(f"[{escape_markdown_v2(name)}]({url})")
            caption_lines.append(f"[Twitch](https://www.twitch.tv/{STREAMER})")
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("Смотреть стрим", url=f"https://www.twitch.tv/{STREAMER}")
            ]])

        caption = "\n".join(caption_lines)

        for attempt in range(3):
            try:
                if message_id is None:
                    msg = await bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=stream_info['thumbnail_url'],
                        caption=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=reply_markup
                    )
                    message_id = msg.message_id
                    logger.info(f"Отправлено новое сообщение: ID {message_id}")
                else:
                    await bot.edit_message_media(
                        chat_id=CHANNEL_ID,
                        message_id=message_id,
                        media=InputMediaPhoto(
                            media=stream_info['thumbnail_url'],
                            caption=caption,
                            parse_mode="MarkdownV2"
                        ),
                        reply_markup=reply_markup
                    )
                break
            except BadRequest as e:
                logger.warning(f"Попытка {attempt+1}: BadRequest: {e}")
                if attempt == 2:
                    unescaped = caption.replace("\\", "")
                    if message_id is None:
                        msg = await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=stream_info['thumbnail_url'],
                            caption=unescaped,
                            reply_markup=reply_markup
                        )
                        message_id = msg.message_id
                    else:
                        await bot.edit_message_media(
                            chat_id=CHANNEL_ID,
                            message_id=message_id,
                            media=InputMediaPhoto(
                                media=stream_info['thumbnail_url'],
                                caption=unescaped
                            ),
                            reply_markup=reply_markup
                        )
                else:
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"Ошибка при отправке: {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"Ошибка send_or_update_message: {e}")

async def check_stream():
    global is_streaming, message_id, last_stream_data

    bot = Bot(token=TELEGRAM_TOKEN)
    twitch = None

    while True:
        try:
            if twitch is None:
                twitch = await get_twitch_client()

            stream_info = await get_stream_info(twitch)
            if stream_info and not is_streaming:
                is_streaming = True
                await send_or_update_message(bot, stream_info, is_ended=False)
            elif not stream_info and is_streaming:
                is_streaming = False
                if last_stream_data:
                    await send_or_update_message(bot, last_stream_data, is_ended=True)
                message_id = None
                last_stream_data = None
            elif stream_info and is_streaming:
                await send_or_update_message(bot, stream_info, is_ended=False)

        except Exception as e:
            logger.error(f"Ошибка check_stream: {e}")
            twitch = None

        await asyncio.sleep(60)

async def shutdown():
    logger.info("Остановка бота...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in tasks:
        t.cancel()
    await asyncio.sleep(0.1)

async def main():
    logger.info(f"Запуск бота в {START_TIME}")
    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)

    loop.create_task(check_stream())
    await stop
    await shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
