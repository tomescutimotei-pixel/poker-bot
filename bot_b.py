import asyncio
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

# ─── STATES ───────────────────────────────────────────
class UserFunnel(StatesGroup):
    waiting_gg_username = State()
    waiting_withdraw_amount = State()

class AdminFlow(StatesGroup):
    waiting_deposit_amount = State()  # FIX: stare pentru suma depunerii

# ─── HELPERS ──────────────────────────────────────────
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Depunere", callback_data="deposit")
    kb.button(text="💸 Retragere", callback_data="withdraw")
    kb.button(text="📊 Sold curent", callback_data="balance")
    kb.button(text="ℹ️ Ajutor", callback_data="help")
    kb.adjust(2)
    return kb.as_markup()

async def ensure_registered(user_id) -> bool:
    """Returnează True dacă userul este înregistrat."""
    user = await database.get_user(user_id)
    return user is not None

# ─── /START ───────────────────────────────────────────
@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext):
    await state.clear()
    user = await database.get_user(msg.from_user.id)

    if user:
        await msg.answer(
            f"🃏 Bun venit înapoi, *{user['gg_username']}*!\n\nCe dorești să faci?",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    else:
        await msg.answer(
            "🃏 Bun venit la *KingsRiver Poker Club*!\n\n"
            "Pentru a continua, te rugăm să ne trimiți *username-ul sau ID-ul tău din GG Poker Club*:",
            parse_mode="Markdown"
        )
        await state.set_state(UserFunnel.waiting_gg_username)

# ─── COLECTARE GG USERNAME ────────────────────────────
@dp.message(UserFunnel.waiting_gg_username)
async def collect_gg_username(msg: types.Message, state: FSMContext):
    gg_username = msg.text.strip()
    await database.register_user(msg.from_user.id, gg_username)
    await state.clear()

    await msg.answer(
        f"✅ Înregistrare completă!\n\n"
        f"👤 GG Username: *{gg_username}*\n"
        f"🎰 Club: *KingsRiver Poker Club*\n\n"
        f"Acum poți depune fonduri și te bucura de joc!\n"
        f"Ce dorești să faci?",
        reply_markup=main_menu(),
        parse_mode="Markdown"
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
        await call.answer()
        return

    balance = await database.get_balance(call.from_user.id)
    await call.message.answer(
        f"📊 Soldul tău curent: *{balance:.2f} USDT*",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )
    await call.answer()

# ─── DEPUNERE ─────────────────────────────────────────
@dp.callback_query(F.data == "deposit")
async def deposit_flow(call: types.CallbackQuery):
    # FIX: verificare înregistrare
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Am trimis depunerea", callback_data="confirm_deposit")
    kb.button(text="❌ Anulează", callback_data="cancel")

    await call.message.answer(
        f"💰 *Depunere KingsRiver Poker Club*\n\n"
        f"Trimite suma dorită la adresa TON Wallet a clubului:\n\n"
        f"`{config.TELEGRAM_WALLET}`\n\n"
        f"⚠️ Important: Folosește *exclusiv TON/USDT* prin Telegram Wallet.\n"
        f"După ce ai trimis, apasă butonul de confirmare.",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data == "confirm_deposit")
async def confirm_deposit(call: types.CallbackQuery):
    user = await database.get_user(call.from_user.id)
    if not user:
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer()
        return

    gg_name = user['gg_username']

    # FIX: creăm tranzacția pending în DB
    tx_id = await database.create_transaction(call.from_user.id, "deposit", 0, "pending")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Confirmă", callback_data=f"admin_confirm_{call.from_user.id}_{tx_id}")
    kb.button(text="❌ Respinge", callback_data=f"admin_reject_{call.from_user.id}_{tx_id}")

    await bot.send_message(
        config.ADMIN_CHAT_ID,
        f"💰 *Cerere depunere nouă!*\n\n"
        f"👤 GG Username: *{gg_name}*\n"
        f"🆔 Telegram ID: `{call.from_user.id}`\n"
        f"🔖 TX ID: `{tx_id}`\n\n"
        f"Verifică wallet-ul, confirmă și introdu suma primită.",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )

    await call.message.answer(
        "⏳ Cererea ta de depunere a fost trimisă către administrator.\n"
        "Vei fi notificat imediat după confirmare.",
        reply_markup=main_menu()
    )
    await call.answer()

# ─── ADMIN CONFIRMARE DEPUNERE ────────────────────────
@dp.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_deposit(call: types.CallbackQuery, state: FSMContext):
    # FIX: parsare corectă cu tx_id
    parts = call.data.split("_")
    user_id = int(parts[2])
    tx_id = int(parts[3])

    await state.set_state(AdminFlow.waiting_deposit_amount)
    await state.update_data(user_id=user_id, tx_id=tx_id)

    await call.message.edit_text(
        call.message.text + "\n\n⏳ *Aștept suma de la admin...*",
        parse_mode="Markdown"
    )
    await call.message.answer(
        f"💰 Introdu suma depusă (în USDT) pentru utilizatorul `{user_id}`:\n"
        f"_(scrie doar numărul, ex: 50 sau 50.5)_",
        parse_mode="Markdown"
    )
    await call.answer()

# FIX: handler care primește suma și actualizează balanța
@dp.message(AdminFlow.waiting_deposit_amount)
async def admin_set_deposit_amount(msg: types.Message, state: FSMContext):
    try:
        amount = float(msg.text.strip().replace(",", "."))
        if amount <= 0:
            await msg.answer("⚠️ Suma trebuie să fie mai mare decât 0.")
            return

        data = await state.get_data()
        user_id = data["user_id"]
        tx_id = data["tx_id"]

        # FIX: actualizare balanță și status tranzacție
        await database.update_balance(user_id, amount)
        await database.update_transaction_status(tx_id, "completed")
        await state.clear()

        await msg.answer(f"✅ Depunere de *{amount:.2f} USDT* confirmată pentru utilizatorul `{user_id}`.", parse_mode="Markdown")

        await bot.send_message(
            user_id,
            f"✅ Depunerea ta de *{amount:.2f} USDT* a fost confirmată!\n"
            f"Fondurile sunt acum disponibile în contul tău.",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    except ValueError:
        await msg.answer("⚠️ Introdu o sumă validă (ex: 50 sau 50.5)")

@dp.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_deposit(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    tx_id = int(parts[3])

    await database.update_transaction_status(tx_id, "rejected")

    await call.message.edit_text(
        call.message.text + "\n\n❌ *RESPINS de admin*",
        parse_mode="Markdown"
    )
    await bot.send_message(
        user_id,
        "❌ Depunerea ta a fost respinsă de administrator.\n"
        "Te rugăm să contactezi suportul dacă crezi că este o eroare."
    )
    await call.answer("Depunere respinsă!")

# ─── RETRAGERE ────────────────────────────────────────
@dp.callback_query(F.data == "withdraw")
async def withdraw_flow(call: types.CallbackQuery, state: FSMContext):
    # FIX: verificare înregistrare
    if not await ensure_registered(call.from_user.id):
        await call.message.answer("⚠️ Nu ești înregistrat. Trimite /start pentru a începe.")
        await call.answer()
        return

    balance = await database.get_balance(call.from_user.id)

    await call.message.answer(
        f"💸 *Retragere KingsRiver Poker Club*\n\n"
        f"Soldul tău curent: *{balance:.2f} USDT*\n\n"
        f"Introdu suma pe care dorești să o retragi:",
        parse_mode="Markdown"
    )
    await state.set_state(UserFunnel.waiting_withdraw_amount)
    await call.answer()

@dp.message(UserFunnel.waiting_withdraw_amount)
async def process_withdraw(msg: types.Message, state: FSMContext):
    try:
        amount = float(msg.text.strip().replace(",", "."))
        balance = await database.get_balance(msg.from_user.id)

        if amount <= 0:
            await msg.answer("⚠️ Suma trebuie să fie mai mare decât 0.")
            return

        if amount > balance:
            await msg.answer(
                f"⚠️ Sold insuficient!\nSoldul tău curent: *{balance:.2f} USDT*",
                parse_mode="Markdown"
            )
            return

        user = await database.get_user(msg.from_user.id)
        gg_name = user['gg_username'] if user else str(msg.from_user.id)

        tx_id = await database.create_transaction(msg.from_user.id, "withdraw", amount)

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Aprobă", callback_data=f"approve_withdraw_{msg.from_user.id}_{amount}_{tx_id}")
        kb.button(text="❌ Respinge", callback_data=f"reject_withdraw_{msg.from_user.id}_{tx_id}")

        await bot.send_message(
            config.ADMIN_CHAT_ID,
            f"💸 *Cerere retragere nouă!*\n\n"
            f"👤 GG Username: *{gg_name}*\n"
            f"🆔 Telegram ID: `{msg.from_user.id}`\n"
            f"💰 Sumă: *{amount:.2f} USDT*\n"
            f"🔖 TX ID: `{tx_id}`",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )

        await state.clear()
        await msg.answer(
            f"✅ Cererea de retragere de *{amount:.2f} USDT* a fost trimisă.\n"
            f"Vei fi notificat după aprobare.",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )

    except ValueError:
        await msg.answer("⚠️ Te rugăm să introduci o sumă validă (ex: 50 sau 50.5)")

# ─── ADMIN APROBARE RETRAGERE ─────────────────────────
@dp.callback_query(F.data.startswith("approve_withdraw_"))
async def approve_withdraw(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    amount = float(parts[3])
    tx_id = int(parts[4])

    # FIX: actualizare balanță + status tranzacție
    await database.update_balance(user_id, -amount)
    await database.update_transaction_status(tx_id, "completed")

    await call.message.edit_text(
        call.message.text + f"\n\n✅ *APROBAT de admin*",
        parse_mode="Markdown"
    )
    await bot.send_message(
        user_id,
        f"✅ Retragerea ta de *{amount:.2f} USDT* a fost aprobată!\n"
        f"Fondurile au fost trimise la wallet-ul tău.",
        parse_mode="Markdown"
    )
    await call.answer("Retragere aprobată!")

@dp.callback_query(F.data.startswith("reject_withdraw_"))
async def reject_withdraw(call: types.CallbackQuery):
    parts = call.data.split("_")
    user_id = int(parts[2])
    tx_id = int(parts[3])

    # FIX: status tranzacție actualizat
    await database.update_transaction_status(tx_id, "rejected")

    await call.message.edit_text(
        call.message.text + "\n\n❌ *RESPINS de admin*",
        parse_mode="Markdown"
    )
    await bot.send_message(
        user_id,
        "❌ Cererea ta de retragere a fost respinsă.\n"
        "Contactează suportul pentru detalii."
    )
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
        "• 💰 Depunere: Trimite TON/USDT la wallet-ul clubului\n"
        "• 💸 Retragere: Solicită retragere fonduri\n"
        "• 📊 Sold: Vezi soldul curent\n\n"
        "📞 Support: @KingsRiverSupport",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )
    await call.answer()

# ─── PORNIRE BOT ──────────────────────────────────────
async def main():
    await database.init_db()
    print("Bot B (Operațional) pornit...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
