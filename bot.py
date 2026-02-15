import os
import asyncio
import secrets
import aiofiles
import shutil
import subprocess
import logging
from pyrogram import Client, filters, enums
from telegraph.aio import Telegraph
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

if shutil.which("mediainfo") is None:
    print("⚠️ Mediainfo לא נמצא! מנסה להתקין אוטומטית...")
    try:
        subprocess.run("apt-get update && apt-get install -y mediainfo", shell=True, check=True)
        print("✅ Mediainfo הותקן בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה בהתקנה אוטומטית: {e}")
        print("חובה להתקין ידנית: sudo apt-get install mediainfo")

app = Client(
    "MediaInfoBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

CHUNK_LIMIT = 20 * 1024 * 1024 

section_dict = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠", "Menu": "🗃"}

async def create_telegraph_page(title, content):
    telegraph = Telegraph()
    me = await app.get_me()
    author_name = me.first_name
    author_url = f"https://t.me/{me.username}"

    await telegraph.create_account(
        short_name=secrets.token_hex(4),
        author_name=author_name,
        author_url=author_url
    )
    
    response = await telegraph.create_page(
        title=title,
        html_content=content,
        author_name=author_name,
        author_url=author_url
    )
    return response['url']

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
        
        if found_section:
            continue

        if line.startswith("File size"):
            line = size_line
        
        if trigger:
            tc += "<br><pre>"
            trigger = False
        
        tc += line + "\n"
    
    tc += "</pre><br>"
    return tc

@app.on_message(filters.command("start"))
async def start_command(client, message):
    text = (
        f"**היי {message.from_user.mention} 👋**\n"
        "**אני בוט מדיה אינפו**\n\n"
        "**• פשוט שלח לי קובץ/וידאו אני אתן לך מידע עליו מ-mediainfo.**"
    )
    await message.reply_text(text, quote=True)

@app.on_message(filters.command("mediainfo") | (filters.private & (filters.document | filters.video | filters.audio)))
async def mediainfo_handler(client, message):
    target_msg = None
    
    if message.chat.type != enums.ChatType.PRIVATE:
        if not message.text or not message.text.startswith("/mediainfo"):
            return 
        if not message.reply_to_message:
            return await message.reply_text("❌ בקבוצות יש להגיב עם `/mediainfo` על הקובץ.", quote=True)
        target_msg = message.reply_to_message
    else:
        if message.text and message.text.startswith("/mediainfo"):
             if message.reply_to_message:
                 target_msg = message.reply_to_message
             else:
                 return await message.reply_text("❌ הגב על קובץ.", quote=True)
        else:
            target_msg = message

    file_obj = target_msg.video or target_msg.document or target_msg.audio
    
    if not file_obj:
        if message.chat.type == enums.ChatType.PRIVATE:
            return await message.reply("❌ לא זוהה קובץ מדיה תקין.", quote=True)
        return

    status = await message.reply("⏳ **בודק metadata...**", quote=True)
    
    file_path = f"mi_{target_msg.id}_{secrets.token_hex(2)}.dat"
    
    try:
        current_size = 0
        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in client.stream_media(file_obj):
                await f.write(chunk)
                current_size += len(chunk)
                if current_size >= CHUNK_LIMIT:
                    break

        await status.edit("⚙️ **מנתח מידע...**")

        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{file_path}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()

        if not output:
            return await status.edit("❌ **שגיאה:** לא התקבל מידע. ייתכן שהקובץ פגום או לא נתמך.")

        file_name = getattr(file_obj, "file_name", "Unknown File")
        parsed_content = parseinfo(output, file_obj.file_size)
        
        if not parsed_content or len(parsed_content) < 50:
             return await status.edit("❌ **לא נמצאו נתוני Metadata.**\n(ייתכן שהמידע נמצא בסוף הקובץ ולא בהתחלה)")

        final_html = f"<h4>📌 File: {file_name}</h4><br><br>{parsed_content}"
        
        await status.edit("📤 **יוצר דף...**")
        
        link = await create_telegraph_page("MediaInfo Result", final_html)
        
        await status.edit(
            f"✅ **MediaInfo נוצר בהצלחה!**\n\n📂 **קובץ:** `{file_name}`\n🔗 **קישור:** [לחץ כאן לצפייה]({link})",
            disable_web_page_preview=False
        )

    except Exception as e:
        await status.edit(f"❌ שגיאה בלתי צפויה: `{e}`")
        
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    print("🤖 הבוט מתחיל לרוץ...")
    app.run()


