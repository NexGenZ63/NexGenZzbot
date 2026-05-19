import logging
import asyncio
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)
import database as db
from config import BOT_TOKEN, BOT_USERNAME, ADMIN_PASSWORD, PAYPAL_LINK, PAYPAL_LINK_HEBDO, CANAL_PUBLIC, PLANS, ADMIN_TELEGRAM_ID, PARRAIN_BONUS_JOURS

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def sport_emoji(sport: str) -> str:
    return {
        "football": "⚽", "tennis": "🎾", "basketball": "🏀",
        "rugby": "🏉", "hockey": "🏒", "baseball": "⚾", "autre": "🏆",
    }.get(sport.lower(), "🏆")


def type_emoji(t: str) -> str:
    return {"SAFE": "🟢", "SEMI_SAFE": "🟡", "FUN": "🟠", "ULTRA_FUN": "🔴"}.get(t, "🏷️")


def type_label(t: str) -> str:
    return {"SAFE": "SAFE", "SEMI_SAFE": "SEMI SAFE", "FUN": "FUN", "ULTRA_FUN": "ULTRA FUN"}.get(t, t)


def type_bk(t: str) -> str:
    return {
        "SAFE": "5% BK",
        "SEMI_SAFE": "2 – 2,5% BK",
        "FUN": "1% BK",
        "ULTRA_FUN": "0,25 – 0,5% BK",
    }.get(t, "")


def resultat_emoji(r: str) -> str:
    return {"✅ Gagné": "✅", "❌ Perdu": "❌", "⏳ En attente": "⏳"}.get(r, "⏳")


def md_safe(text: str) -> str:
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text


def is_admin_session(ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    return ctx.user_data.get("admin_authenticated", False)


def menu_principal() -> InlineKeyboardMarkup:
    boutons = [
        [InlineKeyboardButton("🎁 Prono gratuit du jour",    callback_data="prono_gratuit")],
        [InlineKeyboardButton("📋 Analyse du prono gratuit", callback_data="analyse_gratuit")],
        [InlineKeyboardButton("📜 Historique gratuit",       callback_data="historique")],
        [InlineKeyboardButton("⭐ Accès VIP",                callback_data="acces_vip")],
        [InlineKeyboardButton("📊 Résultats",                callback_data="resultats")],
        [InlineKeyboardButton("🤝 Parrainer un ami",         callback_data="parrainage")],
        [InlineKeyboardButton("📢 Canal public",             url=CANAL_PUBLIC)],
        [InlineKeyboardButton("📩 Me Contacter",             url="https://t.me/elprofesor63")],
        [InlineKeyboardButton("🔐 Admin",                    callback_data="admin_login")],
    ]
    return InlineKeyboardMarkup(boutons)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username or "", user.first_name or "")

    args = ctx.args
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0][4:])
            if referrer_id != user.id and not await db.has_been_referred(user.id):
                await db.add_referral(referrer_id, user.id)
                await db.extend_vip(referrer_id, PARRAIN_BONUS_JOURS)
                try:
                    await ctx.bot.send_message(
                        referrer_id,
                        f"🎉 *+{PARRAIN_BONUS_JOURS} jours VIP offerts !*\n\n"
                        f"Ton ami {user.first_name} a rejoint PronosBot grâce à ton lien de parrainage. 🙏\n"
                        f"Jours VIP ajoutés à ton abonnement !",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except (ValueError, IndexError):
            pass

    trial_accordé = await db.give_trial_vip(user.id)

    vip = await db.is_vip(user.id)
    statut = "⭐ *VIP actif*" if vip else "👤 Membre gratuit"

    if trial_accordé:
        texte = (
            f"🏆 *Bienvenue sur NexGenZz Pronos !*\n\n"
            f"Salut {user.first_name} ! 🎉\n\n"
            f"Bonne nouvelle — en activant le bot tu gagnes *24h d'essai VIP gratuit !* ⭐\n\n"
            f"Profites-en pour découvrir tous nos pronos, cotes et analyses. 🔥"
        )
    else:
        texte = (
            f"🏆 *Bienvenue sur NexGenZz Pronos !*\n\n"
            f"Salut {user.first_name} ! Ton bot de pronos multi-sports. ⚽🎾🏀\n\n"
            f"Statut : {statut}"
        )
    await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=menu_principal())


async def retour_menu(query, ctx):
    ctx.user_data.pop("admin_authenticated", None)
    vip = await db.is_vip(query.from_user.id)
    statut = "⭐ *VIP actif*" if vip else "👤 Membre gratuit"
    texte = (
        f"🏆 *PronosBot — Menu principal*\n\n"
        f"Statut : {statut}\n\n"
        f"Choisis une option ⬇️"
    )
    await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=menu_principal())


async def show_prono_gratuit(query, ctx):
    prono = await db.get_prono_gratuit()
    if not prono:
        texte = (
            "🎁 *Prono gratuit du jour*\n\n"
            "📭 Pas encore de prono gratuit pour aujourd'hui.\n"
            "Reviens plus tard ou rejoins le canal !"
        )
    else:
        es = sport_emoji(prono["sport"])
        texte = (
            f"🎁 *Prono gratuit du jour*\n\n"
            f"{es} *{prono['match']}*\n"
            f"📅 {prono['date_match']}\n"
            f"🎯 Prono : *{prono['prono']}*\n"
            f"📊 {resultat_emoji(prono['resultat'])} {prono['resultat']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ _Passe VIP pour voir TOUS les pronos + cotes !_"
        )
    boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
    await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def show_historique(query, ctx):
    pronos = await db.get_historique_gratuit(limit=10)
    stats = await db.get_stats_gratuit()
    stats_mois = await db.get_stats_gratuit_mensuelles()

    if not pronos:
        texte = (
            "📜 *Historique des pronos gratuits*\n\n"
            "📭 Aucun prono gratuit publié pour le moment.\n"
            "Reviens plus tard !"
        )
    else:
        texte = (
            f"📜 *Statistiques Pronos Gratuits*\n\n"
            f"*📅 Ce mois ({stats_mois['mois']}) :*\n"
            f"✅ {stats_mois['gagnes']} gagnés | ❌ {stats_mois['perdus']} perdus | 🎯 {stats_mois['taux']}%\n\n"
            f"*📈 Total général :*\n"
            f"✅ {stats['gagnes']} gagnés | ❌ {stats['perdus']} perdus | 🎯 {stats['taux']}%\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*10 derniers pronos gratuits :*\n\n"
        )
        for p in pronos:
            es = sport_emoji(p["sport"])
            er = resultat_emoji(p["resultat"])
            texte += (
                f"{er} {es} *{p['match']}*\n"
                f"📅 {p['date_match']} — 🎯 {p['prono']}\n\n"
            )
        texte += "━━━━━━━━━━━━━━━━━━━━━━━━━\n⭐ _Passe VIP pour voir TOUS les pronos + cotes !_"
    boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
    await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def show_acces_vip(query, ctx):
    user_id = query.from_user.id
    vip = await db.is_vip(user_id)

    if vip or is_admin_session(ctx):
        boutons = [
            [InlineKeyboardButton("🟢 SAFE",      callback_data="vip_type_SAFE"),
             InlineKeyboardButton("🟡 SEMI SAFE", callback_data="vip_type_SEMI_SAFE")],
            [InlineKeyboardButton("🟠 FUN",       callback_data="vip_type_FUN"),
             InlineKeyboardButton("🔴 ULTRA FUN", callback_data="vip_type_ULTRA_FUN")],
            [InlineKeyboardButton("🔙 Menu",      callback_data="menu")],
        ]
        entete = (
            "🔧 _[Prévisualisation admin]_\n\n"
            if is_admin_session(ctx) and not vip
            else ""
        )
        await query.edit_message_text(
            f"{entete}"
            "⭐ *Espace VIP — Choisir une catégorie*\n\n"
            "🟢 *SAFE* — Mise : *5% BK*\n"
            "🟡 *SEMI SAFE* — Mise : *2 – 2,5% BK*\n"
            "🟠 *FUN* — Mise : *1% BK*\n"
            "🔴 *ULTRA FUN* — Mise : *0,25 – 0,5% BK*\n\n"
            "_BK = votre bankroll totale_\n\n"
            "Quelle catégorie veux-tu consulter ?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons)
        )
    else:
        texte = (
            "⭐ *Accès VIP — Choisis ton abonnement*\n\n"
            "✅ Tous les pronos du jour (multi-sports)\n"
            "✅ Cotes + mises conseillées\n"
            "✅ Analyses détaillées\n"
            "✅ Alertes 1h avant chaque match\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🗓️ *Hebdomadaire* — *3€ / 7 jours*\n"
            "📅 *Mensuel* — *10€ / 30 jours*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💳 *Comment s'abonner ?*\n\n"
            "1️⃣ Clique sur le bouton PayPal de ton choix\n"
            "2️⃣ Dans la note PayPal, mets ton *username Telegram*\n"
            f"3️⃣ Ton ID : `{query.from_user.id}` (copie-le aussi)\n"
            "4️⃣ Tape /payer pour notifier ton paiement\n\n"
            "✅ Accès activé sous 24h !"
        )
        boutons = [
            [InlineKeyboardButton("💳 Hebdo — 3€ / 7 jours",     url=PAYPAL_LINK_HEBDO)],
            [InlineKeyboardButton("💳 Mensuel — 10€ / 30 jours", url=PAYPAL_LINK)],
            [InlineKeyboardButton("🔙 Menu",                      callback_data="menu")],
        ]
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


BK_MISE = {
    "SAFE": 5.0,
    "SEMI_SAFE": 2.25,
    "FUN": 1.0,
    "ULTRA_FUN": 0.375,
}


def build_bilan(pronos: list, date_str: str) -> tuple[str, list]:
    lines = []
    total_bk = 0.0
    pending = 0
    resolved = 0
    for p in pronos:
        t = p.get("type_prono") or "SAFE"
        te = type_emoji(t)
        tl = type_label(t)
        mise_bk = BK_MISE.get(t, 1.0)
        res = p.get("resultat", "⏳ En attente")
        try:
            cote = float(str(p["cote"]).replace(",", "."))
        except Exception:
            cote = 1.0
        nom = md_safe(p["match"][:32])
        if res == "✅ Gagné":
            profit = round(mise_bk * (cote - 1), 2)
            total_bk += profit
            resolved += 1
            lines.append(f"✅ {te} *{nom}*\n   _{tl} | cote {p['cote']}_ → *+{profit:.2f}% BK*")
        elif res == "❌ Perdu":
            profit = -mise_bk
            total_bk += profit
            resolved += 1
            lines.append(f"❌ {te} *{nom}*\n   _{tl}_ → *{profit:.2f}% BK*")
        else:
            pending += 1
            lines.append(f"⏳ {te} *{nom}*\n   _{tl}_ — en attente")

    total_bk = round(total_bk, 2)
    signe = "+" if total_bk >= 0 else ""
    if resolved == 0:
        verdict = "⏳ Tous les pronos sont en attente."
    elif total_bk > 0:
        verdict = f"🟢 Journée positive : *{signe}{total_bk:.2f}% BK* gagné !"
    elif total_bk < 0:
        verdict = f"🔴 Journée négative : *{total_bk:.2f}% BK* perdu."
    else:
        verdict = "⚪ Journée nulle : *0.00% BK*."

    texte = f"📊 *Bilan VIP — {md_safe(date_str)}*\n\n"
    texte += "\n\n".join(lines) if lines else "_Aucun prono VIP ce jour._"
    texte += f"\n\n{'─'*28}\n{verdict}"
    if pending:
        texte += f"\n_({pending} prono(s) encore en attente non comptabilisé(s))_"

    boutons = [
        [InlineKeyboardButton("📊 Autre date", callback_data="admin_bilan")],
        [InlineKeyboardButton("🔙 Admin",      callback_data="admin_back")],
    ]
    return texte, boutons


async def show_bilan_journalier(query, ctx, date_str: str):
    pronos = await db.get_pronos_by_date(date_str)
    texte, boutons = build_bilan(pronos, date_str)
    try:
        await query.edit_message_text(texte, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(boutons))
    except Exception:
        await query.edit_message_text(texte, reply_markup=InlineKeyboardMarkup(boutons))


async def show_vip_by_type(query, ctx, type_prono: str):
    pronos = await db.get_pronos_by_type(type_prono, limit=10)
    te = type_emoji(type_prono)
    tl = type_label(type_prono)
    boutons_photo = []
    bk = type_bk(type_prono)
    if not pronos:
        texte = f"⭐ *Espace VIP — {te} {tl}*\n💰 Mise recommandée : *{bk}*\n\n📭 Aucun prono dans cette catégorie pour le moment."
    else:
        texte = f"⭐ *Espace VIP — {te} {tl}*\n💰 Mise recommandée : *{bk}*\n\n"
        for p in pronos:
            es = sport_emoji(p["sport"])
            er = resultat_emoji(p["resultat"])
            texte += (
                f"{es} {md_safe(p['match'])}\n"
                f"📅 {p['date_match']} | 🏷️ {p['sport'].capitalize()}\n"
                f"🎯 {md_safe(p['prono'])} | 💰 Cote : {md_safe(str(p['cote']))} | Mise : {md_safe(str(p['mise']))}u\n"
                f"{er} {p['resultat']}\n\n"
            )
            if p.get("photo_id"):
                boutons_photo.append([InlineKeyboardButton(
                    f"📷 Photo — {p['match'][:28]}", callback_data=f"view_photo_{p['id']}"
                )])
    boutons = boutons_photo + [
        [InlineKeyboardButton("🔙 Catégories VIP", callback_data="acces_vip")],
        [InlineKeyboardButton("🏠 Menu",           callback_data="menu")],
    ]
    try:
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))
    except Exception:
        await query.edit_message_text(texte, reply_markup=InlineKeyboardMarkup(boutons))


async def show_resultats(query, ctx):
    stats = await db.get_stats_globales()
    stats_mois = await db.get_stats_mensuelles()
    pronos = await db.get_pronos_valides(limit=10)

    texte = (
        f"📊 *Résultats & Statistiques VIP*\n\n"
        f"*📅 Ce mois ({stats_mois['mois']}) :*\n"
        f"✅ {stats_mois['gagnes']} gagnés | ❌ {stats_mois['perdus']} perdus\n"
        f"🎯 Taux : *{stats_mois['taux']}%*\n\n"
        f"*📈 Total général :*\n"
        f"✅ Gagnés : *{stats['gagnes']}* | ❌ Perdus : *{stats['perdus']}*\n"
        f"🎯 Taux : *{stats['taux']}%* | 💰 ROI : *{stats['roi']:+}%*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*10 derniers résultats validés :*\n\n"
    )
    if not pronos:
        texte += "_Aucun résultat validé pour le moment._"
    else:
        for p in pronos:
            er = resultat_emoji(p["resultat"])
            es = sport_emoji(p["sport"])
            te = type_emoji(p.get("type_prono") or "SAFE")
            texte += f"{er} {te} {es} *{p['match']}*\n   🎯 {p['prono']} | 📅 {p['date_match']}\n\n"

    boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
    await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def show_admin_login(query, ctx):
    ctx.user_data.pop("admin_authenticated", None)
    ctx.user_data["action"] = "admin_login"
    await query.edit_message_text(
        "🔐 *Panel Admin*\n\nEntre le mot de passe pour accéder au panel :",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]),
    )


async def show_admin_menu(query, ctx):
    nb_users = await db.count_users()
    nb_vip = await db.count_vip()
    nb_attente = await db.count_paiements_attente()

    texte = (
        f"🔧 *Panel Admin*\n\n"
        f"👥 Membres : *{nb_users}* | ⭐ VIP actifs : *{nb_vip}*\n"
        f"💳 Paiements en attente : *{nb_attente}*\n\n"
        f"Que veux-tu faire ?"
    )
    boutons = [
        [InlineKeyboardButton("➕ Poster prono VIP",          callback_data="admin_add_prono")],
        [InlineKeyboardButton("🎁 Définir prono gratuit",    callback_data="admin_set_gratuit")],
        [InlineKeyboardButton("✏️ Mettre à jour résultat",   callback_data="admin_update_result")],
        [InlineKeyboardButton("💳 Valider un paiement VIP",  callback_data="admin_valider_vip")],
        [InlineKeyboardButton("👑 Ajouter VIP manuellement", callback_data="admin_add_vip_manual")],
        [InlineKeyboardButton("❌ Retirer un VIP",           callback_data="admin_remove_vip")],
        [InlineKeyboardButton("📋 Liste des pronos",         callback_data="admin_list_pronos")],
        [InlineKeyboardButton("🗑️ Supprimer un prono",      callback_data="admin_delete_prono")],
        [InlineKeyboardButton("📢 Broadcast",                callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Bilan journalier",         callback_data="admin_bilan")],
        [InlineKeyboardButton("🔄 Réinitialiser les stats",  callback_data="admin_reset_stats")],
        [InlineKeyboardButton("🎟️ Codes promo",              callback_data="admin_promos")],
        [InlineKeyboardButton("🚪 Déconnexion admin",        callback_data="admin_logout")],
        [InlineKeyboardButton("🔙 Menu",                     callback_data="menu")],
    ]
    await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "menu":
        ctx.user_data.clear()
        await retour_menu(query, ctx)

    elif data == "prono_gratuit":
        await show_prono_gratuit(query, ctx)

    elif data == "analyse_gratuit":
        prono = await db.get_prono_gratuit()
        if not prono:
            texte = "📋 *Analyse du prono gratuit*\n\n📭 Aucun prono gratuit disponible pour le moment."
        elif not prono.get("analyse"):
            texte = (
                f"📋 *Analyse du prono gratuit*\n\n"
                f"⚠️ Aucune analyse disponible pour ce prono.\n\n"
                f"_Reviens plus tard !_"
            )
        else:
            es = sport_emoji(prono["sport"])
            texte = (
                f"📋 *Analyse du prono gratuit*\n\n"
                f"{es} *{prono['match']}* — {prono['date_match']}\n"
                f"🎯 Prono : *{prono['prono']}*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{prono['analyse']}"
            )
        boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

    elif data == "historique":
        await show_historique(query, ctx)

    elif data == "acces_vip":
        await show_acces_vip(query, ctx)

    elif data.startswith("vip_type_"):
        if not (await db.is_vip(user_id) or is_admin_session(ctx)):
            await query.answer("⛔ Accès VIP requis", show_alert=True)
            return
        t = data.split("vip_type_", 1)[1]
        await show_vip_by_type(query, ctx, t)

    elif data == "resultats":
        await show_resultats(query, ctx)

    elif data == "parrainage":
        nb = await db.get_referral_count(user_id)
        lien = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        texte = (
            f"🤝 *Parrainage PronosBot*\n\n"
            f"Partage ton lien et gagne *{PARRAIN_BONUS_JOURS} jours VIP* pour chaque ami qui rejoint !\n\n"
            f"🔗 *Ton lien de parrainage :*\n`{lien}`\n\n"
            f"👥 Amis parrainés : *{nb}*\n"
            f"🎁 Jours VIP gagnés : *{nb * PARRAIN_BONUS_JOURS}*"
        )
        boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

    elif data == "admin_login":
        await show_admin_login(query, ctx)

    elif data == "admin_logout":
        ctx.user_data.pop("admin_authenticated", None)
        ctx.user_data.clear()
        await retour_menu(query, ctx)

    elif data == "admin_back":
        if is_admin_session(ctx):
            await show_admin_menu(query, ctx)
        else:
            await retour_menu(query, ctx)

    elif data == "admin_add_prono":
        if not is_admin_session(ctx):
            await query.answer("⛔ Non autorisé", show_alert=True)
            return
        ctx.user_data["action"] = "add_prono"
        ctx.user_data["etape"] = "sport"
        ctx.user_data.pop("prono_is_gratuit", None)
        boutons = [
            [InlineKeyboardButton("⚽ Football",   callback_data="sport_football"),
             InlineKeyboardButton("🎾 Tennis",     callback_data="sport_tennis")],
            [InlineKeyboardButton("🏀 Basketball", callback_data="sport_basketball"),
             InlineKeyboardButton("🏉 Rugby",      callback_data="sport_rugby")],
            [InlineKeyboardButton("🏒 Hockey",     callback_data="sport_hockey"),
             InlineKeyboardButton("🏆 Autre",      callback_data="sport_autre")],
        ]
        await query.edit_message_text(
            "➕ *Nouveau prono — Sport ?*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("sport_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        sport = data.split("_", 1)[1]
        ctx.user_data["prono_sport"] = sport
        if ctx.user_data.get("prono_is_gratuit"):
            ctx.user_data["prono_type"] = "SAFE"
            ctx.user_data["etape"] = "match"
            await query.edit_message_text(
                f"✅ Sport : *{sport_emoji(sport)} {sport.capitalize()}*\n\n"
                f"📝 Envoie le nom du match :\n_Ex : PSG vs Real Madrid_",
                parse_mode="Markdown"
            )
        else:
            ctx.user_data["etape"] = "type"
            boutons = [
                [InlineKeyboardButton("🟢 SAFE",      callback_data="type_prono_SAFE"),
                 InlineKeyboardButton("🟡 SEMI SAFE", callback_data="type_prono_SEMI_SAFE")],
                [InlineKeyboardButton("🟠 FUN",       callback_data="type_prono_FUN"),
                 InlineKeyboardButton("🔴 ULTRA FUN", callback_data="type_prono_ULTRA_FUN")],
            ]
            await query.edit_message_text(
                f"✅ Sport : *{sport_emoji(sport)} {sport.capitalize()}*\n\n"
                f"🏷️ *Type de prono ?*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(boutons)
            )

    elif data.startswith("type_prono_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        t = data.split("type_prono_", 1)[1]
        ctx.user_data["prono_type"] = t
        ctx.user_data["etape"] = "match"
        sport = ctx.user_data.get("prono_sport", "")
        await query.edit_message_text(
            f"✅ Sport : *{sport_emoji(sport)} {sport.capitalize()}* | {type_emoji(t)} *{type_label(t)}*\n\n"
            f"📝 Envoie le nom du match :\n_Ex : PSG vs Real Madrid_",
            parse_mode="Markdown"
        )

    elif data == "admin_set_gratuit":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        pronos = await db.get_pronos_gratuits_created(limit=20)
        boutons = []
        for p in pronos:
            er = resultat_emoji(p.get("resultat", "⏳ En attente"))
            label = f"{er} {sport_emoji(p['sport'])} {p['match'][:22]} — {p['date_match']}"
            boutons.append([InlineKeyboardButton(label, callback_data=f"gratuit_{p['id']}")])
        boutons.append([InlineKeyboardButton("➕ Créer un nouveau prono gratuit", callback_data="admin_add_prono_gratuit")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        msg_txt = (
            "🎁 *Choisis le prono gratuit du jour :*\n_(Seuls tes pronos gratuits apparaissent ici)_"
            if pronos else
            "🎁 *Aucun prono gratuit créé.*\n\nCrée-en un directement :"
        )
        await query.edit_message_text(msg_txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

    elif data == "admin_add_prono_gratuit":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        ctx.user_data["action"] = "add_prono"
        ctx.user_data["etape"] = "sport"
        ctx.user_data["prono_is_gratuit"] = True
        boutons = [
            [InlineKeyboardButton("⚽ Football",   callback_data="sport_football"),
             InlineKeyboardButton("🎾 Tennis",     callback_data="sport_tennis")],
            [InlineKeyboardButton("🏀 Basketball", callback_data="sport_basketball"),
             InlineKeyboardButton("🏉 Rugby",      callback_data="sport_rugby")],
            [InlineKeyboardButton("🏒 Hockey",     callback_data="sport_hockey"),
             InlineKeyboardButton("🏆 Autre",      callback_data="sport_autre")],
        ]
        await query.edit_message_text(
            "🎁 *Nouveau prono gratuit — Sport ?*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("gratuit_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        prono_id = int(data.split("_")[1])
        await db.set_prono_gratuit(prono_id)
        await query.edit_message_text(
            "✅ Prono gratuit du jour défini !",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_update_result":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        pronos = await db.get_pronos(limit=15)
        if not pronos:
            await query.edit_message_text("📭 Aucun prono.")
            return
        boutons = []
        for p in pronos:
            er = resultat_emoji(p["resultat"])
            label = f"{er} [{p['id']}] {p['match'][:20]} — {p['prono'][:15]}"
            boutons.append([InlineKeyboardButton(label, callback_data=f"edit_result_{p['id']}")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        await query.edit_message_text(
            "✏️ *Quel prono mettre à jour ?*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("edit_result_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        prono_id = int(data.split("_")[2])
        ctx.user_data["edit_prono_id"] = prono_id
        boutons = [
            [InlineKeyboardButton("✅ Gagné",      callback_data=f"set_result_{prono_id}_gagne")],
            [InlineKeyboardButton("❌ Perdu",      callback_data=f"set_result_{prono_id}_perdu")],
            [InlineKeyboardButton("⏳ En attente", callback_data=f"set_result_{prono_id}_attente")],
            [InlineKeyboardButton("🔙 Admin",      callback_data="admin_back")],
        ]
        await query.edit_message_text(
            f"✏️ *Prono #{prono_id}* — Nouveau résultat ?",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("set_result_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        parts = data.split("_")
        prono_id = int(parts[2])
        etat = parts[3]
        mapping = {"gagne": "✅ Gagné", "perdu": "❌ Perdu", "attente": "⏳ En attente"}
        await db.update_resultat(prono_id, mapping[etat])
        await query.edit_message_text(
            f"✅ Résultat du prono #{prono_id} mis à jour : *{mapping[etat]}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_valider_vip":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        paiements = await db.get_paiements_attente()
        if not paiements:
            await query.edit_message_text(
                "💳 *Aucun paiement en attente.*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
            return
        boutons = []
        for p in paiements:
            label = f"#{p['id']} — @{p['username'] or p['user_id']} — {p['montant']}€"
            boutons.append([InlineKeyboardButton(label, callback_data=f"valider_paiement_{p['id']}")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        await query.edit_message_text(
            "💳 *Paiements en attente :*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("valider_paiement_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        paiement_id = int(data.split("_")[2])
        paiement = await db.get_paiement(paiement_id)
        if paiement:
            await db.valider_paiement(paiement_id)
            montant = paiement.get("montant", 10)
            if montant <= 3:
                duree = PLANS["hebdomadaire"]["duree"]
                plan_label = "7 jours (hebdomadaire)"
            else:
                duree = PLANS["mensuel"]["duree"]
                plan_label = "30 jours (mensuel)"
            await db.extend_vip(paiement["user_id"], duree)
            try:
                await ctx.bot.send_message(
                    paiement["user_id"],
                    f"🎉 *Ton accès VIP a été activé !*\n\n"
                    f"✅ Plan : *{plan_label}*\n"
                    f"Tu as maintenant accès à tous les pronos VIP.\n"
                    f"Tape /start pour accéder à l'espace VIP. 🏆",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await query.edit_message_text(
                f"✅ VIP activé pour l'utilisateur {paiement['user_id']} — {plan_label} !",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
        else:
            await query.edit_message_text("❌ Paiement introuvable.")

    elif data == "admin_remove_vip":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        vip_users = await db.get_vip_users_details()
        if not vip_users:
            await query.edit_message_text(
                "❌ *Retirer un VIP*\n\n📭 Aucun membre VIP actif.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
            return
        boutons = []
        for u in vip_users:
            nom = u.get("first_name") or u.get("username") or str(u["id"])
            try:
                exp = datetime.fromisoformat(u["vip_until"]).strftime("%d/%m/%Y")
            except Exception:
                exp = "?"
            label = f"❌ {nom[:20]} — expire {exp}"
            boutons.append([InlineKeyboardButton(label, callback_data=f"remove_vip_{u['id']}")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        await query.edit_message_text(
            "❌ *Retirer un VIP — Choisir l'utilisateur :*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons),
        )

    elif data.startswith("remove_vip_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        target_id = int(data.split("_")[2])
        await db.remove_vip(target_id)
        await query.edit_message_text(
            f"✅ VIP retiré pour l'utilisateur `{target_id}`.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_list_pronos":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        pronos = await db.get_pronos(limit=15)
        if not pronos:
            texte = "📋 *Aucun prono enregistré.*"
        else:
            texte = "📋 *Liste des 15 derniers pronos :*\n\n"
            for p in pronos:
                er = resultat_emoji(p["resultat"])
                es = sport_emoji(p["sport"])
                tl = type_label(p.get("type_prono") or "SAFE")
                texte += f"{er} {es} *[{p['id']}]* {p['match'][:22]}\n   📅 {p['date_match']} | {tl}\n\n"
        boutons = [[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

    elif data == "admin_delete_prono":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        pronos = await db.get_pronos(limit=15)
        if not pronos:
            await query.edit_message_text("📭 Aucun prono à supprimer.")
            return
        boutons = []
        for p in pronos:
            label = f"🗑️ [{p['id']}] {p['match'][:25]} — {p['date_match']}"
            boutons.append([InlineKeyboardButton(label, callback_data=f"delete_prono_{p['id']}")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        await query.edit_message_text(
            "🗑️ *Quel prono supprimer ?*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons)
        )

    elif data.startswith("delete_prono_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        prono_id = int(data.split("_")[2])
        boutons = [
            [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"confirm_delete_{prono_id}")],
            [InlineKeyboardButton("❌ Annuler",        callback_data="admin_delete_prono")],
        ]
        await query.edit_message_text(
            f"⚠️ *Confirmer la suppression du prono #{prono_id} ?*\n\n"
            f"Cette action est irréversible.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons),
        )

    elif data.startswith("confirm_delete_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        prono_id = int(data.split("_")[2])
        await db.delete_prono(prono_id)
        await query.edit_message_text(
            f"✅ Prono #{prono_id} supprimé.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_add_vip_manual":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        ctx.user_data["action"] = "add_vip_manual"
        await query.edit_message_text(
            "👑 *Ajouter un VIP manuellement*\n\n"
            "Envoie le *@username* Telegram de la personne :\n\n"
            "_La personne doit avoir démarré le bot au moins une fois._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data="admin_back")]]),
        )

    elif data.startswith("admin_vip_dur_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        parts = data.split("_")
        duree = int(parts[3])
        target_id = int(parts[4])
        target_name = ctx.user_data.get("vip_target_name", "")
        target_username = ctx.user_data.get("vip_target_username", "")
        await db.extend_vip(target_id, duree)
        ctx.user_data.pop("vip_target_id", None)
        ctx.user_data.pop("vip_target_name", None)
        ctx.user_data.pop("vip_target_username", None)
        plan_label = f"{duree} jours"
        try:
            await query.bot.send_message(
                target_id,
                f"🎉 *Ton accès VIP a été activé !*\n\n"
                f"✅ Plan : *{plan_label}*\n"
                f"Tu as maintenant accès à tous les pronos VIP.\n"
                f"Tape /start pour accéder à l'espace VIP. 🏆",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await query.edit_message_text(
            f"✅ *VIP activé !*\n\n"
            f"👤 {target_name} (@{target_username})\n"
            f"⏱️ Durée : *{plan_label}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_broadcast":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        ctx.user_data["action"] = "broadcast"
        await query.edit_message_text(
            "📢 *Broadcast*\n\nEnvoie le message à diffuser à tous les membres :",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_bilan":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        today = datetime.now().strftime("%d/%m/%Y")
        ctx.user_data["action"] = "bilan_date"
        await query.edit_message_text(
            f"📊 *Bilan journalier*\n\nEnvoie la date au format *JJ/MM/AAAA*\n_Ex : {today}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )

    elif data == "admin_reset_stats":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        ctx.user_data["action"] = "confirm_reset_stats"
        await query.edit_message_text(
            "⚠️ *Réinitialiser TOUS les pronos ?*\n\n"
            "Cette action supprimera *définitivement* tous les pronos. Elle est *irréversible* !\n\n"
            "Pour confirmer, tape exactement : *SUPPRIMER TOUT*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data="admin_back")]]),
        )

    elif data.startswith("view_photo_"):
        prono_id = int(data.split("_")[2])
        pronos = await db.get_pronos(limit=50)
        prono = next((p for p in pronos if p["id"] == prono_id), None)
        if prono and prono.get("photo_id"):
            await ctx.bot.send_photo(
                chat_id=query.from_user.id,
                photo=prono["photo_id"],
                caption=f"📷 {prono['match']} — {prono['prono']}"
            )
        else:
            await query.answer("📷 Photo introuvable.", show_alert=True)

    elif data == "admin_promos":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        codes = await db.list_promo_codes()
        boutons = []
        if codes:
            for c in codes:
                uses_txt = f"{c['uses_count']}/{c['max_uses']}" if c['max_uses'] > 0 else f"{c['uses_count']}/∞"
                label = f"🗑️ {c['code']} — {c['jours']}j — {uses_txt} utilisations"
                boutons.append([InlineKeyboardButton(label, callback_data=f"promo_del_{c['code']}")])
        boutons.append([InlineKeyboardButton("➕ Créer un code promo", callback_data="promo_create")])
        boutons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_back")])
        texte = (
            "🎟️ *Codes promo actifs :*\n\n"
            "_Clique sur un code pour le supprimer._"
            if codes else
            "🎟️ *Aucun code promo actif.*"
        )
        await query.edit_message_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

    elif data == "promo_create":
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        ctx.user_data["action"] = "promo_create"
        ctx.user_data["etape"] = "code"
        await query.edit_message_text(
            "🎟️ *Créer un code promo*\n\n"
            "1️⃣ Envoie le *code* (ex : SUMMER2025) :",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data="admin_promos")]]),
        )

    elif data.startswith("promo_del_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        code = data.split("promo_del_", 1)[1]
        boutons = [
            [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"promo_confirm_del_{code}")],
            [InlineKeyboardButton("❌ Annuler",        callback_data="admin_promos")],
        ]
        await query.edit_message_text(
            f"⚠️ *Supprimer le code `{code}` ?*\n\nIl ne sera plus utilisable.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons),
        )

    elif data.startswith("promo_confirm_del_"):
        if not is_admin_session(ctx):
            await query.answer("⛔", show_alert=True)
            return
        code = data.split("promo_confirm_del_", 1)[1]
        await db.delete_promo_code(code)
        await query.edit_message_text(
            f"✅ Code `{code}` supprimé.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Codes promo", callback_data="admin_promos")]]),
        )


async def parrain_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username or "", user.first_name or "")
    nb = await db.get_referral_count(user.id)
    lien = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"
    texte = (
        f"🤝 *Parrainage PronosBot*\n\n"
        f"Partage ton lien et gagne *{PARRAIN_BONUS_JOURS} jours VIP* pour chaque ami qui rejoint !\n\n"
        f"🔗 *Ton lien de parrainage :*\n`{lien}`\n\n"
        f"👥 Amis parrainés : *{nb}*\n"
        f"🎁 Jours VIP gagnés : *{nb * PARRAIN_BONUS_JOURS}*"
    )
    boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
    await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def statut_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username or "", user.first_name or "")

    vip = await db.is_vip(user.id)
    nb_parrains = await db.get_referral_count(user.id)
    jours_vip_parrain = nb_parrains * PARRAIN_BONUS_JOURS

    if vip:
        vip_details = await db.get_vip_users_details()
        vip_until_str = "?"
        for u in vip_details:
            if u["id"] == user.id:
                try:
                    vip_dt = datetime.fromisoformat(u["vip_until"])
                    jours_restants = (vip_dt - datetime.now()).days
                    vip_until_str = f"{vip_dt.strftime('%d/%m/%Y')} (*{jours_restants} jour(s) restant(s)*)"
                except Exception:
                    vip_until_str = u.get("vip_until", "?")
                break
        statut_ligne = f"⭐ *VIP actif*\n📅 Expire le : {vip_until_str}"
    else:
        statut_ligne = "👤 *Membre gratuit*\n_Passe VIP pour accéder à tous les pronos !_"

    texte = (
        f"📋 *Ton statut PronosBot*\n\n"
        f"👤 {user.first_name}"
        + (f" (@{user.username})" if user.username else "") + "\n"
        f"🆔 ID : `{user.id}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{statut_ligne}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤝 *Parrainage :*\n"
        f"👥 Amis parrainés : *{nb_parrains}*\n"
        f"🎁 Jours VIP gagnés via parrainage : *{jours_vip_parrain}*"
    )
    boutons = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
    await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))


async def _payer_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE, montant: float, plan_label: str):
    user = update.effective_user
    await db.add_user(user.id, user.username or "", user.first_name or "")
    await db.add_paiement(user.id, user.username or "", montant)
    try:
        await ctx.bot.send_message(
            ADMIN_TELEGRAM_ID,
            f"💳 *Nouveau paiement en attente !*\n\n"
            f"👤 {user.first_name} (@{user.username})\n"
            f"🆔 ID : `{user.id}`\n"
            f"💰 Montant : {montant}€ — {plan_label}\n\n"
            f"➡️ Valide-le dans le panel admin.",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await update.message.reply_text(
        "✅ *Notification de paiement envoyée !*\n\n"
        f"Plan choisi : *{plan_label}*\n"
        "Ton accès VIP sera activé sous 24h après vérification.\n"
        "Merci pour ta confiance ! 🙏",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]),
    )


async def promo_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username or "", user.first_name or "")
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "🎟️ *Code promo*\n\n"
            "Utilise la commande avec ton code :\n"
            "`/promo TONCODE`",
            parse_mode="Markdown",
        )
        return
    code = args[0].strip().upper()
    result = await db.use_promo_code(user.id, code)
    if result["ok"]:
        await update.message.reply_text(
            f"🎉 *Code promo validé !*\n\n"
            f"✅ *{result['jours']} jours VIP* ont été ajoutés à ton compte.\n"
            f"Tape /start pour accéder à l'espace VIP. 🏆",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]),
        )
    else:
        await update.message.reply_text(
            f"❌ *Code refusé*\n\n_{result['raison']}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]),
        )


async def payer_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 *Choisir ton abonnement VIP :*\n\n"
        "🗓️ Tape `/payer3` pour l'abonnement *3€ / 7 jours*\n"
        "📅 Tape `/payer10` pour l'abonnement *10€ / 30 jours*",
        parse_mode="Markdown",
    )


async def payer3_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _payer_handler(update, ctx, montant=3.0, plan_label="Hebdomadaire (7 jours)")


async def payer10_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _payer_handler(update, ctx, montant=10.0, plan_label="Mensuel (30 jours)")


async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    action = ctx.user_data.get("action")
    etape = ctx.user_data.get("etape")

    if action == "admin_login":
        if text == ADMIN_PASSWORD:
            ctx.user_data["admin_authenticated"] = True
            ctx.user_data.pop("action", None)
            await update.message.reply_text(
                "✅ *Connexion admin réussie !*",
                parse_mode="Markdown"
            )
            nb_users = await db.count_users()
            nb_vip = await db.count_vip()
            nb_attente = await db.count_paiements_attente()
            texte = (
                f"🔧 *Panel Admin*\n\n"
                f"👥 Membres : *{nb_users}* | ⭐ VIP actifs : *{nb_vip}*\n"
                f"💳 Paiements en attente : *{nb_attente}*\n\n"
                f"Que veux-tu faire ?"
            )
            boutons = [
                [InlineKeyboardButton("➕ Poster prono VIP",          callback_data="admin_add_prono")],
                [InlineKeyboardButton("🎁 Définir prono gratuit",    callback_data="admin_set_gratuit")],
                [InlineKeyboardButton("✏️ Mettre à jour résultat",   callback_data="admin_update_result")],
                [InlineKeyboardButton("💳 Valider un paiement VIP",  callback_data="admin_valider_vip")],
                [InlineKeyboardButton("👑 Ajouter VIP manuellement", callback_data="admin_add_vip_manual")],
                [InlineKeyboardButton("❌ Retirer un VIP",           callback_data="admin_remove_vip")],
                [InlineKeyboardButton("📋 Liste des pronos",         callback_data="admin_list_pronos")],
                [InlineKeyboardButton("🗑️ Supprimer un prono",      callback_data="admin_delete_prono")],
                [InlineKeyboardButton("📢 Broadcast",                callback_data="admin_broadcast")],
                [InlineKeyboardButton("📊 Bilan journalier",         callback_data="admin_bilan")],
                [InlineKeyboardButton("🔄 Réinitialiser les stats",  callback_data="admin_reset_stats")],
                [InlineKeyboardButton("🎟️ Codes promo",              callback_data="admin_promos")],
                [InlineKeyboardButton("🚪 Déconnexion admin",        callback_data="admin_logout")],
                [InlineKeyboardButton("🔙 Menu",                     callback_data="menu")],
            ]
            await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))
        else:
            await update.message.reply_text("❌ Mot de passe incorrect. Réessaie.")
        return

    if action == "add_prono":
        sport = ctx.user_data.get("prono_sport", "")
        is_gratuit = ctx.user_data.get("prono_is_gratuit", False)
        type_prono = ctx.user_data.get("prono_type", "SAFE")

        if etape == "match":
            ctx.user_data["prono_match"] = text
            ctx.user_data["etape"] = "date"
            await update.message.reply_text(
                f"✅ Match : *{text}*\n\n📅 Date du match ?\n_Ex : 18/05/2025 21:00_",
                parse_mode="Markdown"
            )

        elif etape == "date":
            ctx.user_data["prono_date"] = text
            ctx.user_data["etape"] = "prono"
            await update.message.reply_text(
                f"✅ Date : *{text}*\n\n🎯 Le prono ?\n_Ex : 1 (victoire domicile) | Over 2.5 | etc._",
                parse_mode="Markdown"
            )

        elif etape == "prono":
            ctx.user_data["prono_prono"] = text
            if is_gratuit:
                ctx.user_data["prono_cote"] = "N/A"
                ctx.user_data["prono_mise"] = "N/A"
                ctx.user_data["etape"] = "analyse"
                await update.message.reply_text(
                    f"✅ Prono : *{text}*\n\n📋 Écris l'analyse du prono :\n_Ex : L'équipe est en grande forme, défense solide..._",
                    parse_mode="Markdown"
                )
            else:
                ctx.user_data["etape"] = "cote"
                await update.message.reply_text(
                    f"✅ Prono : *{text}*\n\n💰 La cote ?\n_Ex : 1.85_",
                    parse_mode="Markdown"
                )

        elif etape == "analyse":
            ctx.user_data["prono_analyse"] = text
            ctx.user_data["etape"] = "confirm"
            match = ctx.user_data.get("prono_match", "")
            date = ctx.user_data.get("prono_date", "")
            prono_val = ctx.user_data.get("prono_prono", "")
            es = sport_emoji(sport)
            texte = (
                f"📋 *Récap du prono gratuit :*\n\n"
                f"{es} *{match}*\n"
                f"📅 {date}\n"
                f"🎯 {prono_val}\n"
                f"📋 Analyse : _{text}_\n\n"
                f"Confirmer ?"
            )
            boutons = [
                [InlineKeyboardButton("✅ Confirmer", callback_data="confirm_prono")],
                [InlineKeyboardButton("❌ Annuler",   callback_data="admin_back")],
            ]
            await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

        elif etape == "cote":
            ctx.user_data["prono_cote"] = text
            ctx.user_data["etape"] = "mise"
            await update.message.reply_text(
                f"✅ Cote : *{text}*\n\n💵 La mise (en unités) ?\n_Ex : 2_",
                parse_mode="Markdown"
            )

        elif etape == "mise":
            ctx.user_data["prono_mise"] = text
            ctx.user_data["etape"] = "confirm"
            match = ctx.user_data.get("prono_match", "")
            date = ctx.user_data.get("prono_date", "")
            prono_val = ctx.user_data.get("prono_prono", "")
            cote = ctx.user_data.get("prono_cote", "")
            es = sport_emoji(sport)
            te = type_emoji(type_prono)
            tl = type_label(type_prono)
            texte = (
                f"📋 *Récap du prono VIP :*\n\n"
                f"{es} *{match}*\n"
                f"📅 {date}\n"
                f"{te} {tl}\n"
                f"🎯 {prono_val} | 💰 Cote : {cote} | Mise : {text}u\n\n"
                f"Confirmer ?"
            )
            boutons = [
                [InlineKeyboardButton("✅ Confirmer", callback_data="confirm_prono")],
                [InlineKeyboardButton("❌ Annuler",   callback_data="admin_back")],
            ]
            await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))

        elif etape == "photo":
            await update.message.reply_text("📷 Envoie la photo directement (pas un texte).")
        return

    if action == "add_vip_manual":
        if not is_admin_session(ctx):
            return
        username_input = text.strip()
        user_found = await db.get_user_by_username(username_input)
        if not user_found:
            await update.message.reply_text(
                f"❌ *Utilisateur introuvable.*\n\n"
                f"Aucun compte avec le username `{username_input}` n'a démarré le bot.\n\n"
                f"La personne doit taper /start dans le bot au moins une fois.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
            ctx.user_data.clear()
            return
        target_id = user_found["id"]
        target_first = user_found.get("first_name", "")
        target_uname = user_found.get("username", "")
        vip_until = user_found.get("vip_until")
        ctx.user_data["vip_target_id"] = target_id
        ctx.user_data["vip_target_name"] = target_first
        ctx.user_data["vip_target_username"] = target_uname
        ctx.user_data.pop("action", None)
        statut = ""
        if vip_until:
            try:
                vip_dt = datetime.fromisoformat(vip_until)
                if vip_dt > datetime.now():
                    statut = f"\n⭐ VIP actif jusqu'au *{vip_dt.strftime('%d/%m/%Y')}*"
                else:
                    statut = "\n❌ VIP expiré"
            except Exception:
                pass
        boutons = [
            [
                InlineKeyboardButton("🗓️ 7 jours",  callback_data=f"admin_vip_dur_7_{target_id}"),
                InlineKeyboardButton("📅 30 jours", callback_data=f"admin_vip_dur_30_{target_id}"),
            ],
            [InlineKeyboardButton("🔙 Annuler", callback_data="admin_back")],
        ]
        await update.message.reply_text(
            f"👤 *Utilisateur trouvé !*\n\n"
            f"Prénom : *{target_first}*\n"
            f"Username : @{target_uname}{statut}\n\n"
            f"Quelle durée VIP veux-tu ajouter ?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(boutons),
        )
        return

    if action == "broadcast":
        users = await db.get_all_users()
        ctx.user_data.clear()
        success = 0
        fail = 0
        for uid in users:
            try:
                await ctx.bot.send_message(uid, text, parse_mode="Markdown")
                success += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(
            f"📢 *Broadcast envoyé !*\n\n✅ {success} reçus | ❌ {fail} échecs",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )
        return

    if action == "bilan_date":
        ctx.user_data.clear()
        await show_bilan_journalier_msg(update, ctx, text.strip())
        return

    if action == "promo_create":
        if not is_admin_session(ctx):
            return
        etape = ctx.user_data.get("etape")
        if etape == "code":
            ctx.user_data["promo_code"] = text.strip().upper()
            ctx.user_data["etape"] = "jours"
            await update.message.reply_text(
                f"✅ Code : *{ctx.user_data['promo_code']}*\n\n"
                "2️⃣ Combien de *jours VIP* ce code offre-t-il ?\n_Ex : 7_",
                parse_mode="Markdown",
            )
        elif etape == "jours":
            try:
                jours = int(text.strip())
                if jours <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Entrez un nombre valide de jours (ex : 7).")
                return
            ctx.user_data["promo_jours"] = jours
            ctx.user_data["etape"] = "max_uses"
            await update.message.reply_text(
                f"✅ Durée : *{jours} jours*\n\n"
                "3️⃣ Nombre *maximum d'utilisations* (0 = illimité) :\n_Ex : 50_",
                parse_mode="Markdown",
            )
        elif etape == "max_uses":
            try:
                max_uses = int(text.strip())
                if max_uses < 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Entrez un nombre valide (0 pour illimité).")
                return
            code = ctx.user_data.get("promo_code", "")
            jours = ctx.user_data.get("promo_jours", 0)
            ctx.user_data.clear()
            ctx.user_data["admin_authenticated"] = True
            try:
                await db.add_promo_code(code, jours, max_uses)
                uses_txt = "illimitées" if max_uses == 0 else f"max {max_uses}"
                await update.message.reply_text(
                    f"✅ *Code promo créé !*\n\n"
                    f"🎟️ Code : `{code}`\n"
                    f"⏱️ Durée : *{jours} jours VIP*\n"
                    f"👥 Utilisations : *{uses_txt}*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Codes promo", callback_data="admin_promos")]]),
                )
            except Exception:
                await update.message.reply_text(
                    f"❌ Ce code existe déjà. Choisis un autre nom.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Codes promo", callback_data="admin_promos")]]),
                )
        return

    if action == "confirm_reset_stats":
        if text.strip() == "SUPPRIMER TOUT":
            ctx.user_data.clear()
            await db.reset_stats()
            await update.message.reply_text(
                "✅ *Tous les pronos ont été supprimés.*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
        else:
            await update.message.reply_text(
                "❌ Texte incorrect. Tape exactement *SUPPRIMER TOUT* pour confirmer, ou clique Annuler.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data="admin_back")]]),
            )
        return


async def show_bilan_journalier_msg(update: Update, ctx, date_str: str):
    pronos = await db.get_pronos_by_date(date_str)
    lines = []
    total_bk = 0.0
    pending = 0
    resolved = 0
    for p in pronos:
        t = p.get("type_prono") or "SAFE"
        te = type_emoji(t)
        tl = type_label(t)
        mise_bk = BK_MISE.get(t, 1.0)
        res = p.get("resultat", "⏳ En attente")
        try:
            cote = float(str(p["cote"]).replace(",", "."))
        except Exception:
            cote = 1.0
        nom = md_safe(p["match"][:32])
        if res == "✅ Gagné":
            profit = round(mise_bk * (cote - 1), 2)
            total_bk += profit
            resolved += 1
            lines.append(f"✅ {te} *{nom}*\n   _{tl} | cote {p['cote']}_ → *+{profit:.2f}% BK*")
        elif res == "❌ Perdu":
            profit = -mise_bk
            total_bk += profit
            resolved += 1
            lines.append(f"❌ {te} *{nom}*\n   _{tl}_ → *{profit:.2f}% BK*")
        else:
            pending += 1
            lines.append(f"⏳ {te} *{nom}*\n   _{tl}_ — en attente")

    total_bk = round(total_bk, 2)
    signe = "+" if total_bk >= 0 else ""
    if resolved == 0 and not pending:
        verdict = "📭 Aucun prono VIP ce jour."
    elif resolved == 0:
        verdict = "⏳ Tous les pronos sont en attente."
    elif total_bk > 0:
        verdict = f"🟢 Journée positive : *{signe}{total_bk:.2f}% BK* gagné !"
    elif total_bk < 0:
        verdict = f"🔴 Journée négative : *{total_bk:.2f}% BK* perdu."
    else:
        verdict = "⚪ Journée nulle : *0.00% BK*."

    texte = f"📊 *Bilan VIP — {md_safe(date_str)}*\n\n"
    texte += "\n\n".join(lines) if lines else "_Aucun prono VIP ce jour._"
    texte += f"\n\n{'─'*28}\n{verdict}"
    if pending:
        texte += f"\n_({pending} prono(s) encore en attente)_"

    boutons = [[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]
    try:
        await update.message.reply_text(texte, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(boutons))
    except Exception:
        await update.message.reply_text(texte, reply_markup=InlineKeyboardMarkup(boutons))


async def photo_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin_session(ctx):
        return
    action = ctx.user_data.get("action")
    etape = ctx.user_data.get("etape")
    if action == "add_prono" and etape == "photo":
        photo_id = update.message.photo[-1].file_id
        prono_id = ctx.user_data.get("last_prono_id")
        if prono_id:
            await db.update_photo_id(prono_id, photo_id)
            ctx.user_data.clear()
            await update.message.reply_text(
                "✅ Photo enregistrée !",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
            )
        else:
            await update.message.reply_text("❌ Erreur : prono introuvable.")


async def confirm_prono_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin_session(ctx):
        await query.answer("⛔", show_alert=True)
        return

    sport = ctx.user_data.get("prono_sport", "")
    match = ctx.user_data.get("prono_match", "")
    date = ctx.user_data.get("prono_date", "")
    prono_val = ctx.user_data.get("prono_prono", "")
    cote = ctx.user_data.get("prono_cote", "N/A")
    mise = ctx.user_data.get("prono_mise", "N/A")
    type_prono = ctx.user_data.get("prono_type", "SAFE")
    is_gratuit = ctx.user_data.get("prono_is_gratuit", False)
    analyse = ctx.user_data.get("prono_analyse", "")

    prono_id = await db.add_prono(sport, match, date, prono_val, cote, mise, type_prono, analyse, created_as_gratuit=is_gratuit)

    if is_gratuit:
        await db.set_prono_gratuit(prono_id)
        ctx.user_data.clear()
        await query.edit_message_text(
            "✅ *Prono gratuit publié !*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
        )
    else:
        asyncio.create_task(notify_vip_new_prono(ctx.bot, {
            "sport": sport, "match": match, "date": date,
            "prono": prono_val, "type_prono": type_prono
        }))

        match_dt = parse_match_datetime(date)
        if match_dt:
            rappel_dt = match_dt - timedelta(hours=1)
            now = datetime.now()
            if rappel_dt > now:
                delay = (rappel_dt - now).total_seconds()
                ctx.application.job_queue.run_once(
                    rappel_match_job,
                    when=delay,
                    data={
                        "es": sport_emoji(sport), "match": match,
                        "date": date, "prono": prono_val
                    }
                )

        ctx.user_data["last_prono_id"] = prono_id
        ctx.user_data["action"] = "add_prono"
        ctx.user_data["etape"] = "photo"
        await query.edit_message_text(
            "✅ *Prono VIP publié !*\n\n"
            "📲 Notification envoyée à tous les abonnés VIP.\n\n"
            "📷 Veux-tu ajouter une photo d'analyse ?\nEnvoie une photo ou tape *skip* pour passer.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏩ Passer", callback_data="skip_photo")]]),
        )


async def skip_photo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text(
        "✅ Prono enregistré sans photo.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_back")]]),
    )


async def notify_vip_new_prono(bot, prono: dict):
    vip_users = await db.get_all_vip_users()
    es = sport_emoji(prono.get("sport", ""))
    te = type_emoji(prono.get("type_prono", "SAFE"))
    tl = type_label(prono.get("type_prono", "SAFE"))
    texte = (
        f"🔔 *Nouveau prono VIP publié !*\n\n"
        f"{es} *{prono['match']}*\n"
        f"📅 {prono['date']} | {te} {tl}\n"
        f"🎯 {prono['prono']}\n\n"
        f"_Ouvre le bot pour voir tous les détails._"
    )
    for uid in vip_users:
        try:
            await bot.send_message(uid, texte, parse_mode="Markdown")
        except Exception:
            pass
        await asyncio.sleep(0.05)


async def rappel_match_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    vip_users = await db.get_all_vip_users()
    texte = (
        f"⏰ *Rappel — Match dans 1 heure !*\n\n"
        f"{data['es']} *{data['match']}*\n"
        f"📅 {data['date']}\n"
        f"🎯 Prono : *{data['prono']}*\n\n"
        f"Bonne chance ! 🍀"
    )
    for uid in vip_users:
        try:
            await context.bot.send_message(uid, texte, parse_mode="Markdown")
        except Exception:
            pass
        await asyncio.sleep(0.05)


def parse_match_datetime(date_str: str):
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %Hh%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


async def check_vip_expiry(context: ContextTypes.DEFAULT_TYPE):
    users = await db.get_users_expiring_soon(days=3)
    for u in users:
        try:
            await context.bot.send_message(
                u["id"],
                "⚠️ *Ton abonnement VIP expire dans 3 jours !*\n\n"
                "Pour continuer à profiter des pronos VIP, renouvelle via PayPal.\n"
                f"💳 [Renouveler 10€]({PAYPAL_LINK})",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)


async def cleanup_expired_vip(context: ContextTypes.DEFAULT_TYPE):
    try:
        removed = await db.remove_expired_vip()
        if removed:
            logger.info(f"VIP expirés nettoyés : {removed} compte(s) mis à jour.")
    except Exception as e:
        logger.error(f"Erreur cleanup VIP expirés : {e}")


class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"PronosBot is running!")

    def log_message(self, format, *args):
        pass


def run_http_server():
    port = int(os.environ.get("PORT", 3000))
    server = HTTPServer(("0.0.0.0", port), KeepAliveHandler)
    logger.info(f"HTTP keep-alive server on port {port}")
    server.serve_forever()


async def post_init(application):
    await db.init_db()
    logger.info("Base de données initialisée.")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN manquant ! Ajoute-le dans les secrets Replit.")
        return

    threading.Thread(target=run_http_server, daemon=True).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("payer",   payer_command))
    app.add_handler(CommandHandler("payer3",  payer3_command))
    app.add_handler(CommandHandler("payer10", payer10_command))
    app.add_handler(CommandHandler("parrain", parrain_command))
    app.add_handler(CommandHandler("statut",  statut_command))
    app.add_handler(CommandHandler("promo",   promo_command))
    app.add_handler(CallbackQueryHandler(confirm_prono_callback, pattern="^confirm_prono$"))
    app.add_handler(CallbackQueryHandler(skip_photo_callback,    pattern="^skip_photo$"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_vip_expiry,   interval=86400, first=60)
        job_queue.run_daily(cleanup_expired_vip, time=datetime.strptime("03:00", "%H:%M").time())

    logger.info("PronosBot démarré !")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
