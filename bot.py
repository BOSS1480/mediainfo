import logging
import os
import re
from pyrogram import Client, filters
from aiohttp import ClientSession
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, path as aiopath, mkdir
import asyncio

# הגדרת טוקן, API ID ו-API HASH
API_ID = ""
API_HASH = ""
TOKEN = ""

AUTHORIZED_USER_ID = 6335855540  # המנהל המורשה

# יצירת Client עם API ID ו-API HASH
bot = Client("mediainfo_bot", bot_token=TOKEN, api_id=API_ID, api_hash=API_HASH)

# Callback להתקדמות הורדה עבור קבצים קטנים (עד 50MB)
def progress_callback(current, total, temp_send):
    percent = int(current * 100 / total)
    if percent - progress_callback.last_update >= 10 or percent == 100:
        progress_callback.last_update = percent
        asyncio.create_task(temp_send.edit(f"<i>הורדה... {percent}%</i>"))
progress_callback.last_update = 0

# פונקציה שתבצע MediaInfo, תוריד את הקובץ ותכתוב את התוצאה לקובץ .txt
async def gen_mediainfo(message, link=None, media=None, mmsg=None):
    temp_send = await message.reply("<i>מתחיל עיבוד MediaInfo...</i>", reply_to_message_id=message.id)
    try:
        download_path = "Mediainfo/"
        if not await aiopath.isdir(download_path):
            await mkdir(download_path)

        if link:
            # הורדת קובץ מקישור עם עדכון התקדמות
            filename_match = re.search(r".+/(.+)", link)
            if not filename_match:
                raise Exception("לא ניתן לחלץ שם קובץ מהקישור.")
            filename = filename_match.group(1)
            des_path = os.path.join(download_path, filename)
            headers = {"user-agent": "Mozilla/5.0"}
            async with ClientSession() as session:
                async with session.get(link, headers=headers) as response:
                    total = response.content_length
                    downloaded = 0
                    last_percent = 0
                    async with aiopen(des_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(5000000):  # 5MB בכל פעם
                            await f.write(chunk)
                            if total:
                                downloaded += len(chunk)
                                percent = int(downloaded * 100 / total)
                                if percent - last_percent >= 10 or percent == 100:
                                    last_percent = percent
                                    await temp_send.edit(f"<i>הורדה... {percent}%</i>")
        elif media:
            des_path = os.path.join(download_path, media.file_name)
            if media.file_size <= 50000000:  # עד 50MB - שימוש בהורדה עם callback
                progress_callback.last_update = 0
                await mmsg.download(des_path, progress=progress_callback, progress_args=(temp_send,))
            else:
                # הורדה סטרימינג עבור קבצים גדולים, עם עדכון אחוזים
                downloaded = 0
                last_percent = 0
                async with aiopen(des_path, "wb") as f:
                    async for chunk in bot.stream_media(media, limit=5):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if media.file_size:
                            percent = int(downloaded * 100 / media.file_size)
                            if percent - last_percent >= 10 or percent == 100:
                                last_percent = percent
                                await temp_send.edit(f"<i>הורדה... {percent}%</i>")
        else:
            raise Exception("לא סופק קישור או מדיה להורדה.")

        # הפעלת MediaInfo על הקובץ שהורד
        stdout = os.popen(f'mediainfo "{des_path}"').read()
        result_text = f"📌 {os.path.basename(des_path)}\n\n"
        if stdout:
            result_text += stdout
        else:
            result_text += "לא נמצאו נתונים מ־MediaInfo."

        # כתיבת התוצאה לקובץ .txt עם שם ייחודי
        txt_filename = f"Mediainfo_{message.id}.txt"
        txt_filepath = os.path.join(download_path, txt_filename)
        async with aiopen(txt_filepath, "w", encoding="utf-8") as txt_file:
            await txt_file.write(result_text)

    except Exception as e:
        logging.error(e)
        await temp_send.edit(f"MediaInfo נעצר בגלל: {str(e)}")
        return
    finally:
        if await aiopath.exists(des_path):
            await aioremove(des_path)

    # שליחת קובץ הטקסט עם התוצאות בתגובה להודעה המקורית
    await message.reply_document(
        document=txt_filepath, 
        caption="תוצאות MediaInfo:", 
        reply_to_message_id=message.id
    )
    await temp_send.delete()

    # מחיקת קובץ הטקסט לאחר השליחה
    await aioremove(txt_filepath)

# Handler לפקודת /mediainfo בקבוצות – ההודעה נשלחת כריפליי
@bot.on_message(filters.group & filters.command(["mediainfo"]))
async def mediainfo_group(client, message):
    rply = message.reply_to_message
    help_msg = "<b>על מנת להשתמש:</b>\n• שלח קישור או מדיה עם הפקודה /mediainfo בתגובה או בטקסט."
    if (len(message.command) > 1) or (rply and rply.text):
        link = None
        if rply and rply.text and re.search(r"https?://", rply.text):
            link = rply.text
        elif len(message.command) > 1:
            link = message.command[1]
        if link:
            return await gen_mediainfo(message, link=link)
    if rply:
        file = next(
            (
                i
                for i in [
                    rply.document,
                    rply.video,
                    rply.audio,
                    rply.voice,
                    rply.animation,
                    rply.video_note,
                ]
                if i is not None
            ),
            None,
        )
        if file:
            return await gen_mediainfo(message, media=file, mmsg=rply)
    return await message.reply(help_msg, reply_to_message_id=message.id)

# Handler להודעות בפרטי – אם נשלח קישור או מדיה ללא פקודה, התגובה נשלחת כריפליי
@bot.on_message(filters.private & ~filters.command(["mediainfo", "start"]))
async def mediainfo_private(client, message):
    if message.text and re.search(r"https?://", message.text):
        await gen_mediainfo(message, link=message.text)
    elif any(
        getattr(message, attr, None)
        for attr in ["document", "video", "audio", "voice", "animation", "video_note"]
    ):
        media = (
            message.document
            or message.video
            or message.audio
            or message.voice
            or message.animation
            or message.video_note
        )
        await gen_mediainfo(message, media=media, mmsg=message)
    else:
        await message.reply("אנא שלח קישור או קובץ/וידאו כדי לבצע MediaInfo.", reply_to_message_id=message.id)

# Handler לפקודת /start – הודעת פתיחה מעוצבת, נשלחת כריפליי
@bot.on_message(filters.command("start"))
async def start(client, message):
    start_text = (
        "**👋 היי!**\n\n"
        "**אני בוט mediainfo.**\n\n"
        "📥 **איך משתמשים?**\n"
        " **פשוט שלח לי קובץ/וידאו שאתב רוצב לקסל עליו פרטים, ואני אחזיר לך פרטים בקובץ `.txt`**\n"
        "**בקבוצות צריך להגיב על הקובץ/קישור עם הפקודה `/mediainfo`.\n\n"
        "🤖 נוצר ע\"י: @The_Joker_Bots"
    )
    await message.reply(start_text, reply_to_message_id=message.id)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
