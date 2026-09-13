# ============================================================
#  ZENTRIX GENERATOR BOT — Railway edition
#  Stock menu UI: 2-column grid + pagination (like your sample)
#  Stock: drop .txt in stock/ (ZArchiver) OR upload via Telegram
# ============================================================

import os
import random
import sqlite3
import logging
import asyncio
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "123456789").split(",") if x.strip()]
STOCK_DIR = os.environ.get("STOCK_DIR", "stock")
DB_PATH   = os.environ.get("DB_PATH", "zentrix.db")
PORT      = int(os.environ.get("PORT", 8080))

TIERS = {
    "Premium":  3000,
    "Platinum": 2500,
}

STOCKS_PER_PAGE = 8   # 4 rows x 2 columns (like your picture)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("ZENTRIX")
os.makedirs(STOCK_DIR, exist_ok=True)

# ---------------- DATABASE ----------------
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY, username TEXT, tier TEXT,
    key_used TEXT, gens INTEGER DEFAULT 0, joined TEXT)""")
cur.execute("""CREATE TABLE IF NOT EXISTS keys(
    key TEXT PRIMARY KEY, tier TEXT, used_by INTEGER DEFAULT 0, created TEXT)""")
cur.execute("""CREATE TABLE IF NOT EXISTS stock_state(
    filename TEXT PRIMARY KEY, offset INTEGER DEFAULT 0)""")
db.commit()

# ---------------- HEALTH SERVER (Railway) ----------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ZENTRIX Generator is alive")
    def log_message(self, *a): pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health server on port {PORT}")
    server.serve_forever()

# ---------------- HELPERS ----------------
def is_admin(uid): return uid in ADMIN_IDS

def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def reg_user(uid, username):
    if not get_user(uid):
        cur.execute("INSERT INTO users(user_id,username,tier,gens,joined) VALUES(?,?,'None',0,?)",
                    (uid, username or "user", datetime.now().strftime("%Y-%m-%d %H:%M")))
        db.commit()

def user_tier(uid):
    u = get_user(uid)
    return u["tier"] if u else None

def gen_key(tier):
    while True:
        k = f"{tier}-{random.randint(100,999)}-{random.randint(100,999)}-{random.randint(100,999)}"
        cur.execute("SELECT 1 FROM keys WHERE key=?", (k,))
        if not cur.fetchone():
            return k

def fmt_count(n):
    """108 -> '108', 20900 -> '20.9K', 789000 -> '789.0K', 1500000 -> '1.5M'"""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)

def stock_files():
    try:
        return sorted(f for f in os.listdir(STOCK_DIR)
                      if f.lower().endswith(".txt") and os.path.isfile(os.path.join(STOCK_DIR, f)))
    except FileNotFoundError:
        return []

def stock_remaining(name):
    path = os.path.join(STOCK_DIR, name)
    if not os.path.isfile(path):
        return 0, 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        total = sum(1 for _ in f)
    cur.execute("SELECT offset FROM stock_state WHERE filename=?", (name,))
    row = cur.fetchone()
    used = row["offset"] if row else 0
    return max(total - used, 0), total

# ---------------- KEYBOARDS ----------------
def main_menu(uid):
    kb = [
        [InlineKeyboardButton("🎰 Generate TXT", callback_data="gen"),
         InlineKeyboardButton("🎟 Redeem Key",  callback_data="redeem")],
        [InlineKeyboardButton("📦 Stock",       callback_data="stock"),
         InlineKeyboardButton("👤 My Account",  callback_data="me")],
    ]
    if is_admin(uid):
        kb.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(kb)

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Gen Key",       callback_data="ad_genkey"),
         InlineKeyboardButton("📤 Add Stock",     callback_data="ad_addstock")],
        [InlineKeyboardButton("🚫 Revoke Access", callback_data="ad_revoke"),
         InlineKeyboardButton("🔍 Check User",    callback_data="ad_check")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ])

def back_home():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]])

def stock_picker_kb(page=0):
    """2-column stock grid with counts + Next/Prev page + Main Menu (like your picture)."""
    files = stock_files()
    total_pages = max((len(files) + STOCKS_PER_PAGE - 1) // STOCKS_PER_PAGE, 1)
    page = max(0, min(page, total_pages - 1))
    chunk = files[page*STOCKS_PER_PAGE:(page+1)*STOCKS_PER_PAGE]

    kb = []
    for i in range(0, len(chunk), 2):
        row = []
        for name in chunk[i:i+2]:
            label = os.path.splitext(name)[0].upper()
            rem, _ = stock_remaining(name)
            row.append(InlineKeyboardButton(f"📮 {label} ({fmt_count(rem)})",
                                            callback_data=f"pick:{name}"))
        kb.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev Page", callback_data=f"page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ Next Page", callback_data=f"page:{page+1}"))
    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
    return InlineKeyboardMarkup(kb)

# ---------------- TEXTS ----------------
START_TEXT = """𝙂𝙤𝙤𝙙 𝙙𝙖𝙮, 𝙪𝙨𝙚𝙧.

𝙏𝙝𝙞𝙨 𝙞𝙨 𝙕𝙀𝙉𝙏𝙍𝙄𝙓 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙤𝙧 —
𝙖 𝙩𝙚𝙭𝙩-𝙗𝙖𝙨𝙚𝙙 𝙖𝙘𝙘𝙤𝙪𝙣𝙩 𝙜𝙚𝙣𝙚𝙧𝙖𝙩𝙞𝙤𝙣 𝙩𝙤𝙤𝙡.

𝙔𝙤𝙪 𝙘𝙖𝙣 𝙜𝙚𝙣𝙚𝙧𝙖𝙩𝙚 𝙖𝙘𝙘𝙤𝙪𝙣𝙩𝙨 𝙝𝙚𝙧𝙚
𝙬𝙞𝙩𝙝 𝙛𝙖𝙨𝙩 𝙥𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜 𝙖𝙣𝙙 𝙛𝙧𝙚𝙨𝙝 𝙤𝙪𝙩𝙥𝙪𝙩.

𝙆𝙚𝙮 𝙛𝙚𝙖𝙩𝙪𝙧𝙚𝙨:
• 𝙁𝙖𝙨𝙩 𝙜𝙚𝙣𝙚𝙧𝙖𝙩𝙞𝙤𝙣
• 𝘼𝙡𝙬𝙖𝙮𝙨 𝙛𝙧𝙚𝙨𝙝 𝙙𝙖𝙩𝙖
• 𝙉𝙤 𝙙𝙪𝙥𝙡𝙞𝙘𝙖𝙩𝙚𝙙 𝙡𝙞𝙣𝙚𝙨

𝙀𝙣𝙨𝙪𝙧𝙚 𝙧𝙚𝙡𝙞𝙖𝙗𝙞𝙡𝙞𝙩𝙮 𝙖𝙣𝙙 𝙚𝙛𝙛𝙞𝙘𝙞𝙚𝙣𝙘𝙮
𝙬𝙞𝙩𝙝 𝙚𝙫𝙚𝙧𝙮 𝙧𝙚𝙦𝙪𝙚𝙨𝙩.

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

𝙕𝙀𝙉𝙏𝙍𝙄𝙓  —  𝙋𝙧𝙚𝙘𝙞𝙨𝙞𝙤𝙣. 𝙎𝙥𝙚𝙚𝙙. 𝙌𝙪𝙖𝙡𝙞𝙩𝙮."""

pending = {}

# ---------------- USER COMMANDS ----------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg_user(update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(START_TEXT, reply_markup=main_menu(update.effective_user.id))

async def redeem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg_user(update.effective_user.id, update.effective_user.username)
    if not ctx.args:
        pending[update.effective_user.id] = {"action": "redeem"}
        await update.message.reply_text(
            "🎟 𝙎𝙚𝙣𝙙 𝙮𝙤𝙪𝙧 𝙠𝙚𝙮 𝙣𝙤𝙬:\n\nExample:\n`Premium-123-456-789`",
            parse_mode="Markdown", reply_markup=back_home())
        return
    await do_redeem(update, ctx, ctx.args[0].strip())

async def do_redeem(update, ctx, key):
    uid = update.effective_user.id
    reg_user(uid, update.effective_user.username)
    cur.execute("SELECT * FROM keys WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return await update.message.reply_text("❌ 𝙄𝙣𝙫𝙖𝙡𝙞𝙙 𝙠𝙚𝙮.", reply_markup=back_home())
    if row["used_by"]:
        return await update.message.reply_text("❌ 𝙆𝙚𝙮 𝙖𝙡𝙧𝙚𝙖𝙙𝙮 𝙧𝙚𝙙𝙚𝙚𝙢𝙚𝙙.", reply_markup=back_home())
    cur.execute("UPDATE keys SET used_by=? WHERE key=?", (uid, key))
    cur.execute("UPDATE users SET tier=?, key_used=? WHERE user_id=?", (row["tier"], key, uid))
    db.commit()
    pending.pop(uid, None)
    await update.message.reply_text(
        f"✅ 𝙆𝙚𝙮 𝙧𝙚𝙙𝙚𝙚𝙢𝙚𝙙!\n\n𝙏𝙞𝙚𝙧: {row['tier']}\n"
        f"𝙇𝙞𝙣𝙚𝙨 𝙥𝙚𝙧 𝙜𝙚𝙣: {TIERS[row['tier']]}\n\n𝙔𝙤𝙪 𝙘𝙖𝙣 𝙣𝙤𝙬 𝙜𝙚𝙣𝙚𝙧𝙖𝙩𝙚.",
        reply_markup=main_menu(uid))

async def stock_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    files = stock_files()
    if not files:
        return await update.message.reply_text(
            "📦 𝙎𝙩𝙤𝙘𝙠 𝙞𝙨 𝙚𝙢𝙥𝙩𝙮.", reply_markup=back_home())
    msg = "📦 𝘼𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝙎𝙩𝙤𝙘𝙠:\n\n"
    for f in files:
        rem, total = stock_remaining(f)
        msg += f"• {f} — {fmt_count(rem)}/{fmt_count(total)} lines\n"
    await update.message.reply_text(msg, reply_markup=back_home())

async def me_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        return await start(update, ctx)
    await update.message.reply_text(
        "👤 𝙈𝙮 𝘼𝙘𝙘𝙤𝙪𝙣𝙩\n\n"
        f"𝙐𝙨𝙚𝙧: @{u['username']}\n𝙏𝙞𝙚𝙧: {u['tier']}\n"
        f"𝙆𝙚𝙮: {u['key_used'] or '—'}\n𝙏𝙤𝙩𝙖𝙡 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙞𝙤𝙣𝙨: {u['gens']}",
        reply_markup=back_home())

# ---------------- GENERATION ----------------
async def gen_start(update, ctx, uid, msg, page=0):
    tier = user_tier(uid)
    if not tier or tier == "None":
        return await msg.reply_text(
            "🔒 𝙔𝙤𝙪 𝙣𝙚𝙚𝙙 𝙩𝙤 𝙧𝙚𝙙𝙚𝙚𝙢 𝙖 𝙠𝙚𝙮 𝙛𝙞𝙧𝙨𝙩.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎟 Redeem Key", callback_data="redeem")]]))
    if not stock_files():
        return await msg.reply_text("📦 𝙉𝙤 𝙨𝙩𝙤𝙘𝙠 𝙖𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚.", reply_markup=back_home())
    await msg.reply_text("🎰 𝙎𝙚𝙡𝙚𝙘𝙩 𝙨𝙩𝙤𝙘𝙠:", reply_markup=stock_picker_kb(page))

async def gen_file(update, ctx, uid, filename):
    tier = user_tier(uid)
    limit = TIERS[tier]
    rem, total = stock_remaining(filename)
    if rem <= 0:
        return await update.callback_query.message.reply_text(
            f"⚠️ `{filename}` is exhausted.", reply_markup=back_home())
    take = min(limit, rem)
    cur.execute("SELECT offset FROM stock_state WHERE filename=?", (filename,))
    row = cur.fetchone()
    offset = row["offset"] if row else 0
    with open(os.path.join(STOCK_DIR, filename), "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.rstrip("\n") for l in f.readlines()[offset:offset + take]]
    cur.execute("INSERT INTO stock_state(filename,offset) VALUES(?,?) "
                "ON CONFLICT(filename) DO UPDATE SET offset=offset+?",
                (filename, offset + take, take))
    cur.execute("UPDATE users SET gens=gens+1 WHERE user_id=?", (uid,))
    db.commit()

    outname = f"{os.path.splitext(filename)[0]}_{tier}_{uid}_{datetime.now().strftime('%H%M%S')}.txt"
    with open(outname, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(outname, "rb") as f:
        await update.callback_query.message.reply_document(
            document=f, filename=outname,
            caption=f"✅ 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙚𝙙!\n\n𝙏𝙞𝙚𝙧: {tier}\n𝙇𝙞𝙣𝙚𝙨: {len(lines)}\n𝙎𝙩𝙤𝙘𝙠: {filename}")
    os.remove(outname)

# ---------------- ADMIN ----------------
async def ad_genkey_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    pending[update.effective_user.id] = {"action": "genkey"}
    await update.message.reply_text(
        "🔑 𝙆𝙚𝙮 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙤𝙧\n\nSend in this format:\n`Premium 5`\n`Platinum 3`",
        parse_mode="Markdown")

async def ad_addstock_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    pending[update.effective_user.id] = {"action": "addstock"}
    await update.message.reply_text(
        "📤 𝘼𝙙𝙙 𝙎𝙩𝙤𝙘𝙠\n\nSend a `.txt` file (or ZIP) and it will be added to stock.")

async def ad_revoke_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if ctx.args:
        return await do_revoke(update, ctx, ctx.args[0])
    pending[update.effective_user.id] = {"action": "revoke"}
    await update.message.reply_text("🚫 𝙎𝙚𝙣𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿 𝙩𝙤 𝙧𝙚𝙫𝙤𝙠𝙚:")

async def do_revoke(update, ctx, target):
    uid = update.effective_user.id
    try:
        tid = int(target)
    except ValueError:
        return await update.message.reply_text("❌ 𝙄𝙣𝙫𝙖𝙡𝙞𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿.")
    cur.execute("UPDATE users SET tier='None', key_used=NULL WHERE user_id=?", (tid,))
    db.commit()
    pending.pop(uid, None)
    await update.message.reply_text(f"🚫 𝘼𝙘𝙘𝙚𝙨𝙨 𝙧𝙚𝙫𝙤𝙠𝙚𝙙 𝙛𝙤𝙧 `{tid}`.", parse_mode="Markdown")

async def ad_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if ctx.args:
        return await do_check(update, ctx, ctx.args[0])
    pending[update.effective_user.id] = {"action": "check"}
    await update.message.reply_text("🔍 𝙎𝙚𝙣𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿 𝙩𝙤 𝙘𝙝𝙚𝙘𝙠:")

async def do_check(update, ctx, target):
    uid = update.effective_user.id
    try:
        tid = int(target)
    except ValueError:
        return await update.message.reply_text("❌ 𝙄𝙣𝙫𝙖𝙡𝙞𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿.")
    u = get_user(tid)
    pending.pop(uid, None)
    if not u:
        return await update.message.reply_text("❌ 𝙐𝙨𝙚𝙧 𝙣𝙤𝙩 𝙛𝙤𝙪𝙣𝙙.")
    await update.message.reply_text(
        f"🔍 𝙐𝙨𝙚𝙧 𝙍𝙚𝙥𝙤𝙧𝙩\n\n𝙐𝙨𝙚𝙧: @{u['username']} (`{tid}`)\n"
        f"𝙏𝙞𝙚𝙧: {u['tier']}\n𝙆𝙚𝙮: {u['key_used'] or '—'}\n"
        f"𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙞𝙤𝙣𝙨: {u['gens']}", parse_mode="Markdown")

async def handle_stock_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin sends .txt file (or .zip) — save to stock/."""
    uid = update.effective_user.id
    doc = update.message.document
    name = doc.file_name or "stock.txt"
    if not name.lower().endswith((".txt", ".zip")):
        return await update.message.reply_text("❌ Only .txt or .zip files.")
    try:
        tgfile = await doc.get_file()
        dest = os.path.join(STOCK_DIR, os.path.basename(name))
        await tgfile.download_to_drive(dest)
        if name.lower().endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(dest) as z:
                z.extractall(STOCK_DIR)
            os.remove(dest)
        pending.pop(uid, None)
        await update.message.reply_text(
            f"✅ 𝙎𝙩𝙤𝙘𝙠 𝙖𝙙𝙙𝙚𝙙: {name}\n\nType /stock to view.",
            reply_markup=back_home())
    except Exception as e:
        await update.message.reply_text(f"❌ Upload failed: {e}")

# ---------------- CALLBACKS ----------------
async def callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data

    if data == "home":
        reg_user(uid, q.from_user.username)
        await q.message.reply_text(START_TEXT, reply_markup=main_menu(uid))
    elif data == "redeem":
        pending[uid] = {"action": "redeem"}
        await q.message.reply_text(
            "🎟 𝙎𝙚𝙣𝙙 𝙮𝙤𝙪𝙧 𝙠𝙚𝙮 𝙣𝙤𝙬:\n\nExample:\n`Premium-123-456-789`",
            parse_mode="Markdown", reply_markup=back_home())
    elif data == "stock":
        await stock_cmd(update, ctx)
    elif data == "me":
        await me_cmd(update, ctx)
    elif data == "gen":
        await gen_start(update, ctx, uid, q.message)
    elif data.startswith("page:"):
        await gen_start(update, ctx, uid, q.message, page=int(data[5:]))
    elif data.startswith("pick:"):
        await gen_file(update, ctx, uid, data[5:])
    elif data == "admin":
        if is_admin(uid):
            await q.message.reply_text("🛠 𝘼𝙙𝙢𝙞𝙣 𝙋𝙖𝙣𝙚𝙡", reply_markup=admin_menu())
    elif data == "ad_genkey":
        pending[uid] = {"action": "genkey"}
        await q.message.reply_text(
            "🔑 𝙆𝙚𝙮 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙤𝙧\n\nSend in this format:\n`Premium 5`\n`Platinum 3`",
            parse_mode="Markdown")
    elif data == "ad_addstock":
        await ad_addstock_cmd(update, ctx)
    elif data == "ad_revoke":
        pending[uid] = {"action": "revoke"}
        await q.message.reply_text("🚫 𝙎𝙚𝙣𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿 𝙩𝙤 𝙧𝙚𝙫𝙤𝙠𝙚:")
    elif data == "ad_check":
        pending[uid] = {"action": "check"}
        await q.message.reply_text("🔍 𝙎𝙚𝙣𝙙 𝙪𝙨𝙚𝙧 𝙄𝘿 𝙩𝙤 𝙘𝙝𝙚𝙘𝙠:")

# ---------------- TEXT / FILE HANDLERS ----------------
async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = pending.get(uid)
    if not st:
        return
    txt = update.message.text.strip()

    if st["action"] == "redeem":
        await do_redeem(update, ctx, txt)
    elif st["action"] == "genkey" and is_admin(uid):
        parts = txt.split()
        if len(parts) != 2 or parts[0].capitalize() not in TIERS or not parts[1].isdigit():
            return await update.message.reply_text("❌ Format: `Premium 5`", parse_mode="Markdown")
        tier, count = parts[0].capitalize(), int(parts[1])
        keys = []
        for _ in range(count):
            k = gen_key(tier)
            cur.execute("INSERT INTO keys(key,tier,created) VALUES(?,?,?)",
                        (k, tier, datetime.now().strftime("%Y-%m-%d %H:%M")))
            keys.append(k)
        db.commit()
        pending.pop(uid, None)
        await update.message.reply_text("🔑 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙚𝙙 𝙆𝙚𝙮𝙨:\n\n" + "\n".join(keys))
    elif st["action"] == "revoke" and is_admin(uid):
        await do_revoke(update, ctx, txt)
    elif st["action"] == "check" and is_admin(uid):
        await do_check(update, ctx, txt)

async def file_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.document and is_admin(uid) and pending.get(uid, {}).get("action") == "addstock":
        await handle_stock_upload(update, ctx)

# ---------------- RUN ----------------
async def main_async():
    threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("redeem",   redeem_cmd))
    app.add_handler(CommandHandler("stock",    stock_cmd))
    app.add_handler(CommandHandler("me",       me_cmd))
    app.add_handler(CommandHandler("genkey",   ad_genkey_cmd))
    app.add_handler(CommandHandler("addstock", ad_addstock_cmd))
    app.add_handler(CommandHandler("revoke",   ad_revoke_cmd))
    app.add_handler(CommandHandler("check",    ad_check_cmd))
    app.add_handler(CommandHandler("generate", lambda u, c: gen_start(u, c, u.effective_user.id, u.message)))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.ATTACHMENT, file_handler))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("ZENTRIX Generator is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
  
