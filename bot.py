
import os
import asyncio
import re
from itertools import count

import aiohttp
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
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Ожидающие решения ссылки пока хранятся в памяти
pending = {}
profile_ids = count(1)


async def supabase_request(method, path, *, params=None, json=None, headers=None):
    request_headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update(headers)

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method,
            f"{SUPABASE_URL}/rest/v1/{path}",
            params=params,
            json=json,
            headers=request_headers,
        ) as response:
            if response.status >= 400:
                error = await response.text()
                raise RuntimeError(
                    f"Supabase error {response.status}: {error}"
                )

            if response.status == 204 or response.content_length == 0:
                return None

            return await response.json()


async def add_favorite(user_id, link):
    await supabase_request(
        "POST",
        "favorites",
        json={
            "user_id": user_id,
            "profile_url": link,
        },
        headers={
            "Prefer": "resolution=ignore-duplicates,return=minimal"
        },
    )


async def get_favorites(user_id):
    return await supabase_request(
        "GET",
        "favorites",
        params={
            "user_id": f"eq.{user_id}",
            "select": "profile_url",
            "order": "created_at.desc",
        },
    )


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
    try:
        rows = await get_favorites(user_id)
    except Exception:
        await message.answer(
            "Не удалось загрузить избранное. Попробуй ещё раз позже."
        )
        return

    if not rows:
        await message.answer("В избранном пока ничего нет ❤️")
        return

    text = "❤️ Твоё избранное:\n\n"
    text += "\n".join(
        f"{i}. {row['profile_url']}"
        for i, row in enumerate(rows, 1)
    )
    await message.answer(text, disable_web_page_preview=True)


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
        await callback.answer(
            "Эта ссылка уже обработана.",
            show_alert=True
        )
        return

    user_id, link = item

    try:
        await add_favorite(user_id, link)
    except Exception:
        await callback.answer(
            "Не удалось сохранить. Попробуй ещё раз.",
            show_alert=True
        )
        return

    pending.pop(profile_id, None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Сохранено в избранное ❤️")


@dp.callback_query(F.data.startswith("skip:"))
async def skip_profile(callback: CallbackQuery):
    profile_id = int(callback.data.split(":")[1])
    item = pending.get(profile_id)

    if not item or item[0] != callback.from_user.id:
        await callback.answer(
            "Эта ссылка уже обработана.",
            show_alert=True
        )
        return

    pending.pop(profile_id, None)
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

