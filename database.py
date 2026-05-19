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
