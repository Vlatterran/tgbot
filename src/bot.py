import asyncio
import logging
import sys
from os import getenv

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from schedule import Schedule

TOKEN = getenv("BOT_TOKEN")

dispatcher = Dispatcher()

schedule = Schedule.from_json_file('schedule.json')


def answer(msg: types.Message, *args, **kwargs):
    if msg.chat.type == 'private':
        return msg.answer(*args, **kwargs)
    return msg.reply(*args, **kwargs)


@dispatcher.message(Command('пары', 'lectures'))
async def echo_handler(message: types.Message) -> None:
    day = message.text.split()
    if len(day) == 1:
        day = 'сегодня'
    else:
        day = day[-1]
    await answer(message, schedule.lectures(day))


async def main() -> None:
    bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
