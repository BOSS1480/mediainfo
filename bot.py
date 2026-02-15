import os
import asyncio
import secrets
import logging
import shutil
import subprocess
import aiofiles
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegraph.aio import Telegraph
from dotenv import load_dotenv

# טעינת הגדרות
load_dotenv()
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# התקנה אוטומטית של MediaInfo אם חסר
if shutil.which("mediainfo") is None:
    try:
        subprocess.run("apt-get update && apt-get install -y mediainfo", shell=True, check=False)
    except:
        pass

app = Client(
    "MediaManagerBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

THUMB_DIR = "thumbnails"
if not os.path.exists(THUMB_DIR):
    os.makedirs(THUMB_DIR)

CHUNK_LIMIT = 20 * 1024 * 1024
section_dict = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠", "Menu": "🗃"}

# --- פונקציות עזר ---

def resize_thumbnail(path):
    """התאמת התמונה לדרישות של טלגרם (320px, JPEG)"""
    try:
        img = Image.open(path)
        img.thumbnail((320, 320))
        img = img.convert("RGB")
        img.save(path, "JPEG", quality=85)
        return True
    except:
        return False

def parseinfo(out, size):
    """עיצוב פלט MediaInfo עם אימוג'ים"""
    tc = ""
    trigger = False
    size_mb = size / (1024 * 1024)
    size_line = f"File size : {size_mb:.2f} MiB"
    if size_mb > 1024:
        size_line = f"File size : {size_mb/1024:.2f} GiB"

    for line in out.split("\n"):
        line = line.strip()
        if not line: continue
        
        found_section = False
        for section, emoji in section_dict.items():
            if line.startswith(section) and ":" not in line:
                trigger = True
                if not line.startswith("General"): tc += "</pre><br>"
                tc += f"<h4>{emoji} {line.replace('Text', 'Subtitle')}</h4>"
                found_section = True
                break
        
        if found_section: continue
        if line.startswith("File size"): line = size_line
        if trigger:
            tc += "<br><pre>"
            trigger = False
        tc += line + "\n"
    tc += "</pre><br>"
    return tc

# --- תפריטים ---

@app.on_message(filters.command("start"))
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("עזרה ותפריטים 📚", callback_data="help_main")]
    ])
    text = (
        "👋 **שלום! אני בוט לניהול מדיה.**\n\n"
        "אני יכול לעזור לך להוסיף תמונות ממוזערות לוידאו במהירות "
        "ולהוציא מידע טכני על קבצים.\n\n"
        "השתמש בכפתור למטה כדי לראות איך אני עובד 👇"
    )
    await message.reply_text(text, reply_markup=keyboard, quote=True)

@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    if callback.data == "help_main":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("מדיה אינפו 📝", callback_data="h_mi"),
             InlineKeyboardButton("תמונה ממוזערת 🖼", callback_data="h_th")],
            [InlineKeyboardButton("חזרה 🔙", callback_data="back_start")]
        ])
        await callback.message.edit_text("📚 **תפריט עזרה**\nבחר נושא ללמידה:", reply_markup=keyboard)
    
    elif callback.data == "h_mi":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("חזרה 🔙", callback_data="help_main")]])
        text = "📝 **מדיה אינפו**\n\nשלח קובץ והגב עליו עם הפקודה `/mediainfo`.\nהבוט ינתח את הקובץ וישלח לך קישור לדף עם כל הפרטים."
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    elif callback.data == "h_th":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("חזרה 🔙", callback_data="help_main")]])
        text = "🖼 **תמונה ממוזערת**\n\n1. שלח לי תמונה רגילה - היא תישמר כקבועה.\n2. שלח לי וידאו - הוא יוחזר אליך מיד עם התמונה שלך."
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif callback.data == "back_start":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("עזרה ותפריטים 📚", callback_data="help_main")]])
        await callback.message.edit_text("👋 **בוט ניהול מדיה**\nבחר אפשרות:", reply_markup=keyboard)

# --- לוגיקה של הבוט ---

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    await message.download(file_name=path)
    if resize_thumbnail(path):
        await message.reply_text("✅ **התמונה נשמרה בהצלחה!**", quote=True)
    else:
        await message.reply_text("❌ שגיאה בעיבוד התמונה.", quote=True)

@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    if message.caption and message.caption.startswith("/mediainfo"):
        await process_mediainfo(client, message)
        return

    user_id = message.from_user.id
    thumb_path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    if os.path.exists(thumb_path):
        msg = await message.reply("⚡ **מעבד...**", quote=True)
        try:
            file_id = message.video.file_id if message.video else message.document.file_id
            await client.send_video(
                chat_id=message.chat.id,
                video=file_id,
                thumb=thumb_path,
                caption=message.caption,
                caption_entities=message.caption_entities,
                supports_streaming=True
            )
            await msg.delete()
        except Exception as e:
            await msg.edit(f"❌ שגיאה: {e}")

@app.on_message(filters.command("mediainfo"))
async def mi_cmd(client, message):
    if message.reply_to_message:
        await process_mediainfo(client, message.reply_to_message)
    else:
        await message.reply("❌ הגב על קובץ עם הפקודה.")

async def process_mediainfo(client, message):
    status = await message.reply("⏳ **מנתח מידע...**", quote=True)
    file_path = f"mi_{message.id}.dat"
    try:
        file_obj = message.video or message.document or message.audio
        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in client.stream_media(file_obj):
                await f.write(chunk)
                if os.path.getsize(file_path) >= CHUNK_LIMIT: break
        
        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{file_path}"',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        
        if output:
            content = parseinfo(output, file_obj.file_size)
            telegraph = Telegraph()
            await telegraph.create_account(short_name="MediaBot")
            page = await telegraph.create_page(title="MediaInfo Result", html_content=content)
            await status.edit(f"✅ **הניתוח הושלם!**\n\n🔗 [לחץ כאן לצפייה בפרטים]({page['url']})")
        else:
            await status.edit("❌ לא התקבל מידע מהקובץ.")
    except Exception as e:
        await status.edit(f"❌ שגיאה: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

if __name__ == "__main__":
    app.run()

