import json
import logging
import asyncio
import signal
import locale
from datetime import datetime, timezone
from twitchAPI.twitch import Twitch
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest
from tg_group_dlc import start_group_dlc
from tg_fun_dlc import start_fun_dlc
from html import escape as h
import random
from telegram.request import HTTPXRequest


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

last_sent = {
    'media_url': None,
    'caption_html': None,
    'reply_markup_key': None,
    'is_ended': None,
}
send_lock = asyncio.Lock()

# Установка русской локали
try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    logger.warning("Локаль ru_RU.UTF-8 не найдена, текст будет на английском")


def format_duration(seconds, always_show_hours=False):
    minutes = seconds // 60
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if always_show_hours or hours > 0:
        return f"{hours} ч {remaining_minutes} мин"
    return f"{minutes} мин"

# Загрузка конфигурации
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
STREAM_LINKS = config.get('STREAM_LINKS', {})
DELETE_STREAM_MESSAGE_AFTER_END = config.get('DELETE_STREAM_MESSAGE_AFTER_END', False)
DELETE_STREAM_MESSAGE_DELAY_SECONDS = config.get('DELETE_STREAM_MESSAGE_DELAY_SECONDS', 600)

START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
message_id = None
delete_task = None
is_streaming = False
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
            quant = 300  # 5 минут
            timestamp = int(datetime.now().timestamp() // quant * quant)

            game_name = stream.game_name or ""
            base_thumb = stream.thumbnail_url.format(width=1920, height=1080)

            irl_like = set(x.lower() for x in config.get("IRL_CATEGORIES", ["IRL"]))
            thumbnail_url = base_thumb  # по умолчанию — твичевское превью

            if game_name.lower() in irl_like:
                custom = config.get("IRL_IMAGE_URL")
                if custom:
                    thumbnail_url = custom

            return {
                'title': stream.title,
                'game_name': game_name,
                'thumbnail_url': f"{thumbnail_url}?t={timestamp}",
                'started_at': stream.started_at,
                'viewer_count': stream.viewer_count
            }
        return None
    except Exception as e:
        logger.error(f"Twitch stream error: {e}")
        return None


def build_stream_caption_html(stream_info, is_ended: bool, always_show_hours: bool, social_links: dict, streamer: str) -> str:
    title = h(stream_info['title'])
    game  = h(stream_info['game_name'])
    viewers = stream_info.get('viewer_count')
    now = datetime.now(timezone.utc)
    duration_seconds = int((now - stream_info['started_at']).total_seconds())
    dur_str = h(format_duration(duration_seconds, always_show_hours))

    lines = []
    if is_ended:
        lines += [
            f"<b>🎬 {title}</b>",
            "",
            f"<b>Игра</b>: <b>{game}</b>",
            f"<b>Продолжительность</b>: <b>{dur_str}</b>",
            "",
        ]
    else:
        lines += [
            f"<i>🎬 {title}</i>",
            "",
            f"<b>Игра</b>: <b>{game}</b>",
            f"<b>Зрители</b>: <b>{h(str(viewers))}</b>",
            f"<b>Продолжительность</b>: <b>{dur_str}</b>",
            "",
        ]

    # 🟣 Ссылки текстом — только после окончания стрима (по желанию)
    if is_ended:
        # lines.append(h("Общий тг чат со стримлером по подписке на бусти любого уровня, присоединяйся 🩶"))
        social_line_parts = [f"<a href=\"{h(url)}\">{h(name)}</a>" for name, url in social_links.items()]
        social_line_parts.append(f"<a href=\"https://www.twitch.tv/{h(streamer)}\">Twitch</a>")
        lines.append(" • ".join(social_line_parts))


    

    return "\n".join(lines)


async def send_or_update_message(bot: Bot, stream_info: dict, is_ended: bool = False):
    global message_id, last_sent, last_stream_data
    async with send_lock:
        # ВСЁ содержимое функции ниже — на один уровень глубже (внутри with)
        # защита от наивной даты
        started_at = stream_info['started_at']
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        caption_html = build_stream_caption_html(
            stream_info={**stream_info, 'started_at': started_at},
            is_ended=is_ended,
            always_show_hours=ALWAYS_SHOW_HOURS,
            social_links=SOCIAL_LINKS,
            streamer=STREAMER
        )

        reply_markup = None
        if not is_ended:
            buttons = []

            # 1-я строка: смотреть стрим
            buttons.append([
                InlineKeyboardButton("Смотреть стрим", url=f"https://www.twitch.tv/{STREAMER}")
            ])

            # Соцсети: по 2 кнопки в ряд
            row = []
            for name, url in STREAM_LINKS.items():
                row.append(InlineKeyboardButton(name, url=url))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
        
            reply_markup = InlineKeyboardMarkup(buttons)


        def _reply_markup_key(markup):
            if not markup:
                return None
            rows = []
            for row in markup.inline_keyboard:
                rows.append(tuple((btn.text, getattr(btn, 'url', None)) for btn in row))
            return tuple(rows)

        media_url = stream_info['thumbnail_url']
        caption = caption_html
        rm_key = _reply_markup_key(reply_markup)

        changed_media   = (media_url != last_sent['media_url'])
        changed_caption = (caption != last_sent['caption_html'])
        changed_rm      = (rm_key   != last_sent['reply_markup_key'])
        changed_state   = (is_ended != last_sent['is_ended'])

        if message_id is not None and not (changed_media or changed_caption or changed_rm or changed_state):
            return

        for attempt in range(3):
            try:
                if message_id is None:
                    msg = await bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=media_url,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    message_id = msg.message_id
                    logger.info(f"Отправлено новое сообщение: ID {message_id}")
                else:
                    if changed_media or changed_state:
                        await bot.edit_message_media(
                            chat_id=CHANNEL_ID,
                            message_id=message_id,
                            media=InputMediaPhoto(
                                media=media_url,
                                caption=caption,
                                parse_mode="HTML",
                            ),
                            reply_markup=reply_markup
                        )
                    elif changed_caption or changed_rm:
                        await bot.edit_message_caption(
                            chat_id=CHANNEL_ID,
                            message_id=message_id,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )

                last_sent.update({
                    'media_url': media_url,
                    'caption_html': caption,
                    'reply_markup_key': rm_key,
                    'is_ended': is_ended,
                })
                last_stream_data = {
                    'title': stream_info['title'],
                    'game_name': stream_info['game_name'],
                    'viewer_count': stream_info.get('viewer_count'),
                    'thumbnail_url': media_url,
                    'started_at': started_at,
                }
                break

            except BadRequest as e:
                msg = str(e).lower()
                logger.warning(f"Попытка {attempt+1}: BadRequest: {e}")

                if "message is not modified" in msg:
                    last_sent.update({
                        'media_url': media_url,
                        'caption_html': caption,
                        'reply_markup_key': rm_key,
                        'is_ended': is_ended,
                    })
                    break

                if "message to edit not found" in msg:
                    if message_id is not None:
                        sent = await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=media_url,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )
                        message_id = sent.message_id
                        last_sent.update({
                            'media_url': media_url,
                            'caption_html': caption,
                            'reply_markup_key': rm_key,
                            'is_ended': is_ended,
                        })
                    break

                if attempt < 2:
                    await asyncio.sleep(1.5 + random.random())
                    continue
                break

            except Exception as e:
                logger.error(f"Ошибка при отправке: {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(1.5 + random.random())

async def delete_stream_message_later(bot: Bot, delay: int):
    global message_id
    try:
        await asyncio.sleep(delay)
        if message_id:
            await bot.delete_message(chat_id=CHANNEL_ID, message_id=message_id)
            logger.info(f"Сообщение о стриме удалено (ID {message_id})")
            message_id = None
    except asyncio.CancelledError:
        logger.info("Удаление сообщения отменено (стрим возобновился)")
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")


async def check_stream():
    global is_streaming, message_id, last_stream_data, last_sent, delete_task

    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=10.0,
    )
    bot = Bot(token=TELEGRAM_TOKEN, request=request)
    twitch = None

    while True:
        try:
            if twitch is None:
                twitch = await get_twitch_client()

            stream_info = await get_stream_info(twitch)

            if stream_info and not is_streaming:
                is_streaming = True

                # отменяем отложенное удаление, если оно было
                if delete_task and not delete_task.done():
                    delete_task.cancel()
                delete_task = None

                await send_or_update_message(bot, stream_info, is_ended=False)

            elif not stream_info and is_streaming:
                is_streaming = False

                if last_stream_data:
                    await send_or_update_message(bot, last_stream_data, is_ended=True)

                    # запускаем ОДНУ задачу удаления (если включено)
                    if DELETE_STREAM_MESSAGE_AFTER_END:
                        if delete_task and not delete_task.done():
                            delete_task.cancel()
                        delete_task = asyncio.create_task(
                            delete_stream_message_later(bot, DELETE_STREAM_MESSAGE_DELAY_SECONDS)
                        )

                last_stream_data = None
                last_sent = {'media_url': None, 'caption_html': None, 'reply_markup_key': None, 'is_ended': None}

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

    # 1) запускаем DLC для группы и получаем его Application
    dlc_app = None
    try:
        dlc_app = await start_group_dlc()
        if dlc_app:
            logger.info("Group DLC запущен")
    except Exception as e:
        logger.exception(f"DLC не запустился: {e}")

    try:
        if dlc_app:
            await start_fun_dlc(app=dlc_app)
            logger.info("Fun DLC подключён к существующему приложению")
        else:
            pass
    except Exception as e:
        logger.exception(f"Fun DLC не подключился: {e}")

    await stop

    try:
        if dlc_app:
            await dlc_app.updater.stop()
            await dlc_app.stop()
            await dlc_app.shutdown()
    except Exception as e:
        logger.warning(f"При остановке DLC: {e}")

    await shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
