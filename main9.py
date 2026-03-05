import logging
import asyncio
import json
import binascii
import os
import sys
import urllib3
import threading
import time
import requests
import base64
import random
import html
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, Application, MessageHandler, filters
from telegram.request import HTTPXRequest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import aiohttp
from colorama import Fore, Style, init

# Initialize Colorama
init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= CONFIGURATION =================
# ⚠️ Yaha Dusre Bot (Bot B) ka Token dalein
BOT_TOKEN = "8019676929:AAF4ikptwlqbQYuOprsvEZ4dJyRirbYVNwI"   

ADMIN_ID = 7114540206  
PREMIUM_USERS = [7114540206]
OFFICIAL_GROUP_ID = -1003288356121 # Add Premium User IDs here
OFFICIAL_GROUP_LINK = "https://t.me/KAMOD_LIKE_GROUP"
CHANNEL_LINK = "@KAMOD_CODEX"
GROUP_LINK = "@KAMOD_LIKE_GROUP"
MUST_JOIN_CHANNELS = ["@KAMOD_CODEX", "@KAMOD_CODEX_BACKUP"]

# Files (Sirf Visit file ki jarurat hai)
OUTPUT_VISIT = "token_ind_visit.json"

# Usage Tracker
DAILY_USAGE = {} 
AUTO_VISITS = {}
AUTO_VISIT_STATS = {}

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ==============================================================================
#             AUTO JWT GENERATOR (FROM MAIN15)
# ==============================================================================

INPUT_VISIT = "account_visit.json"
OUTPUT_VISIT = "token_ind_visit.json"
REFRESH_INTERVAL = 16000  # 7 hours approx

class AutoJWTGenerator:
    def __init__(self):
        self.api_url = "https://kamodjwt.vercel.app/token"

    def fetch_jwt_from_api(self, uid, password):
        try:
            params = {"uid": uid, "password": password}
            response = requests.get(self.api_url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if data.get("success") and "jwt_token" in data:
                    return data["jwt_token"]

            return None
        except:
            return None

    def process_visit_accounts(self):

        if not os.path.exists(INPUT_VISIT):
            print("❌ account_visit.json not found")
            return

        with open(INPUT_VISIT, "r", encoding="utf-8") as f:
            accounts = json.load(f)

        valid_tokens = []
        lock = threading.Lock()

        def worker(acc):
            uid = acc.get("uid")
            pwd = acc.get("password")

            if uid and pwd:
                token = self.fetch_jwt_from_api(uid, pwd)
                if token:
                    with lock:
                        valid_tokens.append({"token": token})
                    print(f"✅ VISIT TOKEN OK: {uid}")
                else:
                    print(f"❌ FAILED: {uid}")

            time.sleep(1)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, acc) for acc in accounts]
            for f in as_completed(futures):
                f.result()

        with open(OUTPUT_VISIT, "w", encoding="utf-8") as f:
            json.dump(valid_tokens, f, indent=4)

        print(f"💾 Saved {len(valid_tokens)} Visit Tokens")


def run_auto_refresher():
    generator = AutoJWTGenerator()
    print("🚀 AUTO TOKEN REFRESHER STARTED")

    while True:
        generator.process_visit_accounts()
        print("😴 Sleeping 7 Hours...")
        time.sleep(REFRESH_INTERVAL)

# ==============================================================================
#             PART 1: TOKEN MEMORY
# ==============================================================================
MEM_TOKENS = [] 

def refresh_tokens_ram():
    global MEM_TOKENS
    while True:
        try:
            if os.path.exists(OUTPUT_VISIT):
                with open(OUTPUT_VISIT, 'r') as f:
                    MEM_TOKENS = json.load(f)
            print(f"🔄 Bot B: Loaded {len(MEM_TOKENS)} Visit Tokens")
        except Exception as e:
            print(f"Token Load Error: {e}")
        time.sleep(300) # Refresh every 5 mins

# ==============================================================================
#             PART 2: FF ENCRYPTION & API
# ==============================================================================
import uid_generator_pb2
import like_count_pb2

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(cipher.encrypt(pad(plaintext, AES.block_size))).decode('utf-8')

def create_profile_check_proto(uid):
    message = uid_generator_pb2.uid_generator()
    message.krishna_ = int(uid)
    message.teamXdarks = 1
    return message.SerializeToString()

async def send_request(session, encrypted_data, token, url):
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Connection': "Keep-Alive", 'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1", 'ReleaseVersion': "OB52"
    }
    try:
        async with session.post(url, data=bytes.fromhex(encrypted_data), headers=headers, ssl=False) as response:
            return response.status
    except: return 999

# 🔥 FIX: Debug Mode & Extended Field Search
async def get_profile_name(uid, tokens):
    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    proto = create_profile_check_proto(uid)
    enc_data = encrypt_message(proto)
    
    valid_tokens = [t for t in tokens if t.get('token')]
    if not valid_tokens: return "Unknown User", "N/A"

    sample = random.sample(valid_tokens, min(len(valid_tokens), 30))
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        for t in sample:
            headers = {
                'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
                'Authorization': f"Bearer {t['token']}",
                'Content-Type': "application/x-www-form-urlencoded",
                'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1", 'ReleaseVersion': "OB52"
            }
            try:
                async with session.post(url, data=bytes.fromhex(enc_data), headers=headers, ssl=False) as r:
                    if r.status == 200:
                        content = await r.read()
                        items = like_count_pb2.Info()
                        items.ParseFromString(content)
                        
                        # 1. Get Name
                        name = items.AccountInfo.PlayerNickname
                        
                        # 2. DEBUG PRINT
                        acc = items.AccountInfo
                        print(f"\n🔍 DEBUG DATA FOR {uid}: {acc}\n") 

                        # 3. Enhanced Like Fetcher (Checks Mm, ShowLiked, Liked, etc.)
                        likes = "N/A"
                        possible_fields = ['Likes', 'ShowLiked', 'Liked', 'liked', 'Like', 'Mm', 'mm', 'like_count', 'score']
                        
                        for field in possible_fields:
                            if hasattr(acc, field):
                                val = getattr(acc, field)
                                if isinstance(val, int): 
                                    likes = val
                                    break
                        
                        return name, likes
            except Exception as e:
                print(f"Error parsing: {e}")
            
    return "Unknown User", "N/A"


# ==============================================================================
#             PART 3: VISIT PROCESSOR
# ==============================================================================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def process_visit_task(
    chat_id,
    user_id,
    uid,
    region,
    tokens,
    context,
    msg_id,
    is_auto=False
):

    # 🔒 OFFICIAL GROUP LOCK
    if chat_id != OFFICIAL_GROUP_ID:
        keyboard = [[
            InlineKeyboardButton(
                "👥 JOIN OFFICIAL GROUP",
                url="https://t.me/KAMOD_LIKE_GROUP"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                "╭━━━━━━━━━━━━━━━━━━━━✪\n"
                "│ ❌ COMMAND NOT ALLOWED\n"
                "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
                "🚀 This bot works only in\n"
                "OFFICIAL GROUP."
            ),
            reply_markup=reply_markup
        )
        return 0

    start_time = time.time()

    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    enc_data = encrypt_message(create_profile_check_proto(uid))

    name_task = asyncio.create_task(get_profile_name(uid, tokens))

    valid_tokens = [t for t in tokens if t.get("token")]
    if not valid_tokens:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="⚠️ No Valid Tokens Found!"
        )
        return 0

    target_success = 20000
    total_success = 0
    total_sent = 0
    last_percent = -1

    sem = asyncio.Semaphore(500)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=None)
    ) as session:

        while total_success < target_success:

            batch_size = min(100, target_success - total_success)

            async def bound_req(token):
                async with sem:
                    return await send_request(session, enc_data, token, url)

            tasks = [
                bound_req(
                    valid_tokens[(total_sent + i) % len(valid_tokens)]["token"]
                )
                for i in range(batch_size)
            ]

            results = await asyncio.gather(*tasks)
            batch_success = results.count(200)

            total_success += batch_success
            total_sent += batch_size

            # ✅ LIMITED NON-BLOCKING PROGRESS
            percent = int((total_success / target_success) * 100)

            update_points = [10, 20, 40, 60, 80, 100]

            for point in update_points:
                if percent >= point and last_percent < point:
                    last_percent = point

                    filled = int(10 * point / 100)
                    bar = "█" * filled + "░" * (10 - filled)

                    try:
                        asyncio.create_task(
                            context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=msg_id,
                                text=f"⏳ PROCESSING....!\n\n⚡ {point}% {bar}"
                            )
                        )
                    except:
                        pass
                    break

            if batch_success == 0:
                break

    success = total_success
    name, likes = await name_task
    elapsed = f"{time.time() - start_time:.2f}s"

    # 🔥 TITLE CHANGE
    title = "AUTOVISIT SUCCESSFULLY" if is_auto else "VISIT SENT SUCCESSFULLY"

    # 🔘 BUTTONS
    keyboard = [
        [
            InlineKeyboardButton(
                "📢 MAIN CHANNEL",
                url="https://t.me/KAMOD_CODEX"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 🔥 FINAL POSTER
    if success == 0:
        final_msg = f"""
╭━━━━━━━━━━━━━━━━━━━━✪
│   ❌ VISIT FAILED
╰━━━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯
│  Name        : {name}
│  UID         : {uid}
│  Region      : {region}
│  Total Likes : {likes}
╰━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 🚀 VISIT DETAILS ✦ ⟯
│  Visits Added : 0
│  Time Taken   : {elapsed}
╰━━━━━━━━━━━━━━━━━━✪
"""
    else:
        final_msg = f"""
╭━━━━━━━━━━━━━━━━━━━━✪
│  ✅ {title}
╰━━━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯
│  Name        : {name}
│  UID         : {uid}
│  Region      : {region}
│  Total Likes : {likes}
╰━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 🚀 VISIT DETAILS ✦ ⟯
│  Visits Added : +{success}
│  Time Taken   : {elapsed}
╰━━━━━━━━━━━━━━━━━━✪
"""

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=final_msg,
            reply_markup=reply_markup
        )
    except:
        pass

    return success   # 👈 IMPORTANT
        
async def auto_visit_loop(chat_id, uid, region, context):

    name, likes = await get_profile_name(uid, MEM_TOKENS)

    AUTO_VISIT_STATS[uid] = {
        "cycles": 0,
        "total_visits": 0,
        "name": name
    }

    while True:
        try:
            msg = await context.bot.send_message(
                chat_id,
                f"⚡ AUTOVISIT RUNNING\nUID: {uid}"
            )

            success = await process_visit_task(
                chat_id,
                ADMIN_ID,
                uid,
                region,
                MEM_TOKENS,
                context,
                msg.message_id,
                is_auto=True   # 👈 IMPORTANT
            )

            AUTO_VISIT_STATS[uid]["cycles"] += 1
            AUTO_VISIT_STATS[uid]["total_visits"] += success

            await asyncio.sleep(1)

        except asyncio.CancelledError:
            break
             
async def autovisit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 OWNER ONLY COMMAND")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "/autovisit ind 12345678\n"
            "/autovisit stop 12345678"
        )
        return

    action = context.args[0].lower()
    uid = context.args[1]

    if action == "stop":

        if uid in AUTO_VISITS:
            AUTO_VISITS[uid].cancel()
            del AUTO_VISITS[uid]

            stats = AUTO_VISIT_STATS.get(uid, {})
            cycles = stats.get("cycles", 0)
            total_visits = stats.get("total_visits", 0)
            name = stats.get("name", "Unknown")

            summary = f"""
━━━━━━━━━━━━━━━━━━━━✪
│  🛑 AUTOVISIT STOPPED
╰━━━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯
│  Name  : {name}
│  UID   : {uid}
╰━━━━━━━━━━━━━━━━━━✪

╭━⟮ ✦ 📊 SUMMARY ✦ ⟯
│  Total Cycles : {cycles}
│  Total Visits : {total_visits}
╰━━━━━━━━━━━━━━━━━━✪
"""

            await update.message.reply_text(summary)
        else:
            await update.message.reply_text("❌ Not Running")

        return

    region = action.upper()

    if uid in AUTO_VISITS:
        await update.message.reply_text("⚠ Already Running")
        return

    task = asyncio.create_task(
        auto_visit_loop(update.effective_chat.id, uid, region, context)
    )

    AUTO_VISITS[uid] = task

    await update.message.reply_text(
        f"🔥 AUTOVISIT STARTED\nUID: {uid}\nRegion: {region}"
    )
    
# =====================================================
# VISIT BUTTON SYSTEM (BOT A BUTTON SUPPORT)
# =====================================================

async def visit_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text != "📍 Send Visit":
        return

    keyboard = [
        [
            InlineKeyboardButton("🇮🇳 IND", callback_data="visit_ind"),
            InlineKeyboardButton("🇧🇩 BD", callback_data="visit_bd")
        ]
    ]

    await update.message.reply_text(
        "🌍 SELECT REGION:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def visit_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "visit_ind":
        region = "IND"
    elif data == "visit_bd":
        region = "BD"
    else:
        return

    context.user_data["visit_region"] = region
    context.user_data["visit_step"] = "uid"

    await query.message.reply_text(
        f"✅ REGION SELECTED: {region}\n\n📍 NOW SEND UID:"
    )


import re

async def visit_uid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("visit_step") != "uid":
        return

    text = update.message.text.strip()

    # UID extract (numbers only)
    match = re.search(r"\d{6,}", text)

    if not match:
        return

    uid = match.group()
    region = context.user_data.get("visit_region", "IND")

    context.user_data.clear()

    if not MEM_TOKENS:
        return await update.message.reply_text(
            "⚠️ System Busy or No Tokens!"
        )

    msg = await update.message.reply_text(
        "⏳ Sending Visits..."
    )

    asyncio.create_task(
        process_visit_task(
            update.effective_chat.id,
            update.effective_user.id,
            uid,
            region,
            MEM_TOKENS,
            context,
            msg.message_id
        )
    )
# ==============================================================================
#             PART 4: COMMANDS
# ==============================================================================

# --- 1. START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = (
        "╭━━━🔥 COMMAND PANEL 🔥━━━╮\n\n"
        "👤 User:\n"
        "➤ /visit region uid\n\n"
        "👑 Owner:\n"
        "➤ /autovisit ind uid\n"
        "➤ /autovisit stop uid\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯"
    )

    await update.message.reply_text(msg)

# --- 2. VISIT COMMAND ---
async def visit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    # 🔒 PRIVATE BLOCK SYSTEM
    if update.effective_chat.type == "private" and user_id != ADMIN_ID:

        keyboard = [
            [
                InlineKeyboardButton(
                    "➕ Add Your Group",
                    url=f"https://t.me/{context.bot.username}?startgroup=true"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Official Group",
                    url="https://t.me/KAMOD_LIKE_GROUP"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        error_text = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│   ❌ COMMAND NOT ALLOWED\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ 🚫 PRIVATE ACCESS BLOCKED ⟯\n"
            "│  This command is restricted.\n"
            "│  WORK ONLY OFFICIAL GROUP.\n"
            "╰━━━━━━━━━━━━━━━━━━✪"
        )

        return await update.message.reply_text(
            error_text,
            reply_markup=reply_markup
        )

    # ✅ FORMAT CHECK
    if len(context.args) != 2:
        return await update.message.reply_text(
            "❌ Format: /visit IND 12345678"
        )

    region, uid = context.args[0].upper(), context.args[1]

    if not MEM_TOKENS:
        return await update.message.reply_text(
            "⚠️ System Busy or No Tokens!"
        )

    msg = await update.message.reply_text(
        "⏳ Processing Visit Request..."
    )

    asyncio.create_task(
        process_visit_task(
            update.effective_chat.id,
            user_id,
            uid,
            region,
            MEM_TOKENS,
            context,
            msg.message_id
        )
    )

# --- 3. CHECK VISIT COMMAND (ADMIN ONLY) ---
async def check_visit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 <b>Admin Only Command!</b>", parse_mode='HTML')

    if len(context.args) != 2:
        return await update.message.reply_text("❌ <b>Usage:</b> <code>/checkvisit IND 7737005533</code>", parse_mode='HTML')

    uid = context.args[1]
    total = len(MEM_TOKENS)
    
    if total == 0:
        return await update.message.reply_text("❌ No Tokens Loaded to check.", parse_mode='HTML')

    status_msg = await update.message.reply_text(f"🔄 <b>Checking {total} Tokens...</b>\n\nTarget UID: {uid}", parse_mode='HTML')

    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    enc_data = encrypt_message(create_profile_check_proto(uid))
    sem = asyncio.Semaphore(200) 
    
    async def check_one(session, token):
        async with sem:
            code = await send_request(session, enc_data, token, url)
            return code

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=None)) as session:
        tasks = [check_one(session, t.get("token")) for t in MEM_TOKENS if t.get("token")]
        results = await asyncio.gather(*tasks)
    
    working = results.count(200)
    dead = total - working
    
    report = (
        "📊 <b>VISIT TOKEN HEALTH REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Target UID:</b> <code>{uid}</code>\n"
        f"📂 <b>Total Tokens:</b> {total}\n\n"
        f"✅ <b>Working (Live):</b> {working}\n"
        f"❌ <b>Failed (Dead):</b> {dead}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Tokens refreshed automatically in background.</i>"
    )
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=report, parse_mode='HTML')


if __name__ == '__main__':

    threading.Thread(target=run_auto_refresher, daemon=True).start()
    threading.Thread(target=refresh_tokens_ram, daemon=True).start()

    request = HTTPXRequest(connect_timeout=60, read_timeout=60, write_timeout=60, pool_timeout=60)

    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("visit", visit_command))
    app.add_handler(CommandHandler("autovisit", autovisit_command))
    app.add_handler(CommandHandler("checkvisit", check_visit_command))

    # BUTTON CLICK
    app.add_handler(MessageHandler(filters.Regex("^📍 Send Visit$"), visit_button_handler))

    # REGION SELECT
    app.add_handler(CallbackQueryHandler(visit_region_callback, pattern="visit_"))

    # UID INPUT
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, visit_uid_handler))

    print("""
╔══════════════════════════════╗
║      🚀 KAMOD VISIT BOT      ║
╠══════════════════════════════╣
║  ⚡ Status   : ONLINE         ║
║  🔥 Mode     : VISIT ONLY     ║
║  🛡 System   : STABLE         ║
╚══════════════════════════════╝
""")

    app.run_polling()