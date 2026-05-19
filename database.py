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
                analyse            TEXT    DEFAULT '',
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
    """Donne 24h VIP gratuit si l'utilisateur n'a jamais eu de trial. Retourne True si accordé."""
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
            "UPDATE users SET vip_until = $1 WHERE id = $2", new_until, user_id
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


async def get_vip_users_details() -> list[dict]:
    now = datetime.now().isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE vip_until > $1 ORDER BY vip_until ASC", now
        )
    return [dict(r) for r in rows]


async def get_all_vip_users() -> list[int]:
    now = datetime.now().isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM users WHERE vip_until > $1", now
        )
    return [r["id"] for r in rows]


async def get_users_expiring_soon(days: int = 3) -> list[dict]:
    now = datetime.now()
    limit = (now + timedelta(days=days)).isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE vip_until > $1 AND vip_until <= $2",
            now.isoformat(), limit
        )
    return [dict(r) for r in rows]


async def remove_expired_vip() -> int:
    now = datetime.now().isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET vip_until = NULL WHERE vip_until <= $1 AND vip_until IS NOT NULL",
            now
        )
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def add_prono(
    sport: str, match: str, date_match: str, prono: str,
    cote: str, mise: str, type_prono: str, analyse: str = "",
    created_as_gratuit: bool = False
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO pronos
                (sport, match, date_match, prono, cote, mise, type_prono, analyse, created_as_gratuit, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
        """, sport, match, date_match, prono, cote, mise, type_prono, analyse,
            int(created_as_gratuit), datetime.utcnow().isoformat())
    return row["id"]


async def get_pronos(limit: int = 15) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos ORDER BY id DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]


async def get_pronos_by_type(type_prono: str, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos WHERE type_prono = $1 AND created_as_gratuit = 0 ORDER BY id DESC LIMIT $2",
            type_prono, limit
        )
    return [dict(r) for r in rows]


async def get_pronos_by_date(date_str: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos WHERE date_match LIKE $1 AND created_as_gratuit = 0 ORDER BY id DESC",
            f"{date_str}%"
        )
    return [dict(r) for r in rows]


async def get_pronos_valides(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos WHERE resultat != '⏳ En attente' ORDER BY id DESC LIMIT $1",
            limit
        )
    return [dict(r) for r in rows]


async def get_pronos_gratuits_created(limit: int = 20) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos WHERE created_as_gratuit = 1 ORDER BY id DESC LIMIT $1",
            limit
        )
    return [dict(r) for r in rows]


async def get_prono_gratuit() -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM pronos WHERE is_gratuit = 1 ORDER BY id DESC LIMIT 1"
        )
    return dict(row) if row else None


async def set_prono_gratuit(prono_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pronos SET is_gratuit = 0")
        await conn.execute("UPDATE pronos SET is_gratuit = 1 WHERE id = $1", prono_id)


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


async def get_stats_globales() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 0 AND resultat != '⏳ En attente'"
        )
    gagnes = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    perdus = sum(1 for r in rows if r["resultat"] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    roi    = round((gagnes - perdus) / total * 100, 1) if total else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux, "roi": roi}


async def get_stats_mensuelles() -> dict:
    mois = datetime.now().strftime("%m/%Y")
    debut = datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 0 AND resultat != '⏳ En attente' AND created_at >= $1",
            debut
        )
    gagnes = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    perdus = sum(1 for r in rows if r["resultat"] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"mois": mois, "gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_stats_gratuit() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 1 AND resultat != '⏳ En attente'"
        )
    gagnes = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    perdus = sum(1 for r in rows if r["resultat"] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_stats_gratuit_mensuelles() -> dict:
    mois = datetime.now().strftime("%m/%Y")
    debut = datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 1 AND resultat != '⏳ En attente' AND created_at >= $1",
            debut
        )
    gagnes = sum(1 for r in rows if r["resultat"] == "✅ Gagné")
    perdus = sum(1 for r in rows if r["resultat"] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"mois": mois, "gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_historique_gratuit(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pronos WHERE created_as_gratuit = 1 ORDER BY id DESC LIMIT $1",
            limit
        )
    return [dict(r) for r in rows]


async def add_paiement(user_id: int, username: str, montant: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO paiements (user_id, username, montant, created_at) VALUES ($1, $2, $3, $4)",
            user_id, username, montant, datetime.utcnow().isoformat()
        )


async def get_paiements_attente() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM paiements WHERE statut = 'attente' ORDER BY id ASC"
        )
    return [dict(r) for r in rows]


async def get_paiement(paiement_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM paiements WHERE id = $1", paiement_id
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
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM paiements WHERE statut = 'attente'"
        )
    return val or 0


async def has_been_referred(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM referrals WHERE referred_id = $1", user_id
        )
    return row is not None


async def add_referral(referrer_id: int, referred_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES ($1, $2, $3)",
            referrer_id, referred_id, datetime.utcnow().isoformat()
        )


async def get_referral_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id
        )
    return val or 0


# ══════════════════════════════════════════════════════════════════════════════
# CODES PROMO
# ══════════════════════════════════════════════════════════════════════════════

async def add_promo_code(code: str, jours: int, max_uses: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promo_codes (code, jours, max_uses, created_at) VALUES ($1, $2, $3, $4)",
            code.upper(), jours, max_uses, datetime.utcnow().isoformat()
        )


async def list_promo_codes() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM promo_codes WHERE active = 1 ORDER BY id DESC"
        )
    return [dict(r) for r in rows]


async def get_promo_code(code: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM promo_codes WHERE code = $1 AND active = 1",
            code.upper()
        )
    return dict(row) if row else None


async def has_used_promo(user_id: int, code: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM promo_usages WHERE user_id = $1 AND code = $2",
            user_id, code.upper()
        )
    return row is not None


async def use_promo_code(user_id: int, code: str) -> dict:
    """Valide et applique un code promo. Retourne {"ok": bool, "raison": str, "jours": int}"""
    promo = await get_promo_code(code)
    if not promo:
        return {"ok": False, "raison": "Code invalide ou expiré."}
    if await has_used_promo(user_id, code):
        return {"ok": False, "raison": "Tu as déjà utilisé ce code."}
    if promo["max_uses"] > 0 and promo["uses_count"] >= promo["max_uses"]:
        return {"ok": False, "raison": "Ce code a atteint son nombre maximum d'utilisations."}

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promo_usages (user_id, code, created_at) VALUES ($1, $2, $3)",
            user_id, code.upper(), datetime.utcnow().isoformat()
        )
        await conn.execute(
            "UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = $1",
            code.upper()
        )

    await extend_vip(user_id, promo["jours"])
    return {"ok": True, "jours": promo["jours"]}


async def delete_promo_code(code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE promo_codes SET active = 0 WHERE code = $1", code.upper()
        )
