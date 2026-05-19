from datetime import datetime, timedelta
import asyncpg
import os

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool

    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"]
        )

    return _pool


async def give_trial_vip(user_id: int):
    pool = await get_pool()

    async with pool.acquire() as conn:

        # Vérifie si l'utilisateur existe
        user = await conn.fetchrow(
            """
            SELECT trial_used
            FROM users
            WHERE user_id = $1
            """,
            user_id
        )

        # Nouvel utilisateur
        if not user:
            expire_date = datetime.utcnow() + timedelta(days=1)

            await conn.execute(
                """
                INSERT INTO users (
                    user_id,
                    vip_expiration,
                    trial_used
                )
                VALUES ($1, $2, TRUE)
                """,
                user_id,
                expire_date
            )

            return True

        # Essai déjà utilisé
        if user["trial_used"]:
            return False

        # Active le VIP 24h
        expire_date = datetime.utcnow() + timedelta(days=1)

        await conn.execute(
            """
            UPDATE users
            SET
                vip_expiration = $1,
                trial_used = TRUE
            WHERE user_id = $2
            """,
            expire_date,
            user_id
        )

        return True


# =========================
# INITIALISATION DATABASE
# =========================

async def init_db():
    pool = await get_pool()

    async with pool.acquire() as conn:

        # Table utilisateurs
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            abonnement_expire TIMESTAMP,
            plan TEXT,
            free_trial_used BOOLEAN DEFAULT FALSE,
            parrain_id BIGINT,
            date_inscription TIMESTAMP DEFAULT NOW()
        )
        """)

        # Table paiements
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS paiements (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            montant TEXT,
            plan TEXT,
            date TIMESTAMP DEFAULT NOW()
        )
        """)

        # Table pronostics
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pronostics (
            id SERIAL PRIMARY KEY,
            contenu TEXT,
            date TIMESTAMP DEFAULT NOW()
        )
        """)

        # Table parrainage
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS parrainages (
            id SERIAL PRIMARY KEY,
            parrain_id BIGINT,
            filleul_id BIGINT,
            bonus_jours INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT NOW()
        )
        """)

    print("✅ Database initialisée")
