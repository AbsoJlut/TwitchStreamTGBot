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

# Установка русской локали для форматирования текста
try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    logger.warning("Локаль ru_RU.UTF-8 не найдена, текст будет на английском")

# Функция для экранирования символов MarkdownV2
def escape_markdown_v2(text):
    """Экранирует специальные символы для Telegram MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    special_chars = r'_[]()~`>#+-=|{}.!?\'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Функция для форматирования продолжительности
def format_duration(seconds, always_show_hours=False):
    """Форматирует продолжительность в 'X ч Y мин' или 'Y мин'."""
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
except FileNotFoundError:
    logger.error("Файл config.json не найден")
    raise
except json.JSONDecodeError:
    logger.error("Файл config.json содержит невалидный JSON")
    raise

required_keys = ['TWITCH_CLIENT_ID', 'TWITCH_CLIENT_SECRET', 'TELEGRAM_TOKEN', 'CHANNEL_ID', 'STREAMER']
missing_keys = [key for key in required_keys if key not in config]
if missing_keys:
    logger.error(f"Отсутствуют ключи в config.json: {', '.join(missing_keys)}")
    raise KeyError(f"Отсутствуют ключи: {', '.join(missing_keys)}")

TWITCH_CLIENT_ID = config['TWITCH_CLIENT_ID']
TWITCH_CLIENT_SECRET = config['TWITCH_CLIENT_SECRET']
TELEGRAM_TOKEN = config['TELEGRAM_TOKEN']
CHANNEL_ID = config['CHANNEL_ID']
STREAMER = config['STREAMER']
DISPLAY_NAME = config.get('DISPLAY_NAME', STREAMER)  # Псевдоним для отображения
ALWAYS_SHOW_HOURS = config.get('ALWAYS_SHOW_HOURS', False)  # Всегда показывать часы
SOCIAL_LINKS = config.get('SOCIAL_LINKS', {})  # Соцсети
START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Глобальные переменные
message_id = None
is_streaming = False
last_message_text = None
last_stream_data = None

async def get_twitch_client():
    try:
        twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
        await twitch.authenticate_app([])
        logger.info("Twitch API аутентификация успешна")
        return twitch
    except Exception as e:
        logger.error(f"Ошибка аутентификации Twitch API: {e}", exc_info=True)
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
        logger.error(f"Ошибка при получении данных стрима для {STREAMER}: {e}", exc_info=True)
        return None

async def send_or_update_message(bot, stream_info, is_ended=False):
    global message_id, last_message_text, last_stream_data
    try:
        # Рассчитываем продолжительность стрима
        now = datetime.now(timezone.utc)
        duration_seconds = int((now - stream_info['started_at']).total_seconds())
        duration_minutes = duration_seconds // 60

        # Кэшируем данные стрима для сравнения
        current_stream_data = {
            'title': stream_info['title'],
            'game_name': stream_info['game_name'],
            'viewer_count': stream_info['viewer_count'],
            'thumbnail_url': stream_info['thumbnail_url'],
            'started_at': stream_info['started_at'],  # Сохраняем started_at
            'duration_minutes': duration_minutes  # Для обновления продолжительности
        }
        
        if not is_ended:
            # Проверяем, нужно ли обновить данные
            update_needed = last_stream_data is None or current_stream_data != last_stream_data
            if not update_needed:
                logger.debug(f"Данные для {STREAMER} не изменились, пропускаем обновление")
                return
            if last_stream_data:
                changes = {k: v for k, v in current_stream_data.items() if last_stream_data.get(k) != v}
                logger.info(f"Обнаружены изменения для {STREAMER}: {changes}")

        # Формируем текст сообщения
        if is_ended:
            message_text = (
                f"*{escape_markdown_v2(DISPLAY_NAME)}*\n"
                f"*🎬* {escape_markdown_v2(stream_info['title'])}*\n\n"
                f"*Игра*: {escape_markdown_v2(stream_info['game_name'])}*\n"
                f"*Продолжительность*: {escape_markdown_v2(format_duration(duration_seconds, ALWAYS_SHOW_HOURS))}*\n\n"
                f"*Соцсети*:\n"
            )
            for name, url in SOCIAL_LINKS.items():
                message_text += f"[{escape_markdown_v2(name.capitalize())}]({url})\n"
            message_text += f"[Twitch](https://www.twitch.tv/{STREAMER})\n\n"
            message_text += f"*Спасибо за просмотр стрима\\!*"
            reply_markup = None  # Убираем кнопку
        else:
            message_text = (
                f"*{escape_markdown_v2(DISPLAY_NAME)}*\n"
                f"*🎬*: {escape_markdown_v2(stream_info['title'])}*\n\n"
                f"*Игра* {escape_markdown_v2(stream_info['game_name'])}*\n"
                f"*Зрители*: {stream_info['viewer_count']}*\n"
                f"*Продолжительность*: {escape_markdown_v2(format_duration(duration_seconds, ALWAYS_SHOW_HOURS))}*\n\n"
                f"*Соцсети*:\n"
            )
            for name, url in SOCIAL_LINKS.items():
                message_text += f"[{escape_markdown_v2(name.capitalize())}]({url})\n"
            message_text += f"[Twitch](https://www.twitch.tv/{STREAMER})"
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="Смотреть стрим",
                        url=f"https://www.twitch.tv/{STREAMER}"
                    )]
                ]
            )

        logger.debug(f"Отправляемый текст сообщения: {message_text}")

        # Повторные попытки отправки
        for attempt in range(3):
            try:
                if message_id is None:
                    # Отправляем новое сообщение с фото
                    message = await bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=stream_info['thumbnail_url'],
                        caption=message_text,
                        parse_mode='MarkdownV2',
                        reply_markup=reply_markup
                    )
                    message_id = message.message_id
                    logger.info(f"Создано новое сообщение для {STREAMER}: message_id={message_id}")
                    break
                else:
                    # Обновляем существующее сообщение
                    await bot.edit_message_media(
                        chat_id=CHANNEL_ID,
                        message_id=message_id,
                        media=InputMediaPhoto(
                            media=stream_info['thumbnail_url'],
                            caption=message_text,
                            parse_mode='MarkdownV2'
                        ),
                        reply_markup=reply_markup
                    )
                    logger.info(f"Обновлено сообщение для {STREAMER}: message_id={message_id}")
                    break
            except BadRequest as e:
                logger.error(f"Попытка {attempt + 1}: Ошибка парсинга MarkdownV2: {e}. Текст: {message_text}", exc_info=True)
                if "message is not modified" in str(e).lower():
                    logger.debug(f"Сообщение для {STREAMER} не изменилось, пропускаем обновление")
                    return
                if attempt == 2:
                    # Последняя попытка: отправляем без Markdown
                    unescaped_text = message_text.replace('\\', '')
                    if message_id is None:
                        message = await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=stream_info['thumbnail_url'],
                            caption=unescaped_text,
                            reply_markup=reply_markup
                        )
                        message_id = message.message_id
                        logger.info(f"Создано новое сообщение без Markdown для {STREAMER}: message_id={message_id}")
                    else:
                        await bot.edit_message_media(
                            chat_id=CHANNEL_ID,
                            message_id=message_id,
                            media=InputMediaPhoto(
                                media=stream_info['thumbnail_url'],
                                caption=unescaped_text
                            ),
                            reply_markup=reply_markup
                        )
                        logger.info(f"Обновлено сообщение без Markdown для {STREAMER}: message_id={message_id}")
                    break
            except Exception as e:
                logger.error(f"Попытка {attempt + 1}: Ошибка при отправке/обновлении: {e}", exc_info=True)
                if attempt == 2:
                    raise
                await asyncio.sleep(2)  # Задержка перед повторной попыткой

        last_message_text = message_text
        if not is_ended:
            last_stream_data = current_stream_data

    except Exception as e:
        logger.error(f"Ошибка при отправке/обновлении сообщения в Telegram: {e}", exc_info=True)
        if message_id is not None and "message to edit not found" in str(e).lower():
            logger.warning(f"Сообщение не найдено, сбрасываем message_id: {message_id}")
            message_id = None
            last_message_text = None
            last_stream_data = None

async def check_stream():
    global is_streaming, message_id, last_stream_data
    twitch = None
    bot = Bot(token=TELEGRAM_TOKEN)

    while True:
        try:
            if twitch is None:
                twitch = await get_twitch_client()
                if twitch is None:
                    logger.warning("Не удалось инициализировать Twitch клиент, повтор через 60 секунд")
                    await asyncio.sleep(60)
                    continue

            logger.debug("Начало проверки статуса стрима")
            stream_info = await get_stream_info(twitch)
            is_streaming_now = stream_info is not None

            if is_streaming_now and not is_streaming:
                is_streaming = True
                await send_or_update_message(bot, stream_info, is_ended=False)
                logger.info(f"Стрим {STREAMER} начался")
            elif not is_streaming_now and is_streaming:
                is_streaming = False
                if message_id is not None and last_stream_data is not None:
                    # Проверяем наличие всех необходимых ключей
                    required_keys = {'title', 'game_name', 'thumbnail_url', 'started_at', 'viewer_count'}
                    if all(key in last_stream_data for key in required_keys):
                        last_stream_info = {
                            'title': last_stream_data['title'],
                            'game_name': last_stream_data['game_name'],
                            'thumbnail_url': last_stream_data['thumbnail_url'],
                            'started_at': last_stream_data['started_at'],
                            'viewer_count': last_stream_data['viewer_count']
                        }
                        await send_or_update_message(bot, last_stream_info, is_ended=True)
                        logger.info(f"Стрим {STREAMER} закончился, сообщение обновлено")
                    else:
                        logger.warning(f"Недостаточно данных для обновления сообщения: last_stream_data={last_stream_data}")
                else:
                    logger.warning(f"Не удалось обновить сообщение: message_id={message_id}, last_stream_data={last_stream_data}")
                message_id = None
                last_message_text = None
                last_stream_data = None
                logger.info(f"Стрим {STREAMER} закончился, message_id сброшен")
            elif is_streaming_now and is_streaming:
                await send_or_update_message(bot, stream_info, is_ended=False)

        except Exception as e:
            logger.error(f"Ошибка в check_stream: {e}", exc_info=True)
            twitch = None  # Сбрасываем клиент для повторной инициализации

        logger.debug("Ожидание следующей проверки")
        await asyncio.sleep(60)

async def shutdown():
    logger.info(f"Завершение работы бота. Время запуска: {START_TIME}")
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        logger.debug(f"Отмена задачи: {task}")
        task.cancel()
    await asyncio.sleep(0.1)

async def main():
    logger.info(f"Запуск бота. Время: {START_TIME}")
    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    loop.add_signal_handler(signal.SIGTERM, lambda: stop.set_result(None))
    loop.add_signal_handler(signal.SIGINT, lambda: stop.set_result(None))

    loop.create_task(check_stream())

    try:
        await stop
    except Exception as e:
        logger.error(f"Ошибка в main: {e}", exc_info=True)
    finally:
        await shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Фатальная ошибка: {e}", exc_info=True)