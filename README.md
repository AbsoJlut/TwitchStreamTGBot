# 🎮 Twitch Stream Bot

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)](https://www.docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Issues](https://img.shields.io/github/issues/AbsoJlut/twitch-stream-bot)](https://github.com/AbsoJlut/twitch-stream-bot/issues)

**Twitch Stream Bot** — это Telegram-бот, который следит за статусом стримов на Twitch и отправляет уведомления в Telegram-канал о начале, продолжении и завершении трансляций. Бот использует Twitch API, поддерживает форматирование сообщений с MarkdownV2, добавляет интерактивные кнопки и работает в Docker-контейнере для простого развертывания. 🚀

---

## ✨ Основные возможности

- 📡 **Отслеживание стримов**: Проверяет статус трансляций на Twitch через Twitch API.
- 🔔 **Уведомления в Telegram**: Отправляет сообщения о начале, обновлении и завершении стримов.
- 📝 **Красивые сообщения**: Форматирование с MarkdownV2, включая название стрима, игру, зрителей и продолжительность.
- 🇷🇺 **Русская локализация**: Корректное отображение времени и дат.
- 📜 **Логирование**: Все события записываются в `log.txt` и консоль для удобной отладки.
- 🐳 **Docker**: Легкое развертывание с помощью Docker и Docker Compose.

---

## 🛠 Требования

- **Python**: 3.11 или выше
- **Docker**: Docker и Docker Compose (для контейнеризации)
- **Twitch API**: Client ID и Client Secret ([Twitch Developer Console](https://dev.twitch.tv/console))
- **Telegram API**: Токен бота от [BotFather](https://t.me/BotFather)
- **Telegram-канал**: ID канала для отправки уведомлений

---

## 📦 Установка и запуск

### 1. Клонируйте репозиторий
```bash
git clone https://github.com/AbsoJlut/TwitchStreamTGBot.git
cd TwitchStreamTGBot
```

### 2. Настройте конфигурацию
Переименуйте `config.json.example` в `config.json` и заполните поля:
```json
{
  "TWITCH_CLIENT_ID": "your_twitch_client_id",
  "TWITCH_CLIENT_SECRET": "your_twitch_client_secret",
  "TELEGRAM_TOKEN": "your_telegram_bot_token",
  "CHANNEL_ID": "@YourChannelOrID",
  "STREAMER": "streamer_username",
  "ALWAYS_SHOW_HOURS": true,
  "SOCIAL_LINKS": {
    "Boosty": "link",
    "Discord": "link"
  }
}
```
- **twitch_client_id/secret**: Получите в [Twitch Developer Console](https://dev.twitch.tv/console).
- **streamer_name**: Имя стримера (например, `shroud`).
- **telegram_bot_token**: Токен от BotFather.
- **telegram_channel_id**: ID канала (например, `@MyChannel` или `-1001234567890`).
- **ALWAYS_SHOW_HOURS**: Показывать часы в длительности (`true`/`false`).

### 3. Установите зависимости (без Docker)
Если вы не используете Docker:
```bash
pip install -r requirements.txt
```

### 4. Запустите с Docker
Для запуска в контейнере:
```bash
docker-compose up -d
```
Бот начнет работать, а логи будут записываться в `log.txt`.

### 5. Перезапуск бота после изменений
Для перезапуска используйте:
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

---

## 📂 Структура проекта

```
twitch-stream-bot/
├── twitch_stream_bot.py    # Основной скрипт бота
├── config.json             # Конфигурация (токены, настройки)
├── docker-compose.yml      # Настройки Docker Compose
├── Dockerfile              # Описание Docker-образа
├── requirements.txt        # Зависимости Python
├── log.txt                # Логи работы бота
└── README.md              # Документация
```

---

## 📋 Логирование

- Логи записываются в `log.txt` и выводятся в консоль.
- Формат: `[УРОВЕНЬ] ДАТА ВРЕМЯ - СООБЩЕНИЕ`.

Для отладки проверяйте `log.txt`.

---

## 🛠 Устранение неполадок

1. **Ошибка MarkdownV2 (`Can't parse entities`)**:
   - **Причина**: Специальные символы (`!`, `#`, `|`) в заголовке стрима.
   - **Решение**: Проверьте заголовок стрима или обновите функцию `escape_markdown_v2`.

2. **Ошибка `KeyError: 'started_at'`**:
   - **Причина**: Данные стрима не содержат ожидаемых ключей.
   - **Решение**: Перезапустите бот или проверьте `streamer_name`.

3. **Ошибка `Invalid message_id`**:
   - **Причина**: Сообщение в Telegram удалено.
   - **Решение**: Бот автоматически отправит новое сообщение.

4. **Ошибка `Invalid JSON in config.json`**:
   - **Причина**: Некорректный формат `config.json`.
   - **Решение**: Проверьте синтаксис JSON (используйте онлайн-валидаторы).

---

## 📜 Лицензия

Проект распространяется под [MIT License](LICENSE). Вы можете использовать, изменять и распространять код, соблюдая условия лицензии.

---

## 📬 Контакты

Если у вас есть вопросы, предложения или баги:
- ✍️ Создайте [Issue](https://github.com/AbsoJlut/twitch-stream-bot/issues).
- 👤 Автор: [AbsoJlut](https://github.com/AbsoJlut).
