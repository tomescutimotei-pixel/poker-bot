import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                gg_username TEXT,
                balance REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                type TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                invoice_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)
        await conn.execute("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS invoice_id TEXT DEFAULT NULL
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # defaults
        defaults = [
            ('withdrawal_days',        '[-1]'),
            ('withdrawal_blocked',     'false'),
            ('withdrawal_blocked_msg', 'Retragerile sunt temporar dezactivate din cauze tehnice. Îți mulțumim pentru înțelegere!'),
            ('deposit_days',           '[-1]'),
            ('deposit_blocked',        'false'),
            ('deposit_blocked_msg',    'Depunerile sunt temporar dezactivate din cauze tehnice. Îți mulțumim pentru înțelegere!'),
        ]
        for key, value in defaults:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key, value
            )

# ─── USERS ────────────────────────────────────────────
async def get_user(telegram_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id=$1", telegram_id
        )

async def register_user(telegram_id, gg_username):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (telegram_id, gg_username) VALUES ($1, $2)
               ON CONFLICT (telegram_id) DO UPDATE SET gg_username=$2""",
            telegram_id, gg_username
        )

async def update_balance(telegram_id, amount):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = balance + $1 WHERE telegram_id=$2",
            amount, telegram_id
        )

async def get_balance(telegram_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM users WHERE telegram_id=$1", telegram_id
        )
        return row["balance"] if row else 0.0

async def manual_update_balance(telegram_id, new_balance):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance=$1 WHERE telegram_id=$2",
            new_balance, telegram_id
        )

async def get_all_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM users ORDER BY registered_at DESC")

# ─── TRANSACTIONS ─────────────────────────────────────
async def create_transaction(user_id, t_type, amount, status="pending"):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO transactions (user_id, type, amount, status)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            user_id, t_type, amount, status
        )

async def update_transaction_status(tx_id, status):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE transactions SET status=$1 WHERE id=$2",
            status, tx_id
        )

async def update_transaction_invoice(tx_id, invoice_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE transactions SET invoice_id=$1 WHERE id=$2",
            invoice_id, tx_id
        )

async def get_transaction_by_invoice(invoice_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM transactions WHERE invoice_id=$1",
            invoice_id
        )

async def get_pending_withdrawals():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT t.*, u.gg_username FROM transactions t
               JOIN users u ON t.user_id = u.telegram_id
               WHERE t.type='withdraw' AND t.status='pending'
               ORDER BY t.created_at DESC"""
        )

async def get_pending_deposits():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT t.*, u.gg_username FROM transactions t
               JOIN users u ON t.user_id = u.telegram_id
               WHERE t.type='deposit' AND t.status='pending'
               ORDER BY t.created_at DESC"""
        )

async def get_all_transactions(limit=100):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT t.*, u.gg_username FROM transactions t
               JOIN users u ON t.user_id = u.telegram_id
               ORDER BY t.created_at DESC LIMIT $1""",
            limit
        )

async def get_stats():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users       = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_balance     = await conn.fetchval("SELECT COALESCE(SUM(balance), 0) FROM users")
        pending_deposits  = await conn.fetchval("SELECT COUNT(*) FROM transactions WHERE type='deposit'  AND status='pending'")
        pending_withdrawals = await conn.fetchval("SELECT COUNT(*) FROM transactions WHERE type='withdraw' AND status='pending'")
        volume_today      = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE status='completed' AND created_at::date = CURRENT_DATE"
        )
        return {
            "total_users":          total_users,
            "total_balance":        float(total_balance),
            "pending_deposits":     pending_deposits,
            "pending_withdrawals":  pending_withdrawals,
            "volume_today":         float(volume_today),
        }

# ─── SETTINGS ─────────────────────────────────────────
async def get_setting(key: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key=$1", key)
        return row["value"] if row else None

async def set_setting(key: str, value: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value=$2",
            key, value
        )
