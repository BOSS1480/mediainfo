import os
import asyncio
import secrets
import logging
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegraph.aio import Telegraph
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

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

MSG_START = (
    "👋 **שלום! אני בוט לניהול מדיה.**\n\n"
    "אני יכול לעזור לך:\n"
    "🔹 לחלץ מידע טכני (MediaInfo) במהירות.\n"
    "🔹 לנהל תמונות ממוזערות (Thumbnails).\n"
    "🔹 להחליף תמונות לוידאו ללא הורדה מחדש.\n\n"
    "לחץ על הכפתור למטה לעזרה ותפריטים 👇"
)

MSG_HELP_MAIN = "📚 **מרכז העזרה**\n\nבחר את הנושא שמעניין אותך:"

MSG_HELP_MEDIAINFO = (
    "📝 **עזרה: MediaInfo**\n\n"
    "כדי לקבל מידע טכני על קובץ:\n"
    "1. שלח לי את הקובץ (וידאו/אודיו).\n"
    "2. הגב עליו עם הפקודה `/mediainfo`.\n"
    "3. אני אוריד רק את ההתחלה (20MB) ואפיק דוח מלא."
)

MSG_HELP_THUMB = (
    "🖼 **עזרה: תמונה ממוזערת**\n\n"
    "כדי להגדיר תמונה קבועה:\n"
    "1. שלח לי תמונה רגילה.\n"
    "2. אני אשמור אותה אוטומטית.\n\n"
    "מעכשיו, כל וידאו שתשלח לי - יוחזר אליך מיד עם התמונה החדשה!\n\n"
    "🗑 מחיקת תמונה: `/del_thumb`\n"
    "👀 צפייה בתמונה: `/view_thumb`"
)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("עזרה ותפריטים 📚", callback_data="help_main")]
    ])
    await message.reply_text(MSG_START, reply_markup=keyboard, quote=True)

@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    data = callback.data
    
    if data == "help_main":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("מדיה אינפו 📝", callback_data="help_mediainfo"),
                InlineKeyboardButton("תמונה ממוזערת 🖼", callback_data="help_thumb")
            ],
            [InlineKeyboardButton("חזרה לתפריט ראשי 🔙", callback_data="start_menu")]
        ])
        await callback.message.edit_text(MSG_HELP_MAIN, reply_markup=keyboard)

    elif data == "help_mediainfo":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("חזרה 🔙", callback_data="help_main")]
        ])
        await callback.message.edit_text(MSG_HELP_MEDIAINFO, reply_markup=keyboard)

    elif data == "help_thumb":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("חזרה 🔙", callback_data="help_main")]
        ])
        await callback.message.edit_text(MSG_HELP_THUMB, reply_markup=keyboard)

    elif data == "start_menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("עזרה ותפריטים 📚", callback_data="help_main")]
        ])
        await callback.message.edit_text(MSG_START, reply_markup=keyboard)

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    await message.download(file_name=path)
    await message.reply_text("✅ **התמונה נשמרה!**", quote=True)

@app.on_message(filters.command("view_thumb"))
async def view_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    if os.path.exists(path):
        await message.reply_photo(path, caption="🖼 **זו התמונה הממוזערת שלך.**")
    else:
        await message.reply_text("❌ אין לך תמונה שמורה.", quote=True)

@app.on_message(filters.command("del_thumb"))
async def delete_thumbnail(client, message):
    user_id = message.from_user.id
    path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
    if os.path.exists(path):
        os.remove(path)
        await message.reply_text("🗑 **התמונה נמחקה.**", quote=True)
    else:
        await message.reply_text("❌ אין תמונה למחוק.", quote=True)

@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    if message.caption and message.caption.startswith("/mediainfo"):
        await process_mediainfo(client, message)
        return

    user_id = message.from_user.id
    thumb_path = os.path.join(THUMB_DIR, f"{user_id}.jpg")

    if os.path.exists(thumb_path):
        msg = await message.reply("⚡ **מעבד תמונה...**", quote=True)
        try:
            await client.send_video(
                chat_id=message.chat.id,
                video=message.video.file_id if message.video else message.document.file_id,
                thumb=thumb_path,
                caption=message.caption or "",
                supports_streaming=True
            )
            await msg.delete()
        except Exception as e:
            await msg.edit(f"❌ שגיאה: {e}")

@app.on_message(filters.command("mediainfo"))
async def mediainfo_command_handler(client, message):
    if message.reply_to_message:
        target = message.reply_to_message
        if target.video or target.document or target.audio:
            await process_mediainfo(client, target)
        else:
            await message.reply("❌ הגב על קובץ מדיה.", quote=True)
    else:
        await message.reply("❌ יש להגיב על קובץ או לשלוח קובץ עם כיתוב `/mediainfo`.", quote=True)

async def create_telegraph_page(title, content):
    telegraph = Telegraph()
    await telegraph.create_account(short_name="MediaBot")
    response = await telegraph.create_page(title=title, html_content=content)
    return response['url']

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
        
        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{file_path}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        
        if output:
            formatted_out = output.replace("\n", "<br>")
            link = await create_telegraph_page("MediaInfo Result", f"<pre>{formatted_out}</pre>")
            await status.edit(
                f"✅ **MediaInfo מוכן!**\n"
                f"📂 קובץ: `{getattr(file_obj, 'file_name', 'Unknown')}`\n"
                f"🔗 [לחץ כאן לצפייה בנתונים]({link})",
                disable_web_page_preview=False
            )
        else:
            await status.edit("❌ שגיאה בקריאת המידע.")

    except Exception as e:
        await status.edit(f"❌ שגיאה: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    app.run()


