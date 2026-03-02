import asyncio
import aiohttp
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
import database

bot = Bot(token=config.BOT_B_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

CRYPTO_BOT_API = "https://pay.crypt.bot/api"

# ─── STATES ───────────────────────────────────────────
class UserFunnel(StatesGroup):
    waiting_gg_username   = State()
    waiting_custom_amount = State()

# ─── KEYBOARDS ────────────────────────────────────────
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Deposit",  callback_data="deposit")
    kb.button(text="💸 Withdraw", callback_data="withdraw")
    kb.button(text="📊 Balance",  callback_data="balance")
    kb.button(text="ℹ️ Help",     callback_data="help")
    kb.adjust(2)
    return kb.as_markup()

# ─── HELPERS ──────────────────────────────────────────
async def ensure_registered(user_id: int) -> bool:
    return await database.get_user(user_id) is not None

DAYS = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
}

async def check_allowed(op: str) -> tuple[bool, str]:
    # 1. emergency block
    blocked = await database.get_setting(f"{op}_blocked")
    if blocked == "true":
        msg = await database.get_setting(f"{op}_blocked_msg") or ""
        label = "Deposits" if op == "deposit" else "Withdrawals"
        return False, f"🔴 *{label} are temporarily disabled*\n\n{msg}"

    # 2. allowed days
    raw = await database.get_setting(f"{op}_days")
    allowed_days = json.loads(raw) if raw else []

    if -1 in allowed_days:
        return True, ""

    if not allowed_days:
        label = "Deposits" if op == "deposit" else "Withdrawals"
        return False, f"⚠️ {label} are not available at the moment.\nPlease contact support for details."

    today = datetime.utcnow().weekday()
    if today in allowed_days:
        return True, ""

    next_day_name = min([((d - today) % 7, DAYS[d]) for d in allowed_days])[1]
    allowed_names = ", ".join(DAYS[d] for d in sorted(allowed_days))
    label_pl = "deposits" if op == "deposit" else "withdrawals"
    label_sg = "deposit"  if op == "deposit" else "withdrawal"
    return False, (
        f"⏰ *{label_pl.capitalize()} are only available on:* {allowed_names}\n\n"
        f"Next {label_sg} day: *{next_day_name}*\n"
        f"Please come back then."
    )

# ─── CRYPTOBOT: CREATE INVOICE ────────────────────────
async def create_invoice(amount: float, telegram_id: int, tx_id: int) -> dict:
    async with aiohttp.ClientSession() as session:
        headers = {"Crypto-Pay-API-Token": config.CRYPTO_BOT_TOKEN}
        payload = {
            "asset":           "USDT",
            "amount":          str(amount),
            "description":     "KingsRiver Poker Club — Deposit",
            "payload":         f"{telegram_id}:{tx_id}",
            "allow_comments":  False,
            "allow_anonymous": False,
            "expires_in":      3600,
        }
        async with session.post(
            f"{CRYPTO_BOT_API}/createInvoice",
            json=payload, headers=headers
        ) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]
            raise Exception(f"CryptoBot error: {data}")

# ─── /START ───────────────────────────────────────────
@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext):
    await state.clear()
    user = await database.get_user(msg.from_user.id)
    if user:
        await msg.answer(
            f"🃏 Welcome back, *{user['gg_username']}*!\n\nWhat would you like to do?",
            reply_markup=main_menu(), parse_mode="Markdown"
        )
    else:
        await msg.answer(
            "🃏 Welcome to *KingsRiver Poker Club*!\n\n"
            "To get started, please send us your *GG Poker Club username or ID*:",
            parse_mode="Markdown"
        )
        await state.set_state(UserFunnel.waiting_gg_username)

# ─── REGISTRATION ─────────────────────────────────────
@dp.message(UserFunnel.waiting_gg_username)
async def collect_gg_username(msg: types.Message, state: FSMContext):
    gg_username = msg.text.strip()
    await database.register_user(msg.from_user.id, gg_username)
    await state.clear()
    await msg.answer(
        f"✅ Registration complete!\n\n"
        f"👤 GG Username: *{gg_username}*\n"
        f"🎰 Club: *KingsRiver Poker Club*\n\n"
        f"What would you like to do?",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f"🆕 New user registered!\n"
        f"👤 GG Username: *{gg_username}*\n"
        f"🆔 Telegram ID: `{msg.from_user.id}`",
        parse_mode="Markdown"
    )

# ─── BALANCE ──────────────────────────────────────────
@dp.callback_query(F.data == "balance")
async def show_balance(call: types.CallbackQuery):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ You are not registered. Send /start to begin.")
        await call.answer(); return
    balance = await database.get_balance(call.from_user.id)
    await call.message.answer(
        f"📊 Your current balance: *{balance:.2f} USDT*",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await call.answer()

# ─── DEPOSIT ──────────────────────────────────────────
@dp.callback_query(F.data == "deposit")
async def deposit_flow(call: types.CallbackQuery, state: FSMContext):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ You are not registered. Send /start to begin.")
        await call.answer(); return

    allowed, msg_text = await check_allowed("deposit")
    if not allowed:
        await call.message.answer(msg_text, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer(); return

    kb = InlineKeyboardBuilder()
    for amt in [5, 10, 25, 50, 100]:
        kb.button(text=f"{amt} USDT", callback_data=f"dep_{amt}")
    kb.button(text="✏️ Custom amount", callback_data="dep_custom")
    kb.button(text="❌ Cancel",        callback_data="cancel")
    kb.adjust(3, 3, 1)

    await call.message.answer(
        "💰 *KingsRiver Poker Club — Deposit*\n\n"
        "Select the amount you wish to deposit:\n"
        "_(Payment is processed automatically via CryptoBot — USDT)_",
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("dep_"))
async def handle_deposit_amount(call: types.CallbackQuery, state: FSMContext):
    value = call.data[4:]
    if value == "custom":
        await call.message.answer("✏️ Enter the amount in USDT (e.g. 30 or 75.5):")
        await state.set_state(UserFunnel.waiting_custom_amount)
        await state.update_data(mode="deposit")
        await call.answer(); return
    await call.answer()
    await generate_invoice(call.message, call.from_user.id, float(value))

# ─── CUSTOM AMOUNT INPUT ──────────────────────────────
@dp.message(UserFunnel.waiting_custom_amount)
async def process_custom_amount(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "deposit")
    try:
        amount = float(msg.text.strip().replace(",", "."))
        if amount <= 0:
            await msg.answer("⚠️ Amount must be greater than 0.")
            return
        await state.clear()
        if mode == "deposit":
            await generate_invoice(msg, msg.from_user.id, amount)
        else:
            await process_withdrawal(msg, amount)
    except ValueError:
        await msg.answer("⚠️ Please enter a valid amount (e.g. 50 or 50.5)")

# ─── GENERATE CRYPTOBOT INVOICE ───────────────────────
async def generate_invoice(msg, telegram_id: int, amount: float):
    try:
        tx_id   = await database.create_transaction(telegram_id, "deposit", amount, "pending")
        invoice = await create_invoice(amount, telegram_id, tx_id)
        pay_url    = invoice["pay_url"]
        invoice_id = invoice["invoice_id"]
        await database.update_transaction_invoice(tx_id, str(invoice_id))

        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Pay {amount:.2f} USDT", url=pay_url)
        kb.button(text="❌ Cancel", callback_data="cancel")
        kb.adjust(1)

        await msg.answer(
            f"💰 *Invoice generated!*\n\n"
            f"Amount: *{amount:.2f} USDT*\n"
            f"Valid for: *1 hour*\n\n"
            f"Press the button below to pay via CryptoBot.\n"
            f"✅ Your balance will be updated *automatically* after confirmation!",
            reply_markup=kb.as_markup(), parse_mode="Markdown"
        )
        await bot.send_message(
            config.ADMIN_CHAT_ID,
            f"💰 *Deposit invoice created*\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"💵 Amount: *{amount:.2f} USDT*\n"
            f"🔖 TX ID: `{tx_id}` | Invoice: `{invoice_id}`\n"
            f"_Balance updates automatically on payment._",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer("⚠️ Error generating invoice. Please try again or contact support.")
        print(f"CryptoBot invoice error: {e}")

# ─── WITHDRAW ─────────────────────────────────────────
@dp.callback_query(F.data == "withdraw")
async def withdraw_flow(call: types.CallbackQuery, state: FSMContext):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ You are not registered. Send /start to begin.")
        await call.answer(); return

    allowed, msg_text = await check_allowed("withdraw")
    if not allowed:
        await call.message.answer(msg_text, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer(); return

    balance = await database.get_balance(call.from_user.id)
    await call.message.answer(
        f"💸 *KingsRiver Poker Club — Withdrawal*\n\n"
        f"Your current balance: *{balance:.2f} USDT*\n\n"
        f"Enter the amount you wish to withdraw:",
        parse_mode="Markdown"
    )
    await state.set_state(UserFunnel.waiting_custom_amount)
    await state.update_data(mode="withdraw")
    await call.answer()

# ─── PROCESS WITHDRAWAL ───────────────────────────────
async def process_withdrawal(msg, amount: float):
    balance = await database.get_balance(msg.from_user.id)
    if amount > balance:
        await msg.answer(
            f"⚠️ Insufficient balance!\nYour current balance: *{balance:.2f} USDT*",
            parse_mode="Markdown"
        )
        return

    user    = await database.get_user(msg.from_user.id)
    gg_name = user['gg_username'] if user else str(msg.from_user.id)
    tx_id   = await database.create_transaction(msg.from_user.id, "withdraw", amount)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"approve_withdraw_{msg.from_user.id}_{amount}_{tx_id}")
    kb.button(text="❌ Reject",  callback_data=f"reject_withdraw_{msg.from_user.id}_{tx_id}")

    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f"💸 *New withdrawal request!*\n\n"
        f"👤 GG Username: *{gg_name}*\n"
        f"🆔 Telegram ID: `{msg.from_user.id}`\n"
        f"💰 Amount: *{amount:.2f} USDT*\n"
        f"🔖 TX ID: `{tx_id}`",
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await msg.answer(
        f"✅ Your withdrawal request of *{amount:.2f} USDT* has been submitted.\n"
        f"You will be notified once it is approved.",
        reply_markup=main_menu(), parse_mode="Markdown"
    )

# ─── ADMIN: APPROVE / REJECT ──────────────────────────
@dp.callback_query(F.data.startswith("approve_withdraw_"))
async def approve_withdraw(call: types.CallbackQuery):
    parts   = call.data.split("_")
    user_id = int(parts[2])
    amount  = float(parts[3])
    tx_id   = int(parts[4])
    await database.update_balance(user_id, -amount)
    await database.update_transaction_status(tx_id, "completed")
    await call.message.edit_text(call.message.text + "\n\n✅ *APPROVED by admin*", parse_mode="Markdown")
    await bot.send_message(
        user_id,
        f"✅ Your withdrawal of *{amount:.2f} USDT* has been approved!\n"
        f"Funds have been sent to your wallet.",
        parse_mode="Markdown"
    )
    await call.answer("Withdrawal approved!")

@dp.callback_query(F.data.startswith("reject_withdraw_"))
async def reject_withdraw(call: types.CallbackQuery):
    parts   = call.data.split("_")
    user_id = int(parts[2])
    tx_id   = int(parts[3])
    await database.update_transaction_status(tx_id, "rejected")
    await call.message.edit_text(call.message.text + "\n\n❌ *REJECTED by admin*", parse_mode="Markdown")
    await bot.send_message(
        user_id,
        "❌ Your withdrawal request has been rejected.\nPlease contact support for details."
    )
    await call.answer("Withdrawal rejected!")

# ─── CANCEL ───────────────────────────────────────────
@dp.callback_query(F.data == "cancel")
async def cancel_action(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Action cancelled.", reply_markup=main_menu())
    await call.answer()

# ─── HELP ─────────────────────────────────────────────
@dp.callback_query(F.data == "help")
async def help_section(call: types.CallbackQuery):
    await call.message.answer(
        "ℹ️ *KingsRiver Poker Club — Help*\n\n"
        "• 💰 Deposit: Automatic payment via CryptoBot (USDT)\n"
        "• 💸 Withdraw: Request a withdrawal\n"
        "• 📊 Balance: Check your current balance\n\n"
        "📞 Support: @KingsRiverSupport",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await call.answer()

# ─── START BOT ────────────────────────────────────────
async def main():
    await database.init_db()
    print("Bot B (Operations) started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
