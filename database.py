import asyncpg
import os
from datetime import datetime, timedelta

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            ssl="require",
            min_size=1,
            max_size=5,
        )
    return _pool


# ─────────────────────────────
# USERS
# ─────────────────────────────

async def add_user(user_id, username, first_name):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username, first_name, created_at)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (id) DO NOTHING
        """, user_id, username, first_name, datetime.utcnow().isoformat())


async def get_user_by_username(username):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE username = $1", username.replace("@","")
        )


async def get_all_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users")
    return [r["id"] for r in rows]


async def count_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def is_vip(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT vip_until FROM users WHERE id=$1", user_id)

    if not row or not row["vip_until"]:
        return False

    try:
        return datetime.fromisoformat(row["vip_until"]) > datetime.now()
    except:
        return False


async def extend_vip(user_id, days):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT vip_until FROM users WHERE id=$1", user_id)

        now = datetime.now()

        if row and row["vip_until"]:
            try:
                base = datetime.fromisoformat(row["vip_until"])
                if base < now:
                    base = now
            except:
                base = now
        else:
            base = now

        new = base + timedelta(days=days)

        await conn.execute(
            "UPDATE users SET vip_until=$1 WHERE id=$2",
            new.isoformat(), user_id
        )


async def remove_vip(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET vip_until=NULL WHERE id=$1", user_id)


async def get_vip_users_details():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM users WHERE vip_until IS NOT NULL
        """)


async def get_users_expiring_soon(days=3):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users WHERE vip_until IS NOT NULL")

    result = []
    now = datetime.now()

    for r in rows:
        try:
            if datetime.fromisoformat(r["vip_until"]) - now <= timedelta(days=days):
                result.append(r)
        except:
            pass

    return result


async def remove_expired_vip():
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("""
            UPDATE users
            SET vip_until = NULL
            WHERE vip_until IS NOT NULL
        """)
    return res


# ─────────────────────────────
# PRONOS
# ─────────────────────────────

async def add_prono(sport, match, date_match, prono, cote, mise, type_prono, analysis="", created_as_gratuit=False):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO pronos
            (sport, match, date_match, prono, cote, mise, type_prono, resultat, analysis, created_as_gratuit, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'⏳ En attente',$8,$9,$10,$11)
            RETURNING id
        """,
        sport, match, date_match, prono, cote, mise, type_prono,
        analysis, int(created_as_gratuit), datetime.utcnow().isoformat())

    return row["id"]


async def get_prono_gratuit():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM pronos
            WHERE created_as_gratuit = 1
            ORDER BY id DESC
            LIMIT 1
        """)


async def set_prono_gratuit(prono_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pronos SET created_as_gratuit=1 WHERE id=$1", prono_id)


async def get_historique_gratuit(limit=10):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM pronos
            WHERE created_as_gratuit=1
            ORDER BY id DESC
            LIMIT $1
        """, limit)


async def get_stats_gratuit():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT resultat FROM pronos WHERE created_as_gratuit=1")

    g = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    p = sum(1 for r in rows if r["resultat"] == "❌ Perdu")

    t = round((g / (g+p)*100), 2) if (g+p) > 0 else 0

    return {"gagnes": g, "perdus": p, "taux": t}


async def get_stats_gratuit_mensuelles():
    return await get_stats_gratuit()


async def get_pronos_by_date(date_str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM pronos WHERE date_match LIKE $1",
            f"{date_str}%"
        )


async def get_pronos_by_type(type_prono, limit=10):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM pronos
            WHERE type_prono=$1
            ORDER BY id DESC
            LIMIT $2
        """, type_prono, limit)


async def get_pronos(limit=15):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM pronos
            ORDER BY id DESC
            LIMIT $1
        """, limit)


async def update_resultat(prono_id, resultat):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE pronos SET resultat=$1 WHERE id=$2",
            resultat, prono_id
        )


# ─────────────────────────────
# STATS GLOBAL
# ─────────────────────────────

async def get_stats_globales():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT resultat FROM pronos")

    g = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    p = sum(1 for r in rows if r["resultat"] == "❌ Perdu")
    total = g + p

    taux = round((g/total)*100, 2) if total else 0
    roi = round((g - p) * 2, 2)

    return {"gagnes": g, "perdus": p, "taux": taux, "roi": roi}


async def get_stats_mensuelles():
    return await get_stats_globales()


async def get_pronos_valides(limit=10):
    return await get_pronos(limit)


# ─────────────────────────────
# PAIEMENTS
# ─────────────────────────────

async def add_paiement(user_id, username, montant):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO paiements (user_id, username, montant, created_at)
            VALUES ($1,$2,$3,$4)
        """, user_id, username, montant, datetime.utcnow().isoformat())


async def get_paiement(paiement_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM paiements WHERE id=$1", paiement_id)


async def valider_paiement(paiement_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE paiements SET statut='valide' WHERE id=$1", paiement_id)


async def get_paiements_attente():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM paiements WHERE statut='attente'")


async def count_paiements_attente():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM paiements WHERE statut='attente'")


# ─────────────────────────────
# REFERRAL
# ─────────────────────────────

async def add_referral(referrer_id, referred_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO referrals (referrer_id, referred_id, created_at)
            VALUES ($1,$2,$3)
        """, referrer_id, referred_id, datetime.utcnow().isoformat())


async def has_been_referred(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM referrals WHERE referred_id=$1", user_id)
        return r is not None


async def get_referral_count(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=$1",
            user_id
        )
