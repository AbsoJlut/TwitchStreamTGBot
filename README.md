# 🎮 Twitch Stream Telegram Bot

Бот для Telegram, который автоматически отслеживает стрим на Twitch и публикует информацию о нём в канал, а также добавляет интерактивные функции для чата.

---

## 🚀 Возможности

### 📡 Twitch интеграция

* Автоматически отслеживает, когда стример выходит в эфир
* Публикует сообщение в Telegram-канал
* Обновляет:

  * название стрима
  * категорию
  * количество зрителей
  * длительность стрима
* Меняет сообщение при завершении стрима
* Опционально удаляет сообщение после окончания стрима

---

### 🖼 Кастомизация

* Подмена превью для IRL-стримов
* Настраиваемые кнопки:

  * Twitch
  * Донаты
  * Соцсети

---

### 🤖 Telegram функции

#### 📥 Приветствие пользователей

* Красивое сообщение при входе в чат
* Inline-кнопки:

  * правила
  * ссылки
* Deep-link переход в личку бота

#### 📤 Прощание

* Разные сообщения при выходе пользователя
* Без повторов (shuffle-логика)

---

### 🎲 Fun-команды

* `!кубик` — бросок кубика (D4, D6, D10, D20, D100)
* `!обнять` — обнимашки 🤗
* `!лю` — измеритель любви 💘
* `!атака` — атака пользователя ⚔️
* `!отмена` — отменить действие

---

### 🐳 Docker поддержка

Проект полностью готов к запуску через Docker:

```bash
docker-compose up -d
```

---

## ⚙️ Установка

### 1. Клонирование

```bash
git clone https://github.com/AbsoJlut/TwitchStreamTGBot.git
cd TwitchStreamTGBot
```

---

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

или через Docker (рекомендуется)

---

### 3. Создание конфига

Создай файл:

```bash
config.json
```

---

## 🧩 Пример config.json

```json
{
  "TWITCH_CLIENT_ID": "your_client_id",
  "TWITCH_CLIENT_SECRET": "your_client_secret",
  "TELEGRAM_TOKEN": "your_telegram_bot_token",

  "CHANNEL_ID": "@your_channel",
  "DLC_GROUP_ID": -1001234567890,

  "STREAMER": "twitch_username",

  "ALWAYS_SHOW_HOURS": false,

  "DELETE_STREAM_MESSAGE_AFTER_END": true,
  "DELETE_STREAM_MESSAGE_DELAY_SECONDS": 3600,

  "IRL_IMAGE_URL": "https://example.com/image.jpg",
  "IRL_CATEGORIES": ["IRL"],

  "SOCIAL_LINKS": {
    "Boosty": "https://boosty.to/your",
    "Discord": "https://discord.gg/your"
  },

  "STREAM_LINKS": {
    "DonationAlerts": "https://donate.link",
    "Boosty": "https://boosty.to/your"
  },

  "LINKS_COMMAND": {
    "Twitch": "https://twitch.tv/your",
    "Telegram": "https://t.me/your"
  },

  "DLC_RULES": [
    "Правило 1",
    "Правило 2"
  ]
}
```

---

## ▶️ Запуск

### Обычный запуск

```bash
python twitch_stream_bot.py
```

---

### Через Docker

```bash
docker-compose up -d
```

---

## 🧠 Как это работает

* Бот опрашивает Twitch API каждые 60 секунд
* При старте стрима:

  * создаёт сообщение
* Во время стрима:

  * обновляет данные
* После окончания:

  * меняет сообщение
  * (опционально) удаляет его

---

## 📌 Стек технологий

* Python 3.10+
* python-telegram-bot
* twitchAPI
* aiohttp
* Docker

---

## ❤️ Автор

Разработка и поддержка: **AbsoJlut**

---

## ⭐ Поддержка проекта

Если тебе понравился бот — поставь ⭐ на GitHub и поддержи разработку!

---
