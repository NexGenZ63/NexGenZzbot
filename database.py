from datetime import datetime, timedelta
import asyncpg
import os

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"])
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            vip_expiration TIMESTAMP,
            trial_used BOOLEAN DEFAULT FALSE,
            date_inscription TIMESTAMP DEFAULT NOW()
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pronos (
            id SERIAL PRIMARY KEY,
            sport TEXT,
            match TEXT,
            date_match TEXT,
            prono TEXT,
            cote TEXT DEFAULT 'N/A',
            mise TEXT DEFAULT 'N/A',
            resultat TEXT DEFAULT '⏳ En attente',
            type_prono TEXT DEFAULT 'SAFE',
            "analyse" TEXT DEFAULT '',
            photo_id TEXT,
            is_gratuit BOOLEAN DEFAULT FALSE,
            is_prono_du_jour BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS paiements (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT DEFAULT '',
            montant NUMERIC,
            statut TEXT DEFAULT 'attente',
            date TIMESTAMP DEFAULT NOW()
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS parrainages (
            id SERIAL PRIMARY KEY,
            parrain_id BIGINT,
            filleul_id BIGINT UNIQUE,
            date TIMESTAMP DEFAULT NOW()
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE,
            jours INTEGER,
            max_uses INTEGER DEFAULT 0,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id SERIAL PRIMARY KEY,
            code TEXT,
            user_id BIGINT,
            date TIMESTAMP DEFAULT NOW(),
            UNIQUE(code, user_id)
        )
        """)
    print("✅ Database initialisée")


# ========================
# UTILISATEURS
# ========================

async def add_user(user_id: int, username: str, first_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO users (user_id, username, first_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET username = EXCLUDED.username,
            first_name = EXCLUDED.first_name
        """, user_id, username, first_name)


async def get_user_by_username(username: str) -> dict | None:
    pool = await get_pool()
    uname = username.lstrip("@")
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT user_id AS id, first_name, username,
               vip_expiration::TEXT AS vip_until
        FROM users WHERE LOWER(username) = LOWER($1)
        """, uname)
    return dict(row) if row else None


async def count_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def get_all_users() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
    return [r["user_id"] for r in rows]


# ========================
# VIP
# ========================

async def is_vip(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT vip_expiration FROM users WHERE user_id = $1", user_id
        )
    if not row or not row["vip_expiration"]:
        return False
    return row["vip_expiration"] > datetime.utcnow()


async def extend_vip(user_id: int, days: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT vip_expiration FROM users WHERE user_id = $1", user_id
        )
        if row and row["vip_expiration"] and row["vip_expiration"] > datetime.utcnow():
            new_exp = row["vip_expiration"] + timedelta(days=days)
        else:
            new_exp = datetime.utcnow() + timedelta(days=days)
        await conn.execute("""
        UPDATE users SET vip_expiration = $1 WHERE user_id = $2
        """, new_exp, user_id)


async def remove_vip(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET vip_expiration = NULL WHERE user_id = $1", user_id
        )


async def count_vip() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE vip_expiration > NOW()"
        )


async def get_all_vip_users() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM users WHERE vip_expiration > NOW()"
        )
    return [r["user_id"] for r in rows]


async def get_vip_users_details() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT user_id AS id, first_name, username,
               vip_expiration::TEXT AS vip_until
        FROM users WHERE vip_expiration > NOW()
        ORDER BY vip_expiration ASC
        """)
    return [dict(r) for r in rows]


async def get_users_expiring_soon(days: int = 3) -> list[dict]:
    pool = await get_pool()
    cutoff = datetime.utcnow() + timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT user_id AS id FROM users
        WHERE vip_expiration > NOW() AND vip_expiration <= $1
        """, cutoff)
    return [dict(r) for r in rows]


async def remove_expired_vip() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("""
        UPDATE users SET vip_expiration = NULL
        WHERE vip_expiration IS NOT NULL AND vip_expiration <= NOW()
        """)
    return int(result.split()[-1])


async def give_trial_vip(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trial_used FROM users WHERE user_id = $1", user_id
        )
        if not row:
            expire_date = datetime.utcnow() + timedelta(days=1)
            await conn.execute("""
            UPDATE users SET vip_expiration = $1, trial_used = TRUE WHERE user_id = $2
            """, expire_date, user_id)
            return True
        if row["trial_used"]:
            return False
        expire_date = datetime.utcnow() + timedelta(days=1)
        await conn.execute("""
        UPDATE users SET vip_expiration = $1, trial_used = TRUE WHERE user_id = $2
        """, expire_date, user_id)
        return True


# ========================
# PARRAINAGE
# ========================

async def has_been_referred(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM parrainages WHERE filleul_id = $1", user_id
        )
    return row is not None


async def add_referral(parrain_id: int, filleul_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO parrainages (parrain_id, filleul_id)
        VALUES ($1, $2) ON CONFLICT (filleul_id) DO NOTHING
        """, parrain_id, filleul_id)


async def get_referral_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM parrainages WHERE parrain_id = $1", user_id
        )


# ========================
# PRONOS
# ========================

async def add_prono(
    sport: str, match: str, date_match: str, prono: str,
    cote: str, mise: str, type_prono: str, analyse: str = "",
    created_as_gratuit: bool = False
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        INSERT INTO pronos (sport, match, date_match, prono, cote, mise, type_prono, "analyse", is_gratuit)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """, sport, match, date_match, prono, cote, mise, type_prono, analyse, created_as_gratuit)
    return row["id"]


async def get_pronos(limit: int = 15) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, sport, match, date_match, prono, cote, mise,
               resultat, type_prono, photo_id, is_gratuit
        FROM pronos ORDER BY created_at DESC LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def get_pronos_by_type(type_prono: str, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, sport, match, date_match, prono, cote, mise,
               resultat, type_prono, photo_id
        FROM pronos
        WHERE type_prono = $1 AND is_gratuit = FALSE
        ORDER BY created_at DESC LIMIT $2
        """, type_prono, limit)
    return [dict(r) for r in rows]


async def get_pronos_by_date(date_str: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, sport, match, date_match, prono, cote, mise,
               resultat, type_prono, photo_id
        FROM pronos
        WHERE date_match LIKE $1 AND is_gratuit = FALSE
        ORDER BY created_at ASC
        """, f"{date_str}%")
    return [dict(r) for r in rows]


async def get_pronos_valides(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, sport, match, date_match, prono, resultat, type_prono
        FROM pronos
        WHERE resultat IN ('✅ Gagné', '❌ Perdu')
        ORDER BY created_at DESC LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def update_resultat(prono_id: int, resultat: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE pronos SET resultat = $1 WHERE id = $2", resultat, prono_id
        )


async def update_photo_id(prono_id: int, photo_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE pronos SET photo_id = $1 WHERE id = $2", photo_id, prono_id
        )


async def delete_prono(prono_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pronos WHERE id = $1", prono_id)


async def reset_stats():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pronos")


# ========================
# PRONO GRATUIT DU JOUR
# ========================

async def set_prono_gratuit(prono_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pronos SET is_prono_du_jour = FALSE WHERE is_prono_du_jour = TRUE")
        await conn.execute("UPDATE pronos SET is_prono_du_jour = TRUE WHERE id = $1", prono_id)


async def get_prono_gratuit() -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT id, sport, match, date_match, prono, resultat, "analyse"
        FROM pronos WHERE is_prono_du_jour = TRUE
        LIMIT 1
        """)
    return dict(row) if row else None


async def get_pronos_gratuits_created(limit: int = 20) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, sport, match, date_match, resultat
        FROM pronos WHERE is_gratuit = TRUE
        ORDER BY created_at DESC LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def get_historique_gratuit(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT sport, match, date_match, prono, resultat
        FROM pronos WHERE is_gratuit = TRUE
        ORDER BY created_at DESC LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def get_stats_gratuit() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        gagnes = await conn.fetchval(
            "SELECT COUNT(*) FROM pronos WHERE is_gratuit = TRUE AND resultat = '✅ Gagné'"
        )
        perdus = await conn.fetchval(
            "SELECT COUNT(*) FROM pronos WHERE is_gratuit = TRUE AND resultat = '❌ Perdu'"
        )
    total = gagnes + perdus
    taux = round((gagnes / total) * 100, 1) if total > 0 else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_stats_gratuit_mensuelles() -> dict:
    pool = await get_pool()
    now = datetime.utcnow()
    mois_str = now.strftime("%B %Y")
    debut = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with pool.acquire() as conn:
        gagnes = await conn.fetchval("""
        SELECT COUNT(*) FROM pronos
        WHERE is_gratuit = TRUE AND resultat = '✅ Gagné' AND created_at >= $1
        """, debut)
        perdus = await conn.fetchval("""
        SELECT COUNT(*) FROM pronos
        WHERE is_gratuit = TRUE AND resultat = '❌ Perdu' AND created_at >= $1
        """, debut)
    total = gagnes + perdus
    taux = round((gagnes / total) * 100, 1) if total > 0 else 0
    return {"mois": mois_str, "gagnes": gagnes, "perdus": perdus, "taux": taux}


# ========================
# STATISTIQUES VIP
# ========================

BK_MISE = {"SAFE": 5.0, "SEMI_SAFE": 2.25, "FUN": 1.0, "ULTRA_FUN": 0.375}


async def get_stats_globales() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT resultat, cote, type_prono FROM pronos
        WHERE is_gratuit = FALSE AND resultat IN ('✅ Gagné', '❌ Perdu')
        """)
    gagnes = 0
    perdus = 0
    roi = 0.0
    for r in rows:
        mise_bk = BK_MISE.get(r["type_prono"] or "SAFE", 1.0)
        if r["resultat"] == "✅ Gagné":
            gagnes += 1
            try:
                cote = float(str(r["cote"]).replace(",", "."))
            except Exception:
                cote = 1.0
            roi += round(mise_bk * (cote - 1), 2)
        else:
            perdus += 1
            roi -= mise_bk
    total = gagnes + perdus
    taux = round((gagnes / total) * 100, 1) if total > 0 else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux, "roi": round(roi, 2)}


async def get_stats_mensuelles() -> dict:
    pool = await get_pool()
    now = datetime.utcnow()
    mois_str = now.strftime("%B %Y")
    debut = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with pool.acquire() as conn:
        gagnes = await conn.fetchval("""
        SELECT COUNT(*) FROM pronos
        WHERE is_gratuit = FALSE AND resultat = '✅ Gagné' AND created_at >= $1
        """, debut)
        perdus = await conn.fetchval("""
        SELECT COUNT(*) FROM pronos
        WHERE is_gratuit = FALSE AND resultat = '❌ Perdu' AND created_at >= $1
        """, debut)
    total = gagnes + perdus
    taux = round((gagnes / total) * 100, 1) if total > 0 else 0
    return {"mois": mois_str, "gagnes": gagnes, "perdus": perdus, "taux": taux}


# ========================
# PAIEMENTS
# ========================

async def add_paiement(user_id: int, username: str, montant: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO paiements (user_id, username, montant)
        VALUES ($1, $2, $3)
        """, user_id, username, montant)


async def get_paiements_attente() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, user_id, username, montant
        FROM paiements WHERE statut = 'attente'
        ORDER BY date ASC
        """)
    return [dict(r) for r in rows]


async def get_paiement(paiement_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, user_id, username, montant FROM paiements WHERE id = $1", paiement_id
        )
    return dict(row) if row else None


async def valider_paiement(paiement_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE paiements SET statut = 'validé' WHERE id = $1", paiement_id
        )


async def count_paiements_attente() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM paiements WHERE statut = 'attente'"
        )


# ========================
# CODES PROMO
# ========================

async def add_promo_code(code: str, jours: int, max_uses: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO promo_codes (code, jours, max_uses)
        VALUES ($1, $2, $3)
        """, code, jours, max_uses)


async def list_promo_codes() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT pc.code, pc.jours, pc.max_uses,
               COUNT(pu.id) AS uses_count
        FROM promo_codes pc
        LEFT JOIN promo_uses pu ON pu.code = pc.code
        WHERE pc.active = TRUE
        GROUP BY pc.code, pc.jours, pc.max_uses
        ORDER BY pc.created_at DESC
        """)
    return [dict(r) for r in rows]


async def delete_promo_code(code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE promo_codes SET active = FALSE WHERE code = $1", code
        )


async def use_promo_code(user_id: int, code: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        promo = await conn.fetchrow("""
        SELECT pc.code, pc.jours, pc.max_uses, pc.active,
               COUNT(pu.id) AS uses_count
        FROM promo_codes pc
        LEFT JOIN promo_uses pu ON pu.code = pc.code
        WHERE pc.code = $1
        GROUP BY pc.code, pc.jours, pc.max_uses, pc.active
        """, code)

        if not promo:
            return {"ok": False, "raison": "Code invalide ou inexistant."}
        if not promo["active"]:
            return {"ok": False, "raison": "Ce code n'est plus actif."}
        if promo["max_uses"] > 0 and promo["uses_count"] >= promo["max_uses"]:
            return {"ok": False, "raison": "Ce code a atteint son nombre maximum d'utilisations."}

        already = await conn.fetchrow(
            "SELECT id FROM promo_uses WHERE code = $1 AND user_id = $2", code, user_id
        )
        if already:
            return {"ok": False, "raison": "Tu as déjà utilisé ce code."}

        await conn.execute(
            "INSERT INTO promo_uses (code, user_id) VALUES ($1, $2)", code, user_id
        )

    await extend_vip(user_id, promo["jours"])
    return {"ok": True, "jours": promo["jours"]}
