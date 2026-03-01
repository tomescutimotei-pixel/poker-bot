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
    waiting_gg_username  = State()
    waiting_custom_amount = State()

# ─── KEYBOARDS ────────────────────────────────────────
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Depunere",   callback_data="deposit")
    kb.button(text="💸 Retragere",  callback_data="withdraw")
    kb.button(text="📊 Sold curent",callback_data="balance")
    kb.button(text="ℹ️ Ajutor",     callback_data="help")
    kb.adjust(2)
    return kb.as_markup()

# ─── HELPERS ──────────────────────────────────────────
async def ensure_registered(user_id: int) -> bool:
    return await database.get_user(user_id) is not None

ZILE_RO = {
    0: "Luni", 1: "Marți", 2: "Miercuri",
    3: "Joi",  4: "Vineri", 5: "Sâmbătă", 6: "Duminică"
}

async def check_allowed(op: str) -> tuple[bool, str]:
    """
    Verifică dacă operațiunea 'deposit' sau 'withdraw' e permisă azi (UTC).
    Returnează (True, "") dacă e ok, sau (False, "mesaj pentru user") dacă nu.
    """
    # 1. blocare urgentă
    blocked = await database.get_setting(f"{op}_blocked")
    if blocked == "true":
        msg = await database.get_setting(f"{op}_blocked_msg") or ""
        label = "Depunerile" if op == "deposit" else "Retragerile"
        return False, f"🔴 *{label} sunt dezactivate temporar*\n\n{msg}"

    # 2. zile permise
    raw = await database.get_setting(f"{op}_days")
    allowed_days = json.loads(raw) if raw else []

    if -1 in allowed_days:          # always open
        return True, ""

    if not allowed_days:
        label = "Depunerile" if op == "deposit" else "Retragerile"
        return False, f"⚠️ {label} nu sunt disponibile momentan.\nContactează suportul pentru detalii."

    today = datetime.utcnow().weekday()   # 0 = Luni … 6 = Duminică  (UTC)
    if today in allowed_days:
        return True, ""

    # găsim următoarea zi permisă
    next_day_name = min(
        [(( d - today) % 7, ZILE_RO[d]) for d in allowed_days]
    )[1]
    allowed_names = ", ".join(ZILE_RO[d] for d in sorted(allowed_days))
    label_pl = "depunerile" if op == "deposit" else "retragerile"
    label_sg = "depunere"   if op == "deposit" else "retragere"
    return False, (
        f"⏰ *Zilele permise pentru {label_pl}:* {allowed_names}\n\n"
        f"Următoarea zi de {label_sg}: *{next_day_name}*\n"
        f"Te rugăm să revii atunci."
    )

# ─── CRYPTOBOT ────────────────────────────────────────
async def create_invoice(amount: float, telegram_id: int, tx_id: int) -> dict:
    async with aiohttp.ClientSession() as session:
        headers = {"Crypto-Pay-API-Token": config.CRYPTO_BOT_TOKEN}
        payload = {
            "asset":           "USDT",
            "amount":          str(amount),
            "description":     "Depunere KingsRiver Poker Club",
            "payload":         f"{telegram_id}:{tx_id}",
            "allow_comments":  False,
            "allow_anonymous": False,
            "expires_in":      3600,
        }
        async with session.post(f"{CRYPTO_BOT_API}/createInvoice", json=payload, headers=headers) as resp:
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
            f"🃏 Bun venit înapoi, *{user['gg_username']}*!\n\nCe dorești să faci?",
            reply_markup=main_menu(), parse_mode="Markdown"
        )
    else:
        await msg.answer(
            "🃏 Bun venit la *KingsRiver Poker Club*!\n\n"
            "Pentru a continua, trimite-ne *username-ul sau ID-ul tău din GG Poker Club*:",
            parse_mode="Markdown"
        )
        await state.set_state(UserFunnel.waiting_gg_username)

# ─── ÎNREGISTRARE ─────────────────────────────────────
@dp.message(UserFunnel.waiting_gg_username)
async def collect_gg_username(msg: types.Message, state: FSMContext):
    gg_username = msg.text.strip()
    await database.register_user(msg.from_user.id, gg_username)
    await state.clear()
    await msg.answer(
        f"✅ Înregistrare completă!\n\n"
        f"👤 GG Username: *{gg_username}*\n"
        f"🎰 Club: *KingsRiver Poker Club*\n\n"
        f"Ce dorești să faci?",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f"🆕 Utilizator nou înregistrat!\n"
        f"👤 GG Username: *{gg_username}*\n"
        f"🆔 Telegram ID: `{msg.from_user.id}`",
        parse_mode="Markdown"
    )

# ─── SOLD ─────────────────────────────────────────────
@dp.callback_query(F.data == "balance")
async def show_balance(call: types.CallbackQuery):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer(); return
    balance = await database.get_balance(call.from_user.id)
    await call.message.answer(
        f"📊 Soldul tău curent: *{balance:.2f} USDT*",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await call.answer()

# ─── DEPUNERE ─────────────────────────────────────────
@dp.callback_query(F.data == "deposit")
async def deposit_flow(call: types.CallbackQuery):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer(); return

    allowed, msg_text = await check_allowed("deposit")
    if not allowed:
        await call.message.answer(msg_text, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer(); return

    kb = InlineKeyboardBuilder()
    for amt in [5, 10, 25, 50, 100]:
        kb.button(text=f"{amt} USDT", callback_data=f"dep_{amt}")
    kb.button(text="✏️ Altă sumă", callback_data="dep_custom")
    kb.button(text="❌ Anulează",  callback_data="cancel")
    kb.adjust(3, 3, 1)

    await call.message.answer(
        "💰 *Depunere KingsRiver Poker Club*\n\n"
        "Selectează suma:\n_(Plata automată prin CryptoBot — USDT)_",
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("dep_"))
async def handle_deposit_amount(call: types.CallbackQuery, state: FSMContext):
    value = call.data[4:]   # strip "dep_"
    if value == "custom":
        await call.message.answer("✏️ Introdu suma dorită în USDT (ex: 30 sau 75.5):")
        await state.set_state(UserFunnel.waiting_custom_amount)
        await state.update_data(mode="deposit")
        await call.answer(); return
    await call.answer()
    await generate_invoice(call.message, call.from_user.id, float(value))

# ─── RETRAGERE ────────────────────────────────────────
@dp.callback_query(F.data == "withdraw")
async def withdraw_flow(call: types.CallbackQuery, state: FSMContext):
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer(); return

    allowed, msg_text = await check_allowed("withdraw")
    if not allowed:
        await call.message.answer(msg_text, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer(); return

    balance = await database.get_balance(call.from_user.id)
    await call.message.answer(
        f"💸 *Retragere KingsRiver Poker Club*\n\n"
        f"Soldul tău curent: *{balance:.2f} USDT*\n\n"
        f"Introdu suma pe care dorești să o retragi:",
        parse_mode="Markdown"
    )
    await state.set_state(UserFunnel.waiting_custom_amount)
    await state.update_data(mode="withdraw")
    await call.answer()

# ─── INPUT SUMĂ CUSTOM (depunere sau retragere) ───────
@dp.message(UserFunnel.waiting_custom_amount)
async def process_custom_amount(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "deposit")
    try:
        amount = float(msg.text.strip().replace(",", "."))
        if amount <= 0:
            await msg.answer("⚠️ Suma trebuie să fie mai mare decât 0.")
            return
        await state.clear()
        if mode == "deposit":
            await generate_invoice(msg, msg.from_user.id, amount)
        else:
            await process_withdrawal(msg, amount)
    except ValueError:
        await msg.answer("⚠️ Te rugăm să introduci o sumă validă (ex: 50 sau 50.5)")

# ─── GENERARE FACTURĂ CRYPTOBOT ───────────────────────
async def generate_invoice(msg, telegram_id: int, amount: float):
    try:
        tx_id   = await database.create_transaction(telegram_id, "deposit", amount, "pending")
        invoice = await create_invoice(amount, telegram_id, tx_id)
        pay_url    = invoice["pay_url"]
        invoice_id = invoice["invoice_id"]
        await database.update_transaction_invoice(tx_id, str(invoice_id))

        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Plătește {amount:.2f} USDT", url=pay_url)
        kb.button(text="❌ Anulează", callback_data="cancel")
        kb.adjust(1)

        await msg.answer(
            f"💰 *Factură generată!*\n\n"
            f"Sumă: *{amount:.2f} USDT*\n"
            f"Valabilă: *1 oră*\n\n"
            f"Apasă butonul de mai jos pentru a plăti prin CryptoBot.\n"
            f"✅ Balanța ta va fi actualizată *automat* după confirmare!",
            reply_markup=kb.as_markup(), parse_mode="Markdown"
        )
        await bot.send_message(
            config.ADMIN_CHAT_ID,
            f"💰 *Factură depunere creată*\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"💵 Sumă: *{amount:.2f} USDT*\n"
            f"🔖 TX ID: `{tx_id}` | Invoice: `{invoice_id}`\n"
            f"_Balanța se actualizează automat la plată._",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer("⚠️ Eroare la generarea facturii. Încearcă din nou sau contactează suportul.")
        print(f"CryptoBot invoice error: {e}")

# ─── PROCESARE RETRAGERE ──────────────────────────────
async def process_withdrawal(msg, amount: float):
    balance = await database.get_balance(msg.from_user.id)
    if amount > balance:
        await msg.answer(
            f"⚠️ Sold insuficient!\nSoldul tău curent: *{balance:.2f} USDT*",
            parse_mode="Markdown"
        )
        return

    user    = await database.get_user(msg.from_user.id)
    gg_name = user['gg_username'] if user else str(msg.from_user.id)
    tx_id   = await database.create_transaction(msg.from_user.id, "withdraw", amount)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Aprobă",  callback_data=f"approve_withdraw_{msg.from_user.id}_{amount}_{tx_id}")
    kb.button(text="❌ Respinge",callback_data=f"reject_withdraw_{msg.from_user.id}_{tx_id}")

    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f"💸 *Cerere retragere nouă!*\n\n"
        f"👤 GG Username: *{gg_name}*\n"
        f"🆔 Telegram ID: `{msg.from_user.id}`\n"
        f"💰 Sumă: *{amount:.2f} USDT*\n"
        f"🔖 TX ID: `{tx_id}`",
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await msg.answer(
        f"✅ Cererea de retragere de *{amount:.2f} USDT* a fost trimisă.\n"
        f"Vei fi notificat după aprobare.",
        reply_markup=main_menu(), parse_mode="Markdown"
    )

# ─── ADMIN: APROBARE / RESPINGERE RETRAGERE ───────────
@dp.callback_query(F.data.startswith("approve_withdraw_"))
async def approve_withdraw(call: types.CallbackQuery):
    parts   = call.data.split("_")
    user_id = int(parts[2])
    amount  = float(parts[3])
    tx_id   = int(parts[4])
    await database.update_balance(user_id, -amount)
    await database.update_transaction_status(tx_id, "completed")
    await call.message.edit_text(call.message.text + "\n\n✅ *APROBAT de admin*", parse_mode="Markdown")
    await bot.send_message(
        user_id,
        f"✅ Retragerea ta de *{amount:.2f} USDT* a fost aprobată!\n"
        f"Fondurile au fost trimise la wallet-ul tău.",
        parse_mode="Markdown"
    )
    await call.answer("Retragere aprobată!")

@dp.callback_query(F.data.startswith("reject_withdraw_"))
async def reject_withdraw(call: types.CallbackQuery):
    parts   = call.data.split("_")
    user_id = int(parts[2])
    tx_id   = int(parts[3])
    await database.update_transaction_status(tx_id, "rejected")
    await call.message.edit_text(call.message.text + "\n\n❌ *RESPINS de admin*", parse_mode="Markdown")
    await bot.send_message(user_id, "❌ Cererea ta de retragere a fost respinsă.\nContactează suportul pentru detalii.")
    await call.answer("Retragere respinsă!")

# ─── ANULARE ──────────────────────────────────────────
@dp.callback_query(F.data == "cancel")
async def cancel_action(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Acțiune anulată.", reply_markup=main_menu())
    await call.answer()

# ─── AJUTOR ───────────────────────────────────────────
@dp.callback_query(F.data == "help")
async def help_section(call: types.CallbackQuery):
    await call.message.answer(
        "ℹ️ *KingsRiver Poker Club — Ajutor*\n\n"
        "• 💰 Depunere: Plată automată prin CryptoBot (USDT)\n"
        "• 💸 Retragere: Solicită retragere fonduri\n"
        "• 📊 Sold: Vezi soldul curent\n\n"
        "📞 Support: @KingsRiverSupport",
        reply_markup=main_menu(), parse_mode="Markdown"
    )
    await call.answer()

# ─── PORNIRE ──────────────────────────────────────────
async def main():
    await database.init_db()
    print("Bot B (Operațional) pornit...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
