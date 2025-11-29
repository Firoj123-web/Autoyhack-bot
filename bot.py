import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pymongo import MongoClient
from dotenv import load_dotenv
from utils.crypto import encrypt_bytes, decrypt_bytes

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS").split(",") if x.strip()]
MONGODB_URL = os.getenv("MONGODB_URL")
DEFAULT_UPI = os.getenv("DEFAULT_UPI",)
SCHEDULER_TYPE = os.getenv("SCHEDULER_TYPE","apscheduler")

logging.basicConfig(level=os.getenv("7894840999","INFO"))
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
client = MongoClient(MONGODB_URL)
db = client.autoyhack
users = db.users

# Helper: create user doc if not exists
def ensure_user(uid, username=None):
    u = users.find_one({"user_id": uid})
    if not u:
        u = {
            "user_id": uid,
            "telegram_username": username,
            "trial_start": None,
            "trial_expiry": None,
            "subscription_expiry": None,
            "plan": None,
            "payment_status": None,
            "client_secret_stored": False,
            "upload_frequency_hours": 3,
            "mode": "auto_niche",
            "niche": "default",
            "custom_links": [],
            "last_upload_time": None,
            "logs": []
        }
        users.insert_one(u)
    return users.find_one({"user_id": uid})

# Start command
@dp.message(Command(commands=["start"]))
async def cmd_start(msg: types.Message):
    u = ensure_user(msg.from_user.id, msg.from_user.username)
    # If first time, start trial
    if not u.get("trial_start"):
        now = datetime.utcnow()
        users.update_one({"user_id": msg.from_user.id},{"$set":{
            "trial_start": now,
            "trial_expiry": now + timedelta(days=1)
        }})
        await msg.reply(
            "🎉 Aapko 1-day FREE trial mil gaya! Ab apna client_secrets.json upload karein (file)."
            f"\n\nPayment UPI: {DEFAULT_UPI}\nPlans: 7 days ₹99 | 30 days ₹349\n\nSend client_secrets.json to start."
        )
    else:
        te = u.get("trial_expiry")
        se = u.get("subscription_expiry")
        msg_text = f"Trial expiry: {te}\nSubscription expiry: {se}\nUse /settings to configure."
        await msg.reply(msg_text)

# Accept client_secrets.json file
@dp.message()
async def handle_files(message: types.Message):
    # client_secrets.json upload
    if message.document:
        fname = message.document.file_name
        if fname.endswith("client_secrets.json"):
            # download file
            file = await bot.get_file(message.document.file_id)
            file_path = file.file_path
            save_path = f"./uploads/{message.from_user.id}_client_secrets.json"
            await message.document.download(destination=save_path)
            # encrypt & store in DB (binary)
            with open(save_path,"rb") as f:
                data = f.read()
            enc = encrypt_bytes(data)
            users.update_one({"user_id": message.from_user.id},{"$set":{
                "client_secret_stored": True,
                "client_secret_enc": enc,
                "client_secret_uploaded_at": datetime.utcnow()
            }})
            await message.reply("Client secrets received. Bot will attempt to use it for OAuth when needed. Trial active for 24 hours.")
            # start scheduler job for this user
            register_user_job(message.from_user.id)
            return

    # Payment screenshot (image)
    if message.photo or message.document and (message.document.mime_type and "image" in message.document.mime_type):
