import asyncpg
import os
from datetime import datetime, timedelta

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            ssl="require",
            min_size=1,
            max_size=5,
        )
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          BIGINT  PRIMARY KEY,
                username    TEXT    DEFAULT '',
                first_name  TEXT    DEFAULT '',
                vip_until   TEXT    DEFAULT NULL,
                referred_by BIGINT  DEFAULT NULL,
                trial_used  INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pronos (
                id                 SERIAL  PRIMARY KEY,
                sport              TEXT    NOT NULL,
                match              TEXT    NOT NULL,
                date_match         TEXT    NOT NULL,
                prono              TEXT    NOT NULL,
                cote               TEXT    DEFAULT 'N/A',
                mise               TEXT    DEFAULT 'N/A',
                type_prono         TEXT    DEFAULT 'SAFE',
                resultat           TEXT    DEFAULT '⏳ En attente',
                analysis           TEXT    DEFAULT '',
                photo_id           TEXT    DEFAULT NULL,
                is_gratuit         INTEGER DEFAULT 0,
                created_as_gratuit INTEGER DEFAULT 0,
                created_at         TEXT    DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS paiements (
                id         SERIAL  PRIMARY KEY,
                user_id    BIGINT  NOT NULL,
                username   TEXT    DEFAULT '',
                montant    REAL    DEFAULT 10,
                statut     TEXT    DEFAULT 'attente',
                created_at TEXT    DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          SERIAL  PRIMARY KEY,
                referrer_id BIGINT  NOT NULL,
                referred_id BIGINT  NOT NULL,
                created_at  TEXT    DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id         SERIAL  PRIMARY KEY,
                code       TEXT    NOT NULL UNIQUE,
                jours      INTEGER NOT NULL,
                max_uses   INTEGER DEFAULT 0,
                uses_count INTEGER DEFAULT 0,
                active     INTEGER DEFAULT 1,
                created_at TEXT    DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS promo_usages (
                id         SERIAL  PRIMARY KEY,
                user_id    BIGINT  NOT NULL,
                code       TEXT    NOT NULL,
                created_at TEXT    DEFAULT '',
                UNIQUE(user_id, code)
            )
        """)


async def add_user(user_id: int, username: str, first_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username, first_name, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name
        """, user_id, username, first_name, datetime.utcnow().isoformat())


async def give_trial_vip(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trial_used, vip_until FROM users WHERE id = $1", user_id
        )
        if not row or row["trial_used"]:
            return False

        vip_until = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        await conn.execute(
            "UPDATE users SET trial_used = 1, vip_until = $1 WHERE id = $2",
            vip_until, user_id
        )
    return True


async def get_all_users() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users")
    return [r["id"] for r in rows]


async def count_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT COUNT(*) FROM users")
    return val or 0


async def get_user_by_username(username: str) -> dict | None:
    username = username.lstrip("@")
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE LOWER(username) = LOWER($1)", username
        )
    return dict(row) if row else None


async def is_vip(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT vip_until FROM users WHERE id = $1", user_id
        )
    if not row or not row["vip_until"]:
        return False
    try:
        return datetime.fromisoformat(row["vip_until"]) > datetime.now()
    except Exception:
        return False


async def extend_vip(user_id: int, days: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT vip_until FROM users WHERE id = $1", user_id
        )
        now = datetime.now()

        if row and row["vip_until"]:
            try:
                current = datetime.fromisoformat(row["vip_until"])
                base = current if current > now else now
            except Exception:
                base = now
        else:
            base = now

        new_until = (base + timedelta(days=days)).isoformat()

        await conn.execute(
            "UPDATE users SET vip_until = $1 WHERE id = $2",
            new_until, user_id
        )


async def remove_vip(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET vip_until = NULL WHERE id = $1", user_id
        )


async def count_vip() -> int:
    now = datetime.now().isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE vip_until > $1", now
        )
    return val or 0


async def add_prono(
    sport: str, match: str, date_match: str, prono: str,
    cote: str, mise: str, type_prono: str, analysis: str = "",
    created_as_gratuit: bool = False
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO pronos
                (sport, match, date_match, prono, cote, mise, type_prono, analysis, created_as_gratuit, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
        """, sport, match, date_match, prono, cote, mise, type_prono,
             analysis, int(created_as_gratuit), datetime.utcnow().isoformat())
    return row["id"]
