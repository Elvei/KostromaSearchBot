
import os
import asyncio
import re
from itertools import count
from collections import defaultdict

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Избранное и ожидающие решения ссылки хранятся в памяти
favorites = defaultdict(list)
pending = {}
profile_ids = count(1)


@dp.message(CommandStart())
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔎 Найти анкеты",
            url="https://vk.com/search?c%5Bsection%5D=people"
        )],
        [InlineKeyboardButton(
            text="❤️ Моё избранное",
            callback_data="show_favorites"
        )],
        [InlineKeyboardButton(
            text="⚙️ Настройки поиска",
            callback_data="settings"
        )]
    ])

    await message.answer(
        "Привет! Это помощник для поиска публичных профилей ВКонтакте.\n\n"
        "Город: Кострома\n"
        "Возраст: 18 лет\n"
        "Пол: женский\n\n"
        "Найди профиль в ВК, скопируй ссылку и отправь её мне. "
        "Я предложу сохранить её или пропустить.",
        reply_markup=keyboard
    )


@dp.message(Command("favorites"))
async def show_favorites_command(message: Message):
    await send_favorites(message, message.from_user.id)


async def send_favorites(message, user_id):
    user_favorites = favorites[user_id]

    if not user_favorites:
        await message.answer("В избранном пока ничего нет ❤️")
        return

    text = "❤️ Твоё избранное:\n\n"
    text += "\n".join(
        f"{i}. {link}" for i, link in enumerate(user_favorites, 1)
    )
    await message.answer(text)


@dp.callback_query(F.data == "show_favorites")
async def show_favorites_callback(callback: CallbackQuery):
    await callback.answer()
    await send_favorites(callback.message, callback.from_user.id)


@dp.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Настройки поиска:\n"
        "Город: Кострома\n"
        "Возраст: 18 лет\n"
        "Пол: женский\n\n"
        "Фильтры можно уточнить на сайте ВКонтакте."
    )


@dp.message(F.text)
async def receive_profile_link(message: Message):
    match = re.search(
        r"https?://(?:www\.|m\.)?(?:vk\.com|vk\.ru)/[^\s]+",
        message.text
    )

    if not match:
        await message.answer(
            "Отправь мне ссылку на публичный профиль ВКонтакте, "
            "например https://vk.com/id123456"
        )
        return

    link = match.group(0).rstrip(".,!?)]}")
    profile_id = next(profile_ids)

    pending[profile_id] = (message.from_user.id, link)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❤️ В избранное",
                callback_data=f"save:{profile_id}"
            ),
            InlineKeyboardButton(
                text="⏭ Пропустить",
                callback_data=f"skip:{profile_id}"
            )
        ]
    ])

    await message.answer(
        f"Профиль:\n{link}\n\nСохранить его или пропустить?",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@dp.callback_query(F.data.startswith("save:"))
async def save_profile(callback: CallbackQuery):
    profile_id = int(callback.data.split(":")[1])
    item = pending.get(profile_id)

    if not item or item[0] != callback.from_user.id:
        await callback.answer("Эта ссылка уже обработана.", show_alert=True)
        return

    user_id, link = pending.pop(profile_id)

    if link not in favorites[user_id]:
        favorites[user_id].append(link)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Сохранено в избранное ❤️")


@dp.callback_query(F.data.startswith("skip:"))
async def skip_profile(callback: CallbackQuery):
    profile_id = int(callback.data.split(":")[1])
    item = pending.get(profile_id)

    if not item or item[0] != callback.from_user.id:
        await callback.answer("Эта ссылка уже обработана.", show_alert=True)
        return

    pending.pop(profile_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Профиль пропущен")


async def main():
    app = web.Application()

    async def health(request):
        return web.Response(text="Bot is running")

    async def webhook(request):
        secret = os.environ["WEBHOOK_SECRET"]

        if request.match_info["secret"] != secret:
            raise web.HTTPForbidden()

        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)

        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_post("/webhook/{secret}", webhook)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        int(os.environ.get("PORT", 10000))
    )
    await site.start()

    public_url = os.environ["PUBLIC_URL"].rstrip("/")
    secret = os.environ["WEBHOOK_SECRET"]

    await bot.set_webhook(f"{public_url}/webhook/{secret}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
