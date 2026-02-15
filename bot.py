import os
import asyncio
import secrets
import aiofiles
import shutil
import subprocess
import logging
from pyrogram import Client, filters, enums
from telegraph.aio import Telegraph

if shutil.which("mediainfo") is None:
    print("⚠️ Mediainfo לא נמצא! מנסה להתקין אוטומטית...")
    try:
        subprocess.run("apt-get update && apt-get install -y mediainfo", shell=True, check=True)
        print("✅ Mediainfo הותקן בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה בהתקנה אוטומטית: {e}")
        print("ייתכן שצריך להריץ ידנית: sudo apt install -y mediainfo")
# -----------------------------------

CHUNK_LIMIT = 20 * 1024 * 1024 

section_dict = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠", "Menu": "🗃"}

async def create_telegraph_page(title, content, client):
    telegraph = Telegraph()
    me = await client.get_me()
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

    has_video = "Video" in out
    has_audio = "Audio" in out
    
    if not (has_video or has_audio):
        return None

    for line in out.split("\n"):
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

async def filter_smart(_, __, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return bool(message.video or message.document or message.audio)
    return False

smart_filter = filters.create(filter_smart)

@Client.on_message((filters.private & smart_filter) | filters.command("mediainfo"))
async def mediainfo_handler(client, message):
    if message.chat.type != enums.ChatType.PRIVATE:
        if not message.reply_to_message:
            return await message.reply("❌ הגב על קובץ כדי לקבל מידע.", quote=True)
        media_msg = message.reply_to_message
    else:
        media_msg = message.reply_to_message if message.reply_to_message else message

    file_obj = media_msg.video or media_msg.document or media_msg.audio
    
    if not file_obj:
        if message.chat.type == enums.ChatType.PRIVATE:
            return await message.reply("❌ שלח לי קובץ וידאו, אודיו או מסמך.", quote=True)
        return

    status = await message.reply("⏳ **קורא נתונים (מוריד 20MB ראשונים)...**", quote=True)
    
    file_path = f"mi_{media_msg.id}_{secrets.token_hex(2)}.dat"
    
    try:
        current_size = 0
        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in client.stream_media(file_obj):
                await f.write(chunk)
                current_size += len(chunk)
                if current_size >= CHUNK_LIMIT:
                    break

        await status.edit("⚙️ **מנתח Metadata...**")

        proc = await asyncio.create_subprocess_shell(
            f'mediainfo "{file_path}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()

        if not output:
            return await status.edit("❌ **שגיאה:** לא התקבל פלט מ-MediaInfo.")

        file_name = getattr(file_obj, "file_name", "Unknown File")
        parsed_content = parseinfo(output, file_obj.file_size)
        
        if parsed_content is None:
            return await status.edit("❌ **לא נמצאו נתונים עבור קובץ זה.**")

        final_html = f"<h4>📌 File: {file_name}</h4><br><br>{parsed_content}"
        
        await status.edit("📤 **יוצר דף...**")
        link = await create_telegraph_page("MediaInfo Result", final_html, client)
        
        await status.edit(
            f"✅ **MediaInfo נוצר בהצלחה!**\n\n📂 **קובץ:** `{file_name}`\n🔗 **קישור:** [לחץ כאן לצפייה]({link})",
            disable_web_page_preview=False
        )

    except Exception as e:
        await status.edit(f"❌ שגיאה: `{e}`")
        
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


