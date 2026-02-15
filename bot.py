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

load_dotenv()
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# --- בדיקה והתקנה אוטומטית של MediaInfo ---
if shutil.which("mediainfo") is None:
    print("⚠️ Mediainfo לא נמצא! מנסה להתקין אוטומטית...")
    try:
        # נסיון להתקנה (דורש הרשאות ב-VPS/Container)
        subprocess.run("apt-get update && apt-get install -y mediainfo", shell=True, check=True)
        print("✅ Mediainfo הותקן בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה בהתקנה אוטומטית: {e}")
        print("חובה להתקין ידנית: sudo apt-get install mediainfo")

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

MSG_START = "👋 **בוט ניהול מדיה (Pyrofork)**\n\nבחר אפשרות לניהול:"
MSG_HELP_MAIN = "📚 **תפריט ראשי**"

section_dict = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠", "Menu": "🗃"}

def resize_thumbnail(path):
    """חובה לכווץ תמונות ל-320px כדי שטלגרם יקבל אותן כ-Thumb"""
    try:
        img = Image.open(path)
        img.thumbnail((320, 320))
        img = img.convert("RGB")
        img.save(path, "JPEG", quality=85)
        return True
    except Exception as e:
        print(f"Error resizing: {e}")
        return False

def parseinfo(out, size):
    tc = ""
    trigger = False
    
    size_line = f"File size : {size / (1024 * 1024):.2f} MiB"
    if size > 1024 * 1024 * 1024:
        size_line = f"File size : {size / (1024 * 1024 * 1024):.2f} GiB"

    lines = out.split("\n")
    for line in lines:
        line = line.strip()
        if not line: continue

        found_section = False
        for section, emoji in section_dict.items():
            if line.startswith(section) and ":" not in line:
                trigger = True
                if not line.startswith("General"):
                    tc += "</pre><br>"
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

@app.on_message(filters.command("start"))
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("מדיה אינפו 📝", callback_data="help_mediainfo"),
            InlineKeyboardButton("תמונה ממוזערת 🖼", callback_data="help_thumb")
        ]
    ])
    await message.reply_text(MSG_START, reply_markup=keyboard, quote=True)

@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    if callback.data == "help_mediainfo":
        await callback.answer("שלח קובץ והגב עליו /mediainfo", show_alert=True)
    elif callback.data == "help_thumb":
        await callback.answer("שלח תמונה רגילה כדי לשמור אותה", show_alert=True)

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    msg = await message.reply("⚙️ מעבד תמונה...", quote=True)
    
    await message.download(file_name=path)
    if resize_thumbnail(path):
        await msg.edit("✅ **התמונה נשמרה!**\nעכשיו שלח וידאו והוא יקבל את התמונה הזו.")
    else:
        await msg.edit("❌ שגיאה בעיבוד התמונה.")

@app.on_message(filters.command("del_thumb"))
async def delete_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    if os.path.exists(path):
        os.remove(path)
        await message.reply_text("🗑 התמונה נמחקה.")
    else:
        await message.reply_text("❌ אין תמונה למחוק.")

@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    # טיפול במדיה אינפו אם כתוב בקאפשן
    if message.caption and message.caption.startswith("/mediainfo"):
        await process_mediainfo(client, message)
        return

    # החלפת תמונה
    user_id = message.from_user.id
    thumb_path = os.path.join(THUMB_DIR, f"{user_id}.jpg")

    if os.path.exists(thumb_path):
        msg = await message.reply("⚡ **מחליף תמונה...**", quote=True)
        try:
            file_ref = message.video.file_id if message.video else message.document.file_id
            
            await client.send_video(
                chat_id=message.chat.id,
                video=file_ref,
                thumb=thumb_path,
                caption=message.caption,
                caption_entities=message.caption_entities,
                supports_streaming=True
            )
            await msg.delete()
        except Exception as e:
            await msg.edit(f"❌ שגיאה: {e}")

@app.on_message(filters.command("mediainfo"))
async def mediainfo_reply_handler(client, message):
    if message.reply_to_message:
        target = message.reply_to_message
        if target.video or target.document or target.audio:
            await process_mediainfo(client, target)
        else:
            await message.reply("❌ הגב על קובץ מדיה.")
    else:
        await message.reply("❌ הגב על קובץ.")

async def process_mediainfo(client, message):
    status = await message.reply("⏳ **מוריד מטא-דאטה...**", quote=True)
    file_path = f"mi_{message.id}_{secrets.token_hex(2)}.dat"
    
    try:
        current_size = 0
        file_obj = message.video or message.document or message.audio
        
        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in client.stream_media(file_obj):
                await f.write(chunk)
                current_size += len(chunk)
                if current_size >= CHUNK_LIMIT:
                    break
        
        # הרצת פקודת mediainfo
        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{file_path}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        
        if output:
            file_name = getattr(file_obj, "file_name", "Unknown File")
            file_size = getattr(file_obj, "file_size", 0)
            
            parsed_content = parseinfo(output, file_size)
            if len(parsed_content) < 20: 
                parsed_content = f"<pre>{output}</pre>"

            final_html = f"<h4>📌 File: {file_name}</h4><br>{parsed_content}"
            
            telegraph = Telegraph()
            await telegraph.create_account(short_name="MediaBot")
            response = await telegraph.create_page(title="MediaInfo", html_content=final_html)
            
            await status.edit(
                f"✅ **MediaInfo מוכן!**\n"
                f"📂 קובץ: `{file_name}`\n"
                f"🔗 [לחץ כאן לצפייה בנתונים]({response['url']})",
                disable_web_page_preview=False
            )
        else:
            await status.edit("❌ שגיאה: Mediainfo החזיר פלט ריק.")

    except Exception as e:
        await status.edit(f"❌ שגיאה: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    print("Bot Started (Pyrofork Edition)...")
    app.run()


