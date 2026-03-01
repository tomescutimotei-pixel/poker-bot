import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER
import config

bot = Bot(token=config.BOT_A_TOKEN)
dp = Dispatcher()

@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def new_member_joined(event: types.ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return

    welcome_text = (
        f"🃏 Welcome to *KingsRiver Poker Club*, {user.full_name}!\n\n"
        f"To access the club, make deposits and withdrawals,\n"
        f"please open a private chat with our bot:\n\n"
        f"👉 {config.OPERATIONS_BOT_USERNAME}\n\n"
        f"Press /start there to begin registration."
    )

    await bot.send_message(
        chat_id=event.chat.id,
        text=welcome_text,
        parse_mode="Markdown"
    )

async def main():
    print("Bot A (Channel Monitor) started...")
    await dp.start_polling(
        bot,
        allowed_updates=["chat_member", "message", "callback_query"]
    )

if __name__ == "__main__":
    asyncio.run(main())
