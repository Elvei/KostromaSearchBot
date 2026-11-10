
import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔎 Найти анкеты",
            url="https://vk.com/search?c%5Bsection%5D=people"
        )],
        [InlineKeyboardButton(
            text="⚙️ Настройки поиска",
            callback_data="settings"
        )]
    ])

    await message.answer(
        "Привет! Это поиск публичных анкет ВКонтакте.\n\n"
        "Город: Кострома\n"
        "Возраст: 18 лет\n"
        "Пол: женский\n\n"
        "Нажми кнопку ниже, чтобы открыть поиск ВКонтакте.",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "settings")
async def settings(callback):
    await callback.answer()
    await callback.message.answer(
        "Настройки поиска:\n"
        "Город: Кострома\n"
        "Возраст: 18 лет\n"
        "Пол: женский\n\n"
        "Фильтры при необходимости можно уточнить на сайте ВКонтакте."
    )

async def main():
    app = web.Application()

    async def health(request):
        return web.Response(text="Bot is running")

    app.router.add_get("/", health)

    async def webhook(request):
        secret = os.environ["WEBHOOK_SECRET"]
        if request.match_info["secret"] != secret:
            raise web.HTTPForbidden()
        from aiogram.types import Update
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")

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

    await bot.set_webhook(
        f"{public_url}/webhook/{secret}"
    )

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
