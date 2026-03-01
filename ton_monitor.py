"""
ton_monitor.py — monitors the club wallet address for USDT deposits.
Runs as a separate service on Railway.

Flow:
1. Every 15 seconds, checks the latest USDT transactions on the club address
2. Looks for a comment/memo in the format KR-{telegram_id}
3. If a new transaction with a valid comment is found → credits the user automatically
4. If no comment or invalid → alerts admin for manual processing
5. Saves the transaction hash in DB to avoid processing it twice
"""

import asyncio
import aiohttp
import os
import database
import config

# ─── CONSTANTS ────────────────────────────────────────
CLUB_WALLET    = "UQB-Zisu31tvNvquF4WDyQHnNy8m4wdKyNsO4fGrIVAj5fwm"
USDT_MASTER    = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"  # USDT Jetton master on mainnet
CHECK_INTERVAL = 15   # seconds between checks
BOT_API        = f"https://api.telegram.org/bot{config.BOT_B_TOKEN}"

# ─── HELPERS ──────────────────────────────────────────
def deposit_code(telegram_id: int) -> str:
    """Unique deposit code for a user."""
    return f"KR-{telegram_id}"

def parse_deposit_code(comment: str):
    """Extracts telegram_id from comment. Returns None if invalid."""
    comment = (comment or "").strip()
    if comment.startswith("KR-"):
        try:
            return int(comment[3:])
        except ValueError:
            pass
    return None

# ─── TELEGRAM NOTIFICATIONS ───────────────────────────
async def send_telegram(chat_id: int, text: str):
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BOT_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })

# ─── TON API: JETTON TRANSFERS ────────────────────────
async def get_recent_jetton_transfers() -> list:
    """Fetches incoming USDT transfers to the club address via TONCenter v3."""
    api_key = os.getenv("TONCENTER_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    url = "https://toncenter.com/api/v3/jetton/transfers"
    params = {
        "address":   CLUB_WALLET,
        "direction": "in",
        "limit":     20,
        "offset":    0,
        "sort":      "desc",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"TONCenter error: HTTP {resp.status}")
                    return []
                data = await resp.json()
                return data.get("jetton_transfers", [])
    except Exception as e:
        print(f"TONCenter request error: {e}")
        return []

# ─── PROCESS TRANSFERS ────────────────────────────────
async def process_transfers():
    """Checks new transfers and processes them."""
    transfers = await get_recent_jetton_transfers()

    for tx in transfers:
        tx_hash = tx.get("transaction_hash", "")
        if not tx_hash:
            continue

        # skip if already processed
        already = await database.get_transaction_by_ton_hash(tx_hash)
        if already:
            continue

        # verify it's USDT — TONCenter v3: jetton address is in tx["jetton"]["address"]
        jetton_info    = tx.get("jetton", {})
        jetton_address = jetton_info.get("address", "") if isinstance(jetton_info, dict) else ""
        if USDT_MASTER.upper() != jetton_address.upper():
            continue

        # amount — USDT has 6 decimals
        try:
            raw_amount = int(tx.get("amount", 0))
            amount = raw_amount / 1_000_000
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        # comment / memo
        comment     = tx.get("comment", "") or tx.get("forward_payload", "") or ""
        telegram_id = parse_deposit_code(str(comment))

        if telegram_id:
            user = await database.get_user(telegram_id)
            if user:
                # user identified — auto credit
                tx_id = await database.create_transaction(telegram_id, "deposit", amount, "completed")
                await database.update_balance(telegram_id, amount)
                await database.save_ton_hash(tx_hash, tx_id)

                await send_telegram(
                    telegram_id,
                    f"✅ *Deposit confirmed automatically!*\n\n"
                    f"💵 Amount: *{amount:.2f} USDT*\n"
                    f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                    f"Funds are now available in your account. 🎰"
                )
                await send_telegram(
                    config.ADMIN_CHAT_ID,
                    f"✅ *Automatic deposit processed*\n\n"
                    f"👤 GG: *{user['gg_username']}*\n"
                    f"🆔 TG: `{telegram_id}`\n"
                    f"💵 Amount: *{amount:.2f} USDT*\n"
                    f"🔖 TX: `{tx_hash[:16]}...`"
                )
                print(f"✅ Auto deposit: {amount} USDT → user {telegram_id}")
            else:
                # valid code but user not registered
                await database.save_ton_hash(tx_hash, None)
                await send_telegram(
                    config.ADMIN_CHAT_ID,
                    f"⚠️ *Deposit with valid code but user not found!*\n\n"
                    f"💵 Amount: *{amount:.2f} USDT*\n"
                    f"📝 Comment: `{comment}`\n"
                    f"🆔 Telegram ID: `{telegram_id}`\n"
                    f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                    f"_Please process manually from the dashboard._"
                )
        else:
            # no valid memo — alert admin for manual processing
            await database.save_ton_hash(tx_hash, None)
            await send_telegram(
                config.ADMIN_CHAT_ID,
                f"⚠️ *Deposit without memo code!*\n\n"
                f"💵 Amount: *{amount:.2f} USDT*\n"
                f"📝 Comment: `{comment or 'none'}`\n"
                f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                f"_Please process manually from the dashboard._"
            )
            print(f"⚠️ Deposit without code: {amount} USDT, comment='{comment}'")

# ─── MAIN LOOP ────────────────────────────────────────
async def main():
    await database.init_db()
    print(f"TON Monitor started — checking every {CHECK_INTERVAL} seconds...")
    print(f"Monitoring wallet: {CLUB_WALLET}")

    while True:
        try:
            await process_transfers()
        except Exception as e:
            print(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
