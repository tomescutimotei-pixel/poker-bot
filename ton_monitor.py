"""
ton_monitor.py — monitorizează adresa wallet a clubului pentru depuneri USDT
Rulează ca proces separat în Railway.

Flux:
1. La fiecare 15 secunde, verifică ultimele tranzacții USDT pe adresa clubului
2. Caută comentariul (memo) în format KR-{telegram_id}
3. Dacă găsește o tranzacție nouă cu comentariu valid → creditează userul automat
4. Dacă nu are comentariu sau e invalid → alertă admin pentru procesare manuală
5. Salvează hash-ul tranzacției în DB pentru a nu o procesa de 2 ori
"""

import asyncio
import aiohttp
import os
import database
import config

# ─── CONSTANTE ────────────────────────────────────────
CLUB_WALLET      = "UQB-Zisu31tvNvquF4WDyQHnNy8m4wdKyNsO4fGrIVAj5fwm"
USDT_MASTER      = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"  # USDT Jetton master pe mainnet
TONCENTER_API    = "https://toncenter.com/api/v2"
CHECK_INTERVAL   = 5   # secunde între verificări
BOT_API          = f"https://api.telegram.org/bot{config.BOT_B_TOKEN}"

# ─── HELPER: COD UNIC USER ────────────────────────────
def deposit_code(telegram_id: int) -> str:
    """Generează codul unic de depunere pentru un user."""
    return f"KR-{telegram_id}"

def parse_deposit_code(comment: str):
    """Extrage telegram_id din comentariu. Returnează None dacă invalid."""
    comment = (comment or "").strip()
    if comment.startswith("KR-"):
        try:
            return int(comment[3:])
        except ValueError:
            pass
    return None

# ─── TELEGRAM NOTIFICĂRI ──────────────────────────────
async def send_telegram(chat_id: int, text: str):
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BOT_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })

# ─── TON API: JETTON TRANSFERS ────────────────────────
async def get_recent_jetton_transfers() -> list:
    """
    Folosim TONCenter v3 pentru a obține transferurile USDT
    primite de adresa clubului.
    """
    api_key = os.getenv("TONCENTER_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    url = f"https://toncenter.com/api/v3/jetton/transfers"
    params = {
        "address":    CLUB_WALLET,
        "direction":  "in",           # doar transferuri primite
        "limit":      20,
        "offset":     0,
        "sort":       "desc",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"TONCenter error: {resp.status}")
                    return []
                data = await resp.json()
                return data.get("jetton_transfers", [])
    except Exception as e:
        print(f"TONCenter request error: {e}")
        return []

# ─── PROCESARE TRANZACȚII ─────────────────────────────
async def process_transfers():
    """Verifică transferurile noi și le procesează."""
    transfers = await get_recent_jetton_transfers()

    for tx in transfers:
        tx_hash = tx.get("transaction_hash", "")
        if not tx_hash:
            continue

        # verificăm dacă am procesat deja această tranzacție
        already = await database.get_transaction_by_ton_hash(tx_hash)
        if already:
            continue

        # verificăm că e USDT (jetton master corect)
        # TONCenter v3: adresa jetton e în tx["jetton"]["address"]
        jetton_info = tx.get("jetton", {})
        jetton_address = jetton_info.get("address", "") if isinstance(jetton_info, dict) else ""
        if USDT_MASTER.upper() != jetton_address.upper():
            continue

        # suma — USDT are 6 decimale
        try:
            raw_amount = int(tx.get("amount", 0))
            amount = raw_amount / 1_000_000
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        # comentariul / memo
        comment = tx.get("comment", "") or tx.get("forward_payload", "") or ""
        telegram_id = parse_deposit_code(str(comment))

        if telegram_id:
            # user identificat — creditare automată
            user = await database.get_user(telegram_id)
            if user:
                tx_id = await database.create_transaction(telegram_id, "deposit", amount, "completed")
                await database.update_balance(telegram_id, amount)
                await database.save_ton_hash(tx_hash, tx_id)

                # notificare user
                await send_telegram(
                    telegram_id,
                    f"✅ *Depunere confirmată automat!*\n\n"
                    f"💵 Sumă: *{amount:.2f} USDT*\n"
                    f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                    f"Fondurile sunt disponibile în contul tău. 🎰"
                )

                # notificare admin
                await send_telegram(
                    config.ADMIN_CHAT_ID,
                    f"✅ *Depunere automată procesată*\n\n"
                    f"👤 GG: *{user['gg_username']}*\n"
                    f"🆔 TG: `{telegram_id}`\n"
                    f"💵 Sumă: *{amount:.2f} USDT*\n"
                    f"🔖 TX: `{tx_hash[:16]}...`"
                )

                print(f"✅ Depunere auto: {amount} USDT → user {telegram_id}")
            else:
                # codul e valid dar userul nu e înregistrat
                await database.save_ton_hash(tx_hash, None)
                await send_telegram(
                    config.ADMIN_CHAT_ID,
                    f"⚠️ *Depunere cu cod valid dar user negăsit!*\n\n"
                    f"💵 Sumă: *{amount:.2f} USDT*\n"
                    f"📝 Comentariu: `{comment}`\n"
                    f"🆔 Telegram ID: `{telegram_id}`\n"
                    f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                    f"_Procesează manual din dashboard._"
                )
        else:
            # fără comentariu valid — alertă admin pentru procesare manuală
            await database.save_ton_hash(tx_hash, None)
            await send_telegram(
                config.ADMIN_CHAT_ID,
                f"⚠️ *Depunere fără cod identificator!*\n\n"
                f"💵 Sumă: *{amount:.2f} USDT*\n"
                f"📝 Comentariu: `{comment or 'lipsă'}`\n"
                f"🔖 TX: `{tx_hash[:16]}...`\n\n"
                f"_Procesează manual din dashboard._"
            )
            print(f"⚠️ Depunere fără cod: {amount} USDT, comment='{comment}'")

# ─── LOOP PRINCIPAL ───────────────────────────────────
async def main():
    await database.init_db()
    print("TON Monitor pornit — verificare la fiecare 15 secunde...")
    print(f"Wallet monitorizat: {CLUB_WALLET}")

    while True:
        try:
            await process_transfers()
        except Exception as e:
            print(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

