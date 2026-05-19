import aiosqlite
from datetime import datetime, timedelta

DB_PATH = "pronos.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                username    TEXT    DEFAULT '',
                first_name  TEXT    DEFAULT '',
                vip_until   TEXT    DEFAULT NULL,
                referred_by INTEGER DEFAULT NULL,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pronos (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                sport             TEXT    NOT NULL,
                match             TEXT    NOT NULL,
                date_match        TEXT    NOT NULL,
                prono             TEXT    NOT NULL,
                cote              TEXT    DEFAULT 'N/A',
                mise              TEXT    DEFAULT 'N/A',
                type_prono        TEXT    DEFAULT 'SAFE',
                resultat          TEXT    DEFAULT '⏳ En attente',
                analyse           TEXT    DEFAULT '',
                photo_id          TEXT    DEFAULT NULL,
                is_gratuit        INTEGER DEFAULT 0,
                created_as_gratuit INTEGER DEFAULT 0,
                created_at        TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paiements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                username   TEXT    DEFAULT '',
                montant    REAL    DEFAULT 10,
                statut     TEXT    DEFAULT 'attente',
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT    NOT NULL UNIQUE,
                jours      INTEGER NOT NULL,
                max_uses   INTEGER DEFAULT 0,
                uses_count INTEGER DEFAULT 0,
                active     INTEGER DEFAULT 1,
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_usages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                code       TEXT    NOT NULL,
                created_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(user_id, code)
            )
        """)
        await db.commit()

    # Migration : ajoute trial_used si la colonne n'existe pas encore
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # colonne déjà présente


async def add_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await db.commit()


async def give_trial_vip(user_id: int) -> bool:
    """Donne 24h VIP gratuit si l'utilisateur n'a jamais eu de trial. Retourne True si accordé."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT trial_used, vip_until FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row["trial_used"]:
            return False
        vip_until = datetime.utcnow() + timedelta(hours=24)
        await db.execute(
            "UPDATE users SET trial_used = 1, vip_until = ? WHERE id = ?",
            (vip_until.isoformat(), user_id)
        )
        await db.commit()
    return True


async def get_all_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM users") as cur:
            rows = await cur.fetchall()
    return [r["id"] for r in rows]


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def get_user_by_username(username: str) -> dict | None:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def is_vip(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT vip_until FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row or not row[0]:
        return False
    try:
        return datetime.fromisoformat(row[0]) > datetime.now()
    except Exception:
        return False


async def extend_vip(user_id: int, days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT vip_until FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()

        now = datetime.now()
        if row and row[0]:
            try:
                current = datetime.fromisoformat(row[0])
                base = current if current > now else now
            except Exception:
                base = now
        else:
            base = now

        new_until = (base + timedelta(days=days)).isoformat()
        await db.execute(
            "UPDATE users SET vip_until = ? WHERE id = ?", (new_until, user_id)
        )
        await db.commit()


async def remove_vip(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vip_until = NULL WHERE id = ?", (user_id,)
        )
        await db.commit()


async def count_vip() -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE vip_until > ?", (now,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def get_vip_users_details() -> list[dict]:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE vip_until > ? ORDER BY vip_until ASC", (now,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_vip_users() -> list[int]:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM users WHERE vip_until > ?", (now,)
        ) as cur:
            rows = await cur.fetchall()
    return [r["id"] for r in rows]


async def get_users_expiring_soon(days: int = 3) -> list[dict]:
    now = datetime.now()
    limit = (now + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE vip_until > ? AND vip_until <= ?",
            (now.isoformat(), limit)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def remove_expired_vip() -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE users SET vip_until = NULL WHERE vip_until <= ? AND vip_until IS NOT NULL",
            (now,)
        )
        await db.commit()
        return cur.rowcount


async def add_prono(
    sport: str, match: str, date_match: str, prono: str,
    cote: str, mise: str, type_prono: str, analyse: str = "",
    created_as_gratuit: bool = False
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO pronos
                (sport, match, date_match, prono, cote, mise, type_prono, analyse, created_as_gratuit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sport, match, date_match, prono, cote, mise, type_prono, analyse, int(created_as_gratuit)))
        await db.commit()
        return cur.lastrowid


async def get_pronos(limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_pronos_by_type(type_prono: str, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE type_prono = ? AND created_as_gratuit = 0 ORDER BY id DESC LIMIT ?",
            (type_prono, limit)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_pronos_by_date(date_str: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE date_match LIKE ? AND created_as_gratuit = 0 ORDER BY id DESC",
            (f"{date_str}%",)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_pronos_valides(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE resultat != '⏳ En attente' ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_pronos_gratuits_created(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE created_as_gratuit = 1 ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_prono_gratuit() -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE is_gratuit = 1 ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def set_prono_gratuit(prono_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE pronos SET is_gratuit = 0")
        await db.execute("UPDATE pronos SET is_gratuit = 1 WHERE id = ?", (prono_id,))
        await db.commit()


async def update_resultat(prono_id: int, resultat: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pronos SET resultat = ? WHERE id = ?", (resultat, prono_id)
        )
        await db.commit()


async def update_photo_id(prono_id: int, photo_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pronos SET photo_id = ? WHERE id = ?", (photo_id, prono_id)
        )
        await db.commit()


async def delete_prono(prono_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pronos WHERE id = ?", (prono_id,))
        await db.commit()


async def reset_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pronos")
        await db.commit()


async def get_stats_globales() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 0 AND resultat != '⏳ En attente'"
        ) as cur:
            rows = await cur.fetchall()

    gagnes = sum(1 for r in rows if r[0] == "✅ Gagné")
    perdus = sum(1 for r in rows if r[0] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    roi    = round((gagnes - perdus) / total * 100, 1) if total else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux, "roi": roi}


async def get_stats_mensuelles() -> dict:
    mois = datetime.now().strftime("%m/%Y")
    debut = datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 0 AND resultat != '⏳ En attente' AND created_at >= ?",
            (debut,)
        ) as cur:
            rows = await cur.fetchall()

    gagnes = sum(1 for r in rows if r[0] == "✅ Gagné")
    perdus = sum(1 for r in rows if r[0] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"mois": mois, "gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_stats_gratuit() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 1 AND resultat != '⏳ En attente'"
        ) as cur:
            rows = await cur.fetchall()

    gagnes = sum(1 for r in rows if r[0] == "✅ Gagné")
    perdus = sum(1 for r in rows if r[0] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_stats_gratuit_mensuelles() -> dict:
    mois = datetime.now().strftime("%m/%Y")
    debut = datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT resultat FROM pronos WHERE created_as_gratuit = 1 AND resultat != '⏳ En attente' AND created_at >= ?",
            (debut,)
        ) as cur:
            rows = await cur.fetchall()

    gagnes = sum(1 for r in rows if r[0] == "✅ Gagné")
    perdus = sum(1 for r in rows if r[0] == "❌ Perdu")
    total  = gagnes + perdus
    taux   = round(gagnes / total * 100, 1) if total else 0
    return {"mois": mois, "gagnes": gagnes, "perdus": perdus, "taux": taux}


async def get_historique_gratuit(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pronos WHERE created_as_gratuit = 1 ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def add_paiement(user_id: int, username: str, montant: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO paiements (user_id, username, montant) VALUES (?, ?, ?)",
            (user_id, username, montant)
        )
        await db.commit()


async def get_paiements_attente() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM paiements WHERE statut = 'attente' ORDER BY id ASC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_paiement(paiement_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM paiements WHERE id = ?", (paiement_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def valider_paiement(paiement_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE paiements SET statut = 'validé' WHERE id = ?", (paiement_id,)
        )
        await db.commit()


async def count_paiements_attente() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM paiements WHERE statut = 'attente'"
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def has_been_referred(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM referrals WHERE referred_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row is not None


async def add_referral(referrer_id: int, referred_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, referred_id)
        )
        await db.commit()


async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


# ══════════════════════════════════════════════════════════════════════════════
# CODES PROMO
# ══════════════════════════════════════════════════════════════════════════════

async def add_promo_code(code: str, jours: int, max_uses: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO promo_codes (code, jours, max_uses) VALUES (?, ?, ?)",
            (code.upper(), jours, max_uses)
        )
        await db.commit()


async def list_promo_codes() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM promo_codes WHERE active = 1 ORDER BY id DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_promo_code(code: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM promo_codes WHERE code = ? AND active = 1",
            (code.upper(),)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def has_used_promo(user_id: int, code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM promo_usages WHERE user_id = ? AND code = ?",
            (user_id, code.upper())
        ) as cur:
            row = await cur.fetchone()
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

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO promo_usages (user_id, code) VALUES (?, ?)",
            (user_id, code.upper())
        )
        await db.execute(
            "UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = ?",
            (code.upper(),)
        )
        await db.commit()

    await extend_vip(user_id, promo["jours"])
    return {"ok": True, "jours": promo["jours"]}


async def delete_promo_code(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE promo_codes SET active = 0 WHERE code = ?", (code.upper(),)
        )
        await db.commit()
