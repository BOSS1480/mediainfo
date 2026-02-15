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

# התקנה אוטומטית של MediaInfo
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

# --- פונקציות לעיבוד תמונה (איכות גבוהה) ---

def get_image_dimensions(path):
    """מחלץ מימדים לשימוש ב-send_video"""
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except:
        return 640, 640

def prepare_thumb(path):
    """מכין תמונה באיכות מקסימלית לפי התקן של טלגרם"""
    try:
        img = Image.open(path)
        # טלגרם תומך עד 640x640 ב-High Res Thumbs
        img.thumbnail((640, 640))
        img = img.convert("RGB")
        # שמירה באיכות 95 (כמעט ללא איבוד) עם הגדרות מקצועיות
        img.save(path, "JPEG", quality=95, optimize=False, subsampling=0)
        return True
    except Exception as e:
        logging.error(f"Error: {e}")
        return False

def parse_media_info(out, size):
    """עיצוב דוח המדיה אינפו"""
    sections = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠"}
    tc = ""
    trigger = False
    size_mb = size / (1024 * 1024)
    size_str = f"{size_mb:.2f} MiB" if size_mb < 1024 else f"{size_mb/1024:.2f} GiB"

    for line in out.split("\n"):
        line = line.strip()
        if not line: continue
        for sec, emo in sections.items():
            if line.startswith(sec) and ":" not in line:
                if tc: tc += "</pre><br>"
                tc += f"<h4>{emo} {line.replace('Text', 'Subtitle')}</h4><pre>"
                trigger = True
                break
        if "File size" in line: line = f"File size : {size_str}"
        if not trigger: continue
        tc += line + "\n"
    return tc + "</pre>"

# --- פקודות ---

@app.on_message(filters.command("start"))
async def start(client, message):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("עזרה ותפריטים 📚", callback_data="help")]])
    await message.reply_text(
        "👋 **ברוך הבא לבוט החלפת תמונה ומידע!**\n\n"
        "שלח תמונה כדי לשמור אותה כ-Thumbnail קבוע.\n"
        "שלח וידאו כדי להחליף לו את התמונה באופן מיידי.",
        reply_markup=keyboard, quote=True
    )

@app.on_callback_query()
async def cb_handler(client, cb: CallbackQuery):
    if cb.data == "help":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("מדיה אינפו 📝", callback_data="h_mi"),
             InlineKeyboardButton("תמונה ממוזערת 🖼", callback_data="h_th")],
            [InlineKeyboardButton("חזרה 🔙", callback_data="start")]
        ])
        await cb.message.edit_text("📚 **תפריט עזרה**", reply_markup=keyboard)
    elif cb.data == "h_mi":
        await cb.answer("הגב על קובץ עם /mediainfo", show_alert=True)
    elif cb.data == "h_th":
        await cb.answer("שלח תמונה לשמירה, ואז וידאו להחלפה", show_alert=True)
    elif cb.data == "start":
        await start(client, cb.message)

@app.on_message(filters.command("view_thumb"))
async def view_thumb(client, message):
    path = os.path.join(THUMB_DIR, f"{message.from_user.id}.jpg")
    if os.path.exists(path):
        await message.reply_photo(path, caption="🖼 זו התמונה השמורה שלך (HQ).")
    else:
        await message.reply_text("❌ אין תמונה שמורה.")

@app.on_message(filters.command("del_thumb"))
async def del_thumb(client, message):
    path = os.path.join(THUMB_DIR, f"{message.from_user.id}.jpg")
    if os.path.exists(path):
        os.remove(path)
        await message.reply_text("🗑 התמונה נמחקה.")
    else:
        await message.reply_text("❌ אין מה למחוק.")

@app.on_message(filters.photo & filters.private)
async def save_photo(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    await message.download(file_name=path)
    if prepare_thumb(path):
        await message.reply_text("✅ **התמונה נשמרה באיכות גבוהה!**", quote=True)

@app.on_message(filters.video | filters.document)
async def media_handler(client, message):
    # MediaInfo
    if message.caption and message.caption.startswith("/mediainfo"):
        await run_mi(client, message)
        return

    # Thumbnail Change
    user_id = message.from_user.id
    thumb_path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    
    if os.path.exists(thumb_path):
        msg = await message.reply("⚡ **מבצע החלפה מהירה...**", quote=True)
        try:
            file_id = message.video.file_id if message.video else message.document.file_id
            width, height = get_image_dimensions(thumb_path)
            
            # שליחת הוידאו עם פרמטרים שמכריחים את טלגרם להציג את התמונה החדשה
            await client.send_video(
                chat_id=message.chat.id,
                video=file_id,
                thumb=thumb_path,
                width=width,
                height=height,
                duration=getattr(message.video, "duration", 0), # חשוב לסנכרון
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
        await run_mi(client, message.reply_to_message)
    else:
        await message.reply("❌ הגב על קובץ.")

async def run_mi(client, message):
    status = await message.reply("⏳ **מנתח...**", quote=True)
    tmp = f"mi_{message.id}.dat"
    try:
        f_obj = message.video or message.document or message.audio
        async with aiofiles.open(tmp, "wb") as f:
            async for chunk in client.stream_media(f_obj):
                await f.write(chunk)
                if os.path.getsize(tmp) >= CHUNK_LIMIT: break
        
        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{tmp}"', stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        
        if output:
            html = parse_media_info(output, f_obj.file_size)
            telegraph = Telegraph()
            await telegraph.create_account(short_name="MediaBot")
            page = await telegraph.create_page(title="MediaInfo", html_content=html)
            await status.edit(f"✅ [לחץ כאן לצפייה במידע]({page['url']})")
        else:
            await status.edit("❌ לא נמצא מידע.")
    except Exception as e:
        await status.edit(f"❌ שגיאה: {e}")
    finally:
        if os.path.exists(tmp): os.remove(tmp)

if __name__ == "__main__":
    app.run()

