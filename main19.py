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
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, Application
from telegram.request import HTTPXRequest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import aiohttp
from colorama import Fore, Style, init

# Initialize Colorama
init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= CONFIGURATION =================
BOT_TOKEN = "8486877952:AAHa-oYkSXuwYUQza6wSc6Vx9WtSOP5tiNI"   
CHANNEL_LINK = "@KAMOD_CODEX"       
OWNER_LINK = "@kamod90"             
ADMIN_ID = 7114540206  
GROUP_LINK = "@KAMOD_LIKE_GROUP"
MUST_JOIN_CHANNELS = ["@KAMOD_CODEX"] 

# Files
INPUT_VISIT = "account_visit.json"
OUTPUT_VISIT = "token_ind_visit.json"
INPUT_LIKE = "account_like.json"
OUTPUT_LIKE = "token_ind.json"
DATA_FILE = "users.json"
CHECK_UID = "7737005533"

# Refresh Config
TARGET_REGION = "IND"
REFRESH_INTERVAL = 25000
DELAY_SEC = 3.0

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ==============================================================================
#             PART 1: AUTO JWT GENERATOR (API VERSION)
# ==============================================================================

class AutoJWTGenerator:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.api_url = "https://kamodjwt.vercel.app/token"

    def fetch_jwt_from_api(self, uid, password):
        """
        Fetches JWT token using the Vercel API.
        """
        try:
            params = {
                "uid": uid,
                "password": password
            }

            response = requests.get(self.api_url, params=params, timeout=30)

            if response.status_code == 200:
                try:
                    data = response.json()

                    # ✅ Correct key for your Vercel API
                    if data.get("success") and "jwt_token" in data:
                        return data["jwt_token"]
                    else:
                        return None

                except ValueError:
                    return None

            return None

        except Exception as e:
            print(f"{Fore.RED}⚠️ API Request Error for {uid}: {e}{Style.RESET_ALL}")
            return None

    def process_file_batch(self, input_file, output_file, type_label, thread_count=1):
        full_input_path = os.path.join(self.current_dir, input_file)
        full_output_path = os.path.join(self.current_dir, output_file)

        if not os.path.exists(full_input_path):
            print(f"{Fore.RED}⚠️ File not found: {input_file}{Style.RESET_ALL}")
            return

        print(f"\n{Fore.YELLOW}🚀 Starting Batch: {type_label.upper()} ({input_file}) | Threads: {thread_count}{Style.RESET_ALL}")

        try:
            with open(full_input_path, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
        except Exception as e:
            print(f"{Fore.RED}❌ JSON Error in {input_file}: {e}{Style.RESET_ALL}")
            return

        valid_tokens_list = []
        lock = threading.Lock()

        def worker(acc):
            uid = acc.get('uid')
            pwd = acc.get('password')

            if uid and pwd:
                token = None

                for attempt in range(1, 3):
                    token = self.fetch_jwt_from_api(uid, pwd)

                    if token and len(token) > 20:
                        break
                    else:
                        if attempt == 1:
                            time.sleep(2)

                if token:
                    with lock:
                        valid_tokens_list.append({"token": token})
                    print(f"{Fore.GREEN}✅ {type_label}: {uid} success (API){Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ {type_label}: {uid} failed{Style.RESET_ALL}")

            time.sleep(1.0)  # prevent API rate limits

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(worker, acc) for acc in accounts]
            for future in as_completed(futures):
                future.result()

        try:
            with open(full_output_path, 'w', encoding='utf-8') as f:
                json.dump(valid_tokens_list, f, indent=4)

            print(f"{Fore.CYAN}💾 Saved {len(valid_tokens_list)} tokens to {output_file}{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}❌ Error saving file: {e}{Style.RESET_ALL}")

def run_auto_refresher():
    generator = AutoJWTGenerator()
    print(f"{Fore.CYAN}{Style.BRIGHT}=== AUTO TOKEN REFRESHER THREAD STARTED (API MODE) ==={Style.RESET_ALL}")
    while True:
        print(f"\n{Fore.MAGENTA}⏰ Time: {datetime.now().strftime('%H:%M:%S')} - Starting Update Cycle...{Style.RESET_ALL}")
        # 1. LIKE TOKENS -> 1 Thread (To be gentle on the API)
        generator.process_file_batch(INPUT_LIKE, OUTPUT_LIKE, "LIKE", thread_count=1)
        # 2. VISIT TOKENS -> 5 Threads (Reduced from 10 to avoid API bans)
        generator.process_file_batch(INPUT_VISIT, OUTPUT_VISIT, "VISIT", thread_count=5)
        
        print(f"\n{Fore.CYAN}😴 Cycle Complete. Sleeping for 9 Hours...{Style.RESET_ALL}")
        time.sleep(REFRESH_INTERVAL)

# ==============================================================================
#             SAFE DATABASE SYSTEM (NO DATA LOSS FIX)
# ==============================================================================
MEM_DATA = {
    "cooldowns": {},
    "premium": {},
    "all_users": [],
    "maintenance": False,
    "usernames": {},
    "autolike": [],
    "admins": {},

    # NEW
    "coins": {},
    "redeem_codes": {}
}
MEM_TOKENS = {"IND_LIKE": [], "IND_VISIT": []} 
DATA_LOCK = threading.Lock()

def load_data_initial():
    global MEM_DATA
    # Check if file exists and is NOT empty
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        print("⚠️ Users file missing or empty. Creating new database.")
        save_data_force()
        return

    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            # Fix Premium Format if needed
            if isinstance(data.get("premium"), list):
                new_prem = {}
                expiry = (datetime.now() + timedelta(days=30)).isoformat()
                for uid in data["premium"]: new_prem[str(uid)] = expiry
                data["premium"] = new_prem
            
            # Load data into RAM
            for key in MEM_DATA:
                if key in data: MEM_DATA[key] = data[key]
            print(f"✅ Database Loaded: {len(MEM_DATA['all_users'])} Users")
            
    except json.JSONDecodeError:
        print("❌ Database Corrupted! Backup created as users_backup.json")
        os.rename(DATA_FILE, "users_backup.json")
        save_data_force()
    except Exception as e: 
        print(f"DB Error: {e}")

def save_data_force():
    """Saves data safely using a temporary file to prevent 0 Byte corruption"""
    with DATA_LOCK:
        temp_file = f"{DATA_FILE}.tmp"
        try:
            with open(temp_file, "w") as f: 
                json.dump(MEM_DATA, f, indent=4)
            
            # Atomic replacement (Safe Save)
            os.replace(temp_file, DATA_FILE)
        except Exception as e:
            print(f"❌ Save Failed: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

def background_db_saver():
    while True:
        time.sleep(30)
        try: save_data_force()
        except: pass


def refresh_tokens_ram():
    global MEM_TOKENS
    while True:
        try:
            if os.path.exists(OUTPUT_VISIT):
                with open(OUTPUT_VISIT, 'r') as f:
                    data = json.load(f)
                    if data:
                        MEM_TOKENS["IND_VISIT"] = data

            if os.path.exists(OUTPUT_LIKE):
                with open(OUTPUT_LIKE, 'r') as f:
                    data = json.load(f)
                    if data:
                        MEM_TOKENS["IND_LIKE"] = data

            print(
                f"🔄 RAM Refreshed | "
                f"V={len(MEM_TOKENS['IND_VISIT'])} "
                f"L={len(MEM_TOKENS['IND_LIKE'])}"
            )
        except Exception as e:
            print(f"Token Load Error: {e}")

        time.sleep(300)  # 5 min

def get_tokens_from_ram(task_type):
    if task_type == "VISIT": return MEM_TOKENS["IND_VISIT"]
    if task_type == "LIKE": return MEM_TOKENS["IND_LIKE"]
    return []

def record_user(user):
    uid = user.id
    username = user.username.lower() if user.username else None
    with DATA_LOCK:
        if uid not in MEM_DATA["all_users"]: MEM_DATA["all_users"].append(uid)
        if username: MEM_DATA["usernames"][username] = uid

def get_data(): return MEM_DATA

def get_india_time():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

# ==============================================================================
#             PART 3: NETWORK REQUESTS
# ==============================================================================
import like_pb2
import uid_generator_pb2
import like_count_pb2

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(cipher.encrypt(pad(plaintext, AES.block_size))).decode('utf-8')

def create_protobuf_message(user_id, region):
    message = like_pb2.like()
    message.uid = int(user_id)
    message.region = region
    return message.SerializeToString()

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

async def get_profile_info_async(uid, region, tokens):
    # This uses VISIT tokens to check name/likes without wasting LIKE tokens
    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    proto = create_profile_check_proto(uid)
    enc_data = encrypt_message(proto)
    sample = random.sample(tokens, min(len(tokens), 5))
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        for t in sample:
            if not t.get('token'): continue
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
                        return {"name": items.AccountInfo.PlayerNickname, "likes": items.AccountInfo.Likes}
            except: pass
    return {"name": "Unknown", "likes": "0"}

# ==============================================================================
#             PART 4: BACKGROUND TASKS
# ==============================================================================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def process_like_task(chat_id, uid, region, like_tokens, visit_tokens,
                            context, msg_id, user_id, is_premium, today_used):

    # ✅ ONLY IND SERVER ALLOWED
    if region.lower() != "ind":
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "╔════════════════════╗\n"
                    "      🚫 SERVER ERROR\n"
                    "╚════════════════════╝\n\n"
                    "❌ Server not token available.\n"
                    "✅ Use IND server only.\n\n"
                    "Example: /like ind 7737005533"
                )
            )
        except:
            pass
        return

    # 🔥 SHORT PREMIUM ANIMATION
    try:
        for percent in [0, 40, 80, 100]:
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "⚡ <b>KAMOD PREMIUM CONSOLE</b> ⚡\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 UID : <code>{uid}</code>\n"
                    f"<code>{bar} {percent}%</code>\n\n"
                    "🚀 Processing..."
                ),
                parse_mode="HTML"
            )
            await asyncio.sleep(0.25)
    except:
        pass

    # 🔍 Fetch Profile
    info = await get_profile_info_async(uid, region, visit_tokens)
    raw_likes = str(info.get('likes', '0'))
    base_likes = int(raw_likes) if raw_likes.isdigit() else 0

    # 🔥 Like Engine
    url = "https://client.ind.freefiremobile.com/LikeProfile"
    enc_data = encrypt_message(create_protobuf_message(uid, region))

    async def run_likes():
        success = 0
        failed_tokens = []

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=None)
        ) as session:

            tasks = [
                send_request(session, enc_data, t["token"], url)
                for t in like_tokens if t.get("token")
            ]

            results = await asyncio.gather(*tasks)

            for i, status in enumerate(results):
                if status == 200:
                    success += 1
                else:
                    failed_tokens.append(like_tokens[i]["token"])

            for token in failed_tokens:
                status = await send_request(
                    session,
                    enc_data,
                    token,
                    url
                )

                if status == 200:
                    success += 1

                await asyncio.sleep(0.08)

        return success

    success = await run_likes()

    keyboard = [[
        InlineKeyboardButton("👑 OWNER", url="https://t.me/kamod90"),
        InlineKeyboardButton("📢 MAIN CHANNEL", url="https://t.me/KAMOD_CODEX"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ❌ FAIL
    if success == 0:

        msg_text = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│  ❌ LIKE DELIVERY FAILED\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯\n"
            f"│  Name   : {info.get('name', 'Unknown')}\n"
            f"│  UID    : {uid}\n"
            f"│  Region : {region}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ ❤️ LIKE DETAILS ✦ ⟯\n"
            f"│  Before : {base_likes}\n"
            f"│  After  : {base_likes}\n"
            "│  Added  : 0\n"
            "╰━━━━━━━━━━━━━━━━━━✪"
        )

    # ✅ SUCCESS
    else:

        if not is_premium:
            with DATA_LOCK:
                get_data()["cooldowns"].setdefault(
                    str(user_id), []
                ).append({
                    "uid": uid,
                    "time": get_india_time().isoformat()
                })

        msg_text = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│  ✅ LIKE SENT SUCCESSFULLY\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯\n"
            f"│  Name   : {info.get('name', 'Unknown')}\n"
            f"│  UID    : {uid}\n"
            f"│  Region : {region}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ ❤️ LIKE DETAILS ✦ ⟯\n"
            f"│  Before : {base_likes}\n"
            f"│  After  : {base_likes + success}\n"
            f"│  Added  : +{success}\n"
            "╰━━━━━━━━━━━━━━━━━━✪"
        )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=msg_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except:
        pass
# --- AUTO LIKE LOOP ---
async def auto_like_job(context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    now = get_india_time()
    current_time_str = now.strftime("%I:%M %p")
    today_date = now.strftime("%Y-%m-%d")

    tasks_to_run = []

    with DATA_LOCK:
        for task in get_data().get("autolike", []):
            if (
                task["time"] == current_time_str
                and task["last_run"] != today_date
                and task["days"] > 0
            ):
                tasks_to_run.append(task)

    for task in tasks_to_run:
        await process_auto_like_task(app, task, today_date)
        
def is_admin(user_id):

    # Owner always admin
    if user_id == ADMIN_ID:
        return True

    admin_data = get_data().get("admins", {})
    expiry = admin_data.get(str(user_id))

    if not expiry:
        return False

    try:
        if datetime.fromisoformat(expiry) > datetime.now():
            return True
        else:
            del admin_data[str(user_id)]
            return False
    except:
        return False

async def process_auto_like_task(app, task, today_date):
    try:
        like_tokens = get_tokens_from_ram("LIKE")
        visit_tokens = get_tokens_from_ram("VISIT")

        if not like_tokens:
            return

        # 🔍 Fetch profile info
        info = await get_profile_info_async(
            task["uid"],
            task["region"],
            visit_tokens
        )

        raw_likes = str(info.get("likes", "0"))
        base_likes = int(raw_likes) if raw_likes.isdigit() else 0

        url = "https://client.ind.freefiremobile.com/LikeProfile"
        enc_data = encrypt_message(
            create_protobuf_message(task["uid"], task["region"])
        )

        # 🔥 ULTRA STABLE SEQUENTIAL MODE
        async def run_al():
            success = 0

            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=None)
            ) as session:

                for t in like_tokens:
                    if not t.get("token"):
                        continue

                    status = await send_request(
                        session,
                        enc_data,
                        t["token"],
                        url
                    )

                    if status == 200:
                        success += 1

                    # Small delay to avoid server rate limit
                    await asyncio.sleep(0.08)

            return success

        success = await run_al()

        # 🔄 Update DB safely
        with DATA_LOCK:
            task["last_run"] = today_date
            task["days"] -= 1

            if task["days"] <= 0:
                try:
                    get_data()["autolike"].remove(task)
                except:
                    pass

        now = get_india_time()

        msg = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│ 🤖 AUTO LIKE SUCCESSFUL\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 👤 PLAYER INFO ✦ ⟯\n"
            f"│  Name   : {info.get('name', 'Unknown')}\n"
            f"│  UID    : {task['uid']}\n"
            f"│  Region : {task['region']}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ ❤️ DELIVERY REPORT ✦ ⟯\n"
            f"│  Before : {base_likes}\n"
            f"│  Added  : +{success}\n"
            f"│  Total  : {base_likes + success}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            f"│  Remaining Days : {task['days']}\n"
            f"│  Time           : {now.strftime('%H:%M:%S')}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            f"💎 Buy Auto Like : {OWNER_LINK}"
        )

        try:
            await app.bot.send_message(
                chat_id=GROUP_LINK,
                text=msg,
                parse_mode="HTML"
            )
        except:
            pass

    except Exception as e:
        print("AutoLike Error:", e)

# ==============================================================================
#             PART 5: COMMAND HANDLERS
# ==============================================================================

async def check_subscription(user_id, context):
    if user_id == ADMIN_ID: return True
    not_joined = []
    for channel in MUST_JOIN_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [ChatMember.LEFT, ChatMember.BANNED, ChatMember.RESTRICTED]:
                not_joined.append(channel)
        except: pass 
    return len(not_joined) == 0

# [REQUEST 3] Force Join Update - Premium Poster & Verify Logic
async def force_join_alert(update, context):
    keyboard = [
        [InlineKeyboardButton("📢 JOIN CHANNEL NOW", url=f"https://t.me/{CHANNEL_LINK.replace('@','')}")],
        [InlineKeyboardButton("Verify & Try Again", callback_data="check_join")]
    ]

    msg = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  🚨 ACCESS REQUIRED\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
        "Join official channel\n"
        "before using this bot.\n\n"
        "╭━⟮ ✦ STEPS ✦ ⟯\n"
        "│  1. Join Channel\n"
        "│  2. Click Verify\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"
        f"Official Support : {OWNER_LINK}"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    # Send message with premium formatting
    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user if update.effective_user else update.callback_query.from_user
    record_user(user)
    if not await check_subscription(user.id, context): return await force_join_alert(update, context)
    
    safe_name = html.escape(user.first_name)
    poster = (
        "⚡ 𝗞𝗔𝗠𝗢𝗗 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗖𝗢𝗡𝗦𝗢𝗟𝗘 ⚡\n"
        " 𝘃 𝟯.𝟬 | 𝗦𝘁𝗮𝘁𝘂𝘀: 𝗢𝗻𝗹𝗶𝗻𝗲 🟢\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 𝗛𝗲𝘆 <b>{safe_name}</b>!\n"
        "🚀 <i>Welcome to the Ultimate FF Tool.</i>\n\n"
        "<b>💠 Main Features:</b>\n"
        "👍 <code>Auto Like</code>  |  👁️ <code>Auto Visit</code>\n"
        "📊 <code>Rank Push</code>  |  🛡️ <code>Anti-Ban</code>\n\n"
        "👇 <b>Click Command List to Begin:</b>"
    )
    kb = [[InlineKeyboardButton("📜 Command List", callback_data="show_help")], [InlineKeyboardButton("🆘 Support", url=f"https://t.me/{OWNER_LINK.replace('@', '')}")]]
    
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(poster, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except Exception:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=poster, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=poster, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await check_subscription(query.from_user.id, context):
        await query.answer("✅ Access Granted!")
        try: 
            await query.message.delete() # [REQUEST 3] Delete warning message
        except: pass
        # [REQUEST 3] Show Help Menu immediately after verify
        await help_command(update, context) 
    else: 
        await query.answer("❌ Join nahi kiya!", show_alert=True)

# [REQUEST 4] Updated Help Menu & Added Info Command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ensure subscription (double check if called directly)
    if not await check_subscription(update.effective_user.id, context): return await force_join_alert(update, context)
    
    help_text = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  📜 COMMAND CENTER\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
        "╭━⟮ ✦ 👤 USER COMMANDS ✦ ⟯\n"
        "│  ❤️  /like IND UID\n"
        "│  👁️  /visit IND UID\n"
        "│  📝  Get IND UID\n"
        "│  💎  /myplan\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"
        "╭━⟮ ✦ 🛡️ ADMIN COMMANDS ✦ ⟯\n"
        "│  ➕  /adduser ID Days\n"
        "│  ➖  /removeuser ID\n"
        "│  👑  /addadmin ID Days\n"
        "│  ❌  /removeadmin ID\n"
        "│  🤖  /autolike IND UID Time Days\n"
        "│  📊  /status\n"
        "│  📢  /broadcast Message\n"
        "│  ⚙️  /maintenance on/off\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"
        f"Owner : {OWNER_LINK}"
    )
    kb = [[InlineKeyboardButton("💬 CONTACT SUPPORT", url=f"https://t.me/{OWNER_LINK.replace('@', '')}")]]
    
    if update.callback_query: 
        await update.callback_query.message.edit_text(help_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    else: 
        await context.bot.send_message(update.effective_chat.id, text=help_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# [REQUEST 4] New Info Command to get Region/UID Details
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2: 
        return await update.message.reply_text("❌ <b>Usage:</b> <code>/info IND 12345678</code>", parse_mode='HTML')
    
    region, uid = context.args[0].upper(), context.args[1]
    visit_tokens = get_tokens_from_ram("VISIT")
    
    msg = await update.message.reply_text("🔍 <b>Fetching Details...</b>", parse_mode='HTML')
    info = await get_profile_info_async(uid, region, visit_tokens)
    
    resp = (
        "📝 <b>𝗣𝗟𝗔𝗬𝗘𝗥 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>𝗡𝗮𝗺𝗲:</b> {info.get('name', 'Unknown')}\n"
        f"🆔 <b>𝗨𝗜𝗗:</b> <code>{uid}</code>\n"
        f"🌍 <b>𝗥𝗲𝗴𝗶𝗼𝗻:</b> {region}\n"
        f"❤️ <b>𝗟𝗶𝗸𝗲𝘀:</b> {info.get('likes', '0')}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=msg.message_id, text=resp, parse_mode='HTML')


from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    record_user(user)

    # 🔧 Maintenance Mode
    if get_data().get("maintenance") and user.id != ADMIN_ID:
        return await update.message.reply_text(
            "🚧 <b>Maintenance Mode!</b>",
            parse_mode="HTML"
        )

    if not await check_subscription(user.id, context):
        return await force_join_alert(update, context)

    # ======================================================
    # ❌ PRIVATE CHAT BLOCK (BOX STYLE + BUTTON)
    # ======================================================
    if update.effective_chat.type == "private" and user.id != ADMIN_ID:

        group_only_msg = (
            "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "│   ❌ COMMAND NOT AVAILABLE   │\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

            "╭━⟮ ⚠️ ACCESS RESTRICTED ⟯━╮\n"
            "│  This command works only\n"
            "│  inside the official group.\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

            "👥 Join Official Group Below"
        )

        keyboard = [[
            InlineKeyboardButton(
    "👥 JOIN OFFICIAL GROUP",
    url=f"https://t.me/{GROUP_LINK.replace('@','')}"
)
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        return await update.message.reply_text(
            group_only_msg,
            reply_markup=reply_markup
        )

    # ======================================================
    # ❌ USAGE CHECK
    # ======================================================
    if len(context.args) != 2:
        return await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/like IND 12345678</code>",
            parse_mode="HTML"
        )

    data = get_data()

    # 👑 PREMIUM CHECK
    is_premium = str(user.id) in data["premium"] or user.id == ADMIN_ID

    if is_premium and str(user.id) in data["premium"]:
        try:
            if datetime.fromisoformat(data["premium"][str(user.id)]) < datetime.now():
                is_premium = False
        except:
            is_premium = False

    today_used = 0

    # ======================================================
    # FREE USER COOLDOWN SYSTEM
    # ======================================================
    if not is_premium:

        history = data["cooldowns"].get(str(user.id), [])
        valid = []

        for e in history:
            try:
                event_time = datetime.fromisoformat(e["time"])
                if get_india_time() - event_time < timedelta(hours=24):
                    valid.append(e)
            except:
                pass

        data["cooldowns"][str(user.id)] = valid
        today_used = len(valid)

        # 🔁 UID COOLDOWN CHECK
        for entry in valid:
            if entry["uid"] == context.args[1]:

                last_used = datetime.fromisoformat(entry["time"])
                unlock_at = last_used + timedelta(hours=24)
                remaining = unlock_at - get_india_time()

                if remaining.total_seconds() > 0:

                    hours, remainder = divmod(
                        int(remaining.total_seconds()), 3600
                    )
                    minutes, _ = divmod(remainder, 60)

                    cooldown_msg = (
                        "╭━━━━━━━━━━━━━━━━━╮\n"
                        "│ ⛔  COOLDOWN ACTIVE │\n"
                        "╰━━━━━━━━━━━━━━━━━╯\n\n"

                        "╭━⟮ ⚠️ STATUS ⟯━╮\n"
                        "│  UID already received\n"
                        "│  likes today.\n"
                        "╰━━━━━━━━━━━━━━╯\n\n"

                        "╭━⟮ ⏳ TIME LEFT ⟯━╮\n"
                        f"│  {hours}h {minutes}m remaining\n"
                        "╰━━━━━━━━━━━━━━╯"
                    )

                    return await update.message.reply_text(cooldown_msg)

        # ❌ DAILY LIMIT CHECK
        if len(valid) >= 2:

            limit_msg = (
                "╭━━━━━━━━━━━━━━━━━━╮\n"
                "│  DAILY LIMIT REACHED   │\n"
                "╰━━━━━━━━━━━━━━━━━━╯\n\n"

                "╭━⟮ 📊 LIMIT INFO ⟯━╮\n"
                "│  Free users can send\n"
                "│  only 2 uid likes per day.\n"
                "╰━━━━━━━━━━━━━━╯\n\n"

                f"👑 Upgrade to PREMIUM\n"
                f"📩 {OWNER_LINK}"
            )

            return await update.message.reply_text(limit_msg)

    # ======================================================
    # TOKEN CHECK
    # ======================================================
    like_tokens = get_tokens_from_ram("LIKE")
    visit_tokens = get_tokens_from_ram("VISIT")

    if not like_tokens:

        no_token_msg = (
            "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "│   ⚠️  TOKEN UNAVAILABLE   │\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "No active like tokens found.\n"
            "Please try again later."
        )

        return await update.message.reply_text(no_token_msg)

    # ======================================================
    # START PROCESS
    # ======================================================
    msg = await update.message.reply_text(
        "❤️ <b>Sending Likes...</b>",
        parse_mode="HTML"
    )

    asyncio.create_task(
        process_like_task(
            update.effective_chat.id,
            context.args[1],
            context.args[0].upper(),
            like_tokens,
            visit_tokens,
            context,
            msg.message_id,
            user.id,
            is_premium,
            today_used
        )
    )

async def autolike_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # ✅ Allow Owner + Added Admins
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 Admin Only")

    if len(context.args) != 4:
        return await update.message.reply_text(
            "❌ Usage: /autolike IND <UID> 10:30PM 5",
            parse_mode="HTML"
        )

    region = context.args[0].upper()
    uid = context.args[1]
    time_str = context.args[2]

    try:
        days = int(context.args[3])
    except:
        return await update.message.reply_text("❌ Days must be number")

    # ✅ Validate Time Format
    try:
        formatted_time = datetime.strptime(time_str, "%I:%M%p").strftime("%I:%M %p")
    except:
        return await update.message.reply_text(
            "❌ Invalid Time Format!\nExample: 10:30PM",
            parse_mode="HTML"
        )

    new_task = {
        "region": region,
        "uid": uid,
        "time": formatted_time,
        "days": days,
        "last_run": ""
    }

    with DATA_LOCK:
        get_data()["autolike"].append(new_task)

    visit_tokens = get_tokens_from_ram("VISIT")
    info = await get_profile_info_async(uid, region, visit_tokens)

    now = get_india_time()
    start_date = now.strftime("%d-%b-%Y")
    expiry_date = (now + timedelta(days=days)).strftime("%d-%b-%Y")

    msg = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  🤖 AUTO LIKE ACTIVATED\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 👤 PLAYER DETAILS ✦ ⟯\n"
        f"│  Name    : {info.get('name', 'Unknown')}\n"
        f"│  UID     : {uid}\n"
        f"│  Region  : {region}\n"
        f"│  Likes   : {info.get('likes', '0')}\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ ⏰ SCHEDULE INFO ✦ ⟯\n"
        f"│  Start Date  : {start_date}\n"
        f"│  Expiry Date : {expiry_date}\n"
        f"│  Daily Time  : {formatted_time}\n"
        f"│  Total Days  : {days}\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 🚀 STATUS ✦ ⟯\n"
        "│  Auto Like Engine : ACTIVE 🟢\n"
        "│  Execution Mode   : Automatic\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        f"💎 Managed by {OWNER_LINK}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")

from telegram import ReplyKeyboardMarkup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        ["❤️ Start Like"],
        ["💰 Wallet", "👥 Refer"],
        ["👑 OWNER"]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await update.message.reply_text(
        "⚡ KAMOD PREMIUM PANEL ⚡\n\nSelect option below:",
        reply_markup=reply_markup
    )
async def show_main_menu(update):

    keyboard = [
        ["❤️ Start Like"],
        ["💰 Wallet", "👥 Refer"],
        ["👑 OWNER"]
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await update.message.reply_text(
        "❤️",
        reply_markup=reply_markup
    )

async def permanent_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    data = get_data()
    user_id = str(update.effective_user.id)

    # =====================================================
    # ❤️ START LIKE
    # =====================================================
    if text == "❤️ Start Like":

        keyboard = [
            ["🇮🇳 IND"],
            ["🇧🇩 BD"]
        ]

        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )

        context.user_data["like_step"] = "region"

        await update.message.reply_text(
            "🌍 Select Region:",
            reply_markup=reply_markup
        )
        return

    # =====================================================
    # 🌍 REGION SELECT
    # =====================================================
    if context.user_data.get("like_step") == "region" and text in ["🇮🇳 IND", "🇧🇩 BD"]:

        region = "IND" if "IND" in text else "BD"
        context.user_data["selected_region"] = region
        context.user_data["like_step"] = "uid"

        # 🔥 Region keyboard remove
        await update.message.reply_text(
            f"✅ Region Selected: {region}\n\n📌 Now Send UID:",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # =====================================================
    # 🆔 UID STEP
    # =====================================================
    if context.user_data.get("like_step") == "uid":

        uid = text.strip()
        region = context.user_data["selected_region"]

        context.user_data.clear()

        like_tokens = get_tokens_from_ram("LIKE")
        visit_tokens = get_tokens_from_ram("VISIT")

        msg = await update.message.reply_text("❤️ Sending Likes...")

        asyncio.create_task(
            process_like_task(
                update.effective_chat.id,
                uid,
                region,
                like_tokens,
                visit_tokens,
                context,
                msg.message_id,
                update.effective_user.id,
                False,
                0
            )
        )

        # 🔥 Bring back main menu automatically
        await show_main_menu(update)
        return

    # =====================================================
    # 💰 WALLET
    # =====================================================
    if text == "💰 Wallet":

        if user_id in data.get("premium", {}) or is_admin(update.effective_user.id):
            await update.message.reply_text("💰 Coins: ♾ UNLIMITED")
            return

        coins = data.setdefault("coins", {}).get(user_id, 0)
        await update.message.reply_text(f"💰 Coins: {coins}")
        return

    # =====================================================
    # 👥 REFER
    # =====================================================
    if text == "👥 Refer":

        ref_link = f"https://t.me/kamod_codex?start={user_id}"

        await update.message.reply_text(
            f"👥 Your Referral Link:\n\n{ref_link}\n\n"
            "Earn 2 coins per user.\n"
            "Daily 2 coins auto at 4:00 AM."
        )
        return

    # =====================================================
    # 🎁 REDEEM
    # =====================================================
    if text == "🎁 Redeem":
        await update.message.reply_text(
            "🎁 Use Command:\n/redeem CODE"
        )
        return

    # =====================================================
    # 👑 OWNER
    # =====================================================
    if text == "👑 OWNER":

        await update.message.reply_text(
            "👑 OFFICIAL LINKS\n\n"
            "👤 Owner: @kamod90\n"
            "📢 Channel: @KAMOD_CODEX\n"
            "👥 Group: @KAMOD_LIKE_GROUP"
        )
        return

async def daily_coin_job(context: ContextTypes.DEFAULT_TYPE):

    data = get_data()

    with DATA_LOCK:
        for uid in data.get("all_users", []):

            uid = str(uid)

            # premium/admin unlimited -> skip
            if uid in data.get("premium", {}) or is_admin(int(uid)):
                continue

            data.setdefault("coins", {}).setdefault(uid, 0)

            # add 2 coins
            data["coins"][uid] += 2

    
async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /redeem CODE")

    code = context.args[0].lower()
    data = get_data()
    user_id = str(update.effective_user.id)

    # check code exist
    if code not in data.get("redeem_codes", {}):
        return await update.message.reply_text("❌ Invalid Code")

    code_data = data["redeem_codes"][code]

    # limit check
    if code_data["used"] >= code_data["limit"]:
        return await update.message.reply_text("❌ Code Expired")

    # premium/admin unlimited show but still add coins optional
    if user_id not in data.get("premium", {}) and not is_admin(update.effective_user.id):
        data.setdefault("coins", {}).setdefault(user_id, 0)
        data["coins"][user_id] += code_data["value"]

    code_data["used"] += 1

    await update.message.reply_text(
        f"🎉 Redeemed Successfully!\n\nCoins Added: {code_data['value']}"
      
    )
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 Admin Only")

    # Initial Loading Message
    status_msg = await update.message.reply_text(
        "🔄 <b>Checking System...</b>",
        parse_mode="HTML"
    )

    like_tokens = get_tokens_from_ram("LIKE")
    visit_tokens = get_tokens_from_ram("VISIT")

    sem = asyncio.Semaphore(15)

    async def check(session, token):
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        enc = encrypt_message(create_profile_check_proto(CHECK_UID))
        async with sem:
            return await send_request(session, enc, token, url)

    async with aiohttp.ClientSession() as session:
        l_res = await asyncio.gather(
            *[check(session, t['token']) for t in like_tokens if t.get('token')],
            return_exceptions=True
        )
        v_res = await asyncio.gather(
            *[check(session, t['token']) for t in visit_tokens if t.get('token')],
            return_exceptions=True
        )

    live_l = l_res.count(200)
    live_v = v_res.count(200)

    data = get_data()

    msg_text = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  📊 SYSTEM MONITOR\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 👥 USERS ✦ ⟯\n"
        f"│  Total    : {len(data['all_users'])}\n"
        f"│  Premium  : {len(data['premium'])}\n"
        f"│  Admins   : {len(data.get('admins', {}))}\n"
        f"│  Autolike  : {len(data['autolike'])}\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 🎫 TOKEN HEALTH ✦ ⟯\n"
        f"│  Like Tokens  : {live_l}/{len(like_tokens)} 🟢\n"
        f"│  Visit Tokens : {live_v}/{len(visit_tokens)} 🟢\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "⚡ Server Status : Stable\n"
        f"👑 Owner : {OWNER_LINK}"
    )

    # ✅ Proper edit using original message object
    await status_msg.edit_text(msg_text, parse_mode="HTML")              
                
async def allliststatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 Admin Only")

    data = get_data()

    with DATA_LOCK:
        autolike_list = data.get("autolike", [])
        premium_users = data.get("premium", {})
        admin_users = data.get("admins", {})

    # AutoLike List
    if autolike_list:
        auto_text = "\n".join(
            [f"🎯 UID: {t['uid']} | 🌍 {t['region']}" for t in autolike_list]
        )
    else:
        auto_text = "No AutoLike Active"

    # Premium List
    if premium_users:
        premium_text = "\n".join([f"👑 {uid}" for uid in premium_users.keys()])
    else:
        premium_text = "No Premium Users"

    # Admin List
    if admin_users:
        admin_text = "\n".join([f"🛡 {uid}" for uid in admin_users.keys()])
    else:
        admin_text = "No Admins"

    msg = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  📋 ALL LIST STATUS\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"

        "📌 AUTO LIKE LIST:\n"
        f"{auto_text}\n\n"

        "👑 PREMIUM USERS:\n"
        f"{premium_text}\n\n"

        "🛡 ADMIN USERS:\n"
        f"{admin_text}"
    )

    await update.message.reply_text(msg)
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # 🔒 Only Owner Can Add Admin
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Only Owner Can Use This Command")

    if len(context.args) != 2:
        return await update.message.reply_text(
            "Usage: /addadmin USER_ID Days",
            parse_mode="HTML"
        )

    user_id = context.args[0]

    try:
        days = int(context.args[1])
    except:
        return await update.message.reply_text("❌ Days must be number")

    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    expiry_fmt = (datetime.now() + timedelta(days=days)).strftime("%d-%b-%Y")

    with DATA_LOCK:
        get_data()["admins"][str(user_id)] = expiry

    msg = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  👑 ADMIN ACCESS GRANTED\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 👤 ADMIN DETAILS ✦ ⟯\n"
        f"│  User ID     : {user_id}\n"
        f"│  Role        : Administrator\n"
        f"│  Valid For   : {days} Days\n"
        f"│  Expiry Date : {expiry_fmt}\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 🔐 PERMISSIONS ✦ ⟯\n"
        "│  ✓ Auto Like Control\n"
        "│  ✓ Status Access\n"
        "│  ✓ Broadcast Access\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        f"👑 Granted By : {OWNER_LINK}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")
    

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # 🔒 Only Owner Can Remove Admin
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Only Owner Can Use This Command")

    if len(context.args) != 1:
        return await update.message.reply_text(
            "Usage: /removeadmin USER_ID",
            parse_mode="HTML"
        )

    user_id = context.args[0]

    with DATA_LOCK:
        if str(user_id) not in get_data()["admins"]:
            return await update.message.reply_text("❌ User Not Admin")

        del get_data()["admins"][str(user_id)]

    msg = (
        "╭━━━━━━━━━━━━━━━━━━━━✪\n"
        "│  ❌ ADMIN ACCESS REVOKED\n"
        "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ 👤 ADMIN DETAILS ✦ ⟯\n"
        f"│  User ID : {user_id}\n"
        f"│  Role    : Administrator\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        "╭━⟮ ✦ ⚠️ STATUS UPDATE ✦ ⟯\n"
        "│  Access : Removed\n"
        "│  Panel  : Disabled\n"
        "╰━━━━━━━━━━━━━━━━━━✪\n\n"

        f"🔒 Removed By : {OWNER_LINK}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")    

async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()
    user = update.effective_user
    user_id = str(user.id)
    safe_name = html.escape(user.first_name)

    if user_id in data["premium"]:
        try:
            exp_date = datetime.fromisoformat(data["premium"][user_id])
            days_left = (exp_date - datetime.now()).days
            expiry_fmt = exp_date.strftime('%d-%b-%Y')
        except:
            expiry_fmt = "Unknown"
            days_left = 0

        msg = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│  💎 VIP DASHBOARD\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 👤 ACCOUNT INFO ✦ ⟯\n"
            f"│  User   : {safe_name}\n"
            "│  Plan   : Premium\n"
            f"│  Expiry : {expiry_fmt}\n"
            f"│  Days   : {days_left}\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 🚀 BENEFITS ✦ ⟯\n"
            "│  ✓ Unlimited Likes\n"
            "│  ✓ No Cooldown\n"
            "│  ✓ Priority Access\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            f"Elite Member • {OWNER_LINK}"
        )

    else:
        msg = (
            "╭━━━━━━━━━━━━━━━━━━━━✪\n"
            "│  🆓 FREE USER DASHBOARD\n"
            "╰━━━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 👤 ACCOUNT INFO ✦ ⟯\n"
            f"│  User   : {safe_name}\n"
            "│  Plan   : Free\n"
            "│  Status : Active\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 📉 LIMITATIONS ✦ ⟯\n"
            "│  👍 Likes  : 2 / Day\n"
            "│  👁️ Visits : Unlimited\n"
            "│  ⏳ Cooldown : 24 Hours\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            "╭━⟮ ✦ 💎 UPGRADE BENEFITS ✦ ⟯\n"
            "│  ✓ Unlimited Likes\n"
            "│  ✓ No Daily Limit\n"
            "│  ✓ Faster Delivery\n"
            "╰━━━━━━━━━━━━━━━━━━✪\n\n"
            f"Upgrade Now • {OWNER_LINK}"
        )

    await update.message.reply_text(msg, parse_mode="HTML")

from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta

# =====================================================
# 👑 ADD PREMIUM USER
# =====================================================
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Admin Only")

    try:
        if len(context.args) != 2:
            return await update.message.reply_text(
                "Usage: /addpremium USER_ID Days"
            )

        uid = context.args[0]
        days = int(context.args[1])

        expiry = datetime.now() + timedelta(days=days)

        with DATA_LOCK:
            get_data()["premium"][uid] = expiry.isoformat()

        msg = (
            "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "│   👑 PREMIUM ACTIVATED   │\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

            "╭━⟮ 👤 USER INFO ⟯━╮\n"
            f"│  🆔 ID   : {uid}\n"
            f"│  💎 Plan : PREMIUM\n"
            f"│  ⏳ Days : {days}\n"
            f"│  📅 Exp  : {expiry.strftime('%d-%b-%Y')}\n"
            "╰━━━━━━━━━━━━━━╯\n\n"

            f"🔥 Managed by {OWNER_LINK}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        print("Add User Error:", e)
        await update.message.reply_text("❌ Error while activating premium.")


# =====================================================
# ❌ REMOVE PREMIUM USER
# =====================================================
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Admin Only")

    try:
        if len(context.args) != 1:
            return await update.message.reply_text(
                "Usage: /removepremium USER_ID"
            )

        uid = context.args[0]

        with DATA_LOCK:
            if uid in get_data()["premium"]:
                del get_data()["premium"][uid]
            else:
                return await update.message.reply_text(
                    "❌ User not found in premium list."
                )

        msg = (
            "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "│   ❌ PREMIUM REMOVED   │\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

            "╭━⟮ 👤 USER INFO ⟯━╮\n"
            f"│  🆔 ID     : {uid}\n"
            f"│  💎 Plan   : PREMIUM\n"
            f"│  ⛔ Status : INACTIVE\n"
            "╰━━━━━━━━━━━━━━╯\n\n"

            f"⚠️ Access Revoked\n"
            f"🔥 Managed by {OWNER_LINK}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        print("Remove User Error:", e)
        await update.message.reply_text("❌ Error while removing premium.")


# =====================================================
# 📢 BROADCAST MESSAGE
# =====================================================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        return await update.message.reply_text(
            "Usage: /broadcast Your message here"
        )

    msg_text = " ".join(context.args)

    total = len(get_data().get("all_users", []))
    success = 0
    failed = 0

    for uid in get_data().get("all_users", []):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "│        📢 BROADCAST        │\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"{msg_text}"
                )
            )
            success += 1
        except:
            failed += 1

    report_msg = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│     📊 BROADCAST REPORT     │\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"

        "╭━⟮ 📈 STATS ⟯━╮\n"
        f"│  👥 Total Users : {total}\n"
        f"│  ✅ Sent        : {success}\n"
        f"│  ❌ Failed      : {failed}\n"
        "╰━━━━━━━━━━━━━━╯"
    )

    await update.message.reply_text(report_msg)

async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    mode = context.args[0].lower() == "on"
    with DATA_LOCK: get_data()["maintenance"] = mode
    await update.message.reply_text(f"Maintenance: {mode}")

# 🔥 STARTUP LOGIC
async def post_init(application: Application):

    application.job_queue.run_repeating(
        auto_like_job,
        interval=60,
        first=10
    )

    # 🔥 DAILY 4AM COIN
    application.job_queue.run_daily(
        daily_coin_job,
        time=datetime.strptime("04:00", "%H:%M").time()
    )
if __name__ == '__main__':
    load_data_initial()
    
    # 🔥 Start Auto-Refresh Thread (Background me file update karega)
    threading.Thread(target=run_auto_refresher, daemon=True).start()
    
    # 🔥 Start Ram Refresh Thread (Updated file se RAM me load karega)
    threading.Thread(target=refresh_tokens_ram, daemon=True).start()
    
    threading.Thread(target=background_db_saver, daemon=True).start()

    # 🔥 FIX: HTTPX Request - High timeouts and limits for Multi-User
    request = HTTPXRequest(connect_timeout=60, read_timeout=60, write_timeout=60, pool_timeout=60)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,       permanent_menu_handler))
    app.add_handler(CommandHandler("like", like_command))
    app.add_handler(CommandHandler("redeem", redeem_command))
    #app.add_handler(CommandHandler("createredeem", create_redeem))
    app.add_handler(CommandHandler("info", info_command)) # Added Info Command
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("myplan", myplan_command))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("maintenance", maintenance_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("autolike", autolike_command))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("allliststatus", allliststatus_command))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="show_help"))

    print("""
🚀━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ KAMOD BOT ENGINE STARTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mode        : LIKE + AUTO REFRESH
Auto Token  : ACTIVE
RAM Sync    : RUNNING
Server      : ONLINE 🟢
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    app.run_polling()





