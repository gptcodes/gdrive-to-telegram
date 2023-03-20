import logging
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import BadRequest, FloodWait
from config import API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(level=logging.INFO)

# Initialize Pyrogram client
app = Client("gdrive_telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Define command handler
@app.on_message(filters.command("upload"))
async def upload_command_handler(client, message):
    # Check if user provided a Google Drive folder link
    if len(message.command) != 2:
        await message.reply("Please provide a Google Drive folder link in the following format: /upload drive_link")
        return

    # Extract folder ID from the Google Drive folder link
    folder_link = message.command[1]
    folder_id = folder_link.split("/")[-1]

    # Get Google Drive API credentials
    creds = Credentials.from_authorized_user_file("credentials.json")

    # Build the Google Drive API service
    service = build("drive", "v3", credentials=creds)

    # Get the list of files in the folder
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="nextPageToken, files(id, name, mimeType)").execute()
    files = results.get("files", [])

    if not files:
        await message.reply("No files found in the Google Drive folder.")
        return

    # Get total number of files
    total_files = len(files)
    done_files = 0

    # Loop through each file and upload it to Telegram
    for file in files:
        try:
            # Get file metadata
            file_id = file["id"]
            file_name = file["name"]
            file_mime_type = file["mimeType"]

            # Download the file from Google Drive
            file_path = f"{file_id}.{file_mime_type.split('/')[-1]}"
            request = service.files().get_media(fileId=file_id)
            with open(file_path, "wb") as f:
                downloader = request.get_downloader()
                done = 0
                while done < int(request.headers["Content-Length"]):
                    status = downloader.next_chunk()
                    done += status.num_bytes
                    await progress_callback(done, int(request.headers["Content-Length"]), message, done_files, total_files)
                    logging.info(f"{file_name}: Downloaded {done} / {request.headers['Content-Length']} bytes")

            # Upload the file to Telegram
            caption = file_name
            if file_mime_type.startswith("image"):
                # If the file is an image, set it as the caption
                caption = f"<b>{file_name}</b>"
                await client.send_photo(chat_id=message.chat.id, photo=file_path, caption=caption, progress=progress_callback, progress_args=(message, done_files, total_files))
            elif file_mime_type.startswith("video"):
                # If the file is a video, set it as the caption
                caption = f"<b>{file_name}</b>"
                await client.send_video(chat_id=message.chat.id, video=file_path, caption=caption, progress=progress_callback, progress_args=(message, done_files, total_files))
            else:
                # Otherwise, send it as a document
                await client.send_document(chat_id=message.chat.id, document=file_path, caption=caption, progress=progress_callback, progress_args=(message, done_files, total files))
                # Delete the file from the server after it has been uploaded to Telegram
                os.remove(file_path)
                done_files += 1
                logging.info(f"{file_name}: Uploaded to Telegram and deleted from server")

            except Exception as e:
                logging.error(f"{file_name}: {str(e)}")
                await message.reply(f"Failed to upload {file_name} to Telegram.")

        # Send a message showing which files have been uploaded
        uploaded_files = "\n".join([f'<a href="{file.link}">{file.name}</a>' for file in uploaded_files])
        await message.reply(f"The following files have been uploaded to Telegram:\n\n{uploaded_files}", parse_mode="html")

# Define start command handler
@app.on_message(filters.command("start"))
async def start_command_handler(client, message):
    # Greet the user and call them by their Telegram name
    user_name = message.from_user.first_name
    await message.reply(f"Hello, {user_name}! Welcome to the Google Drive to Telegram uploader bot. Use /upload to upload files from a Google Drive folder.")

# Define help command handler
@app.on_message(filters.command("help"))
async def help_command_handler(client, message):
    # Show instructions on how to use the bot
    instructions = "To use this bot, follow these steps:\n\n"
    instructions += "1. Share the Google Drive folder you want to upload from with the bot's Google account (email: bot-email-address@developer.gserviceaccount.com)\n"
    instructions += "2. Open the folder and copy the link from the address bar\n"
    instructions += "3. Use the /upload command followed by the Google Drive folder link\n\n"
    instructions += "Example: /upload https://drive.google.com/drive/folders/abc123def456\n\n"
    instructions += "The bot will upload all files in the folder to Telegram and send you a message with the list of uploaded files."

    await message.reply(instructions)
    
# Define progress callback function
async def progress_callback(current: int, total: int, message: Message, done_files: int, total_files: int):
    # Calculate progress percentage
    progress_percent = (current / total) * 100

    # Build progress message
    progress_message = f"Uploading {done_files + 1}/{total_files} files:\n"
    progress_message += f"{progress_percent:.2f}% - {current} / {total} bytes"

    # Update the message with the progress
    try:
        await message.edit(progress_message)
    except BadRequest as e:
        if e.message == "Message not modified":
            pass
        else:
            raise e


# Run the client
app.run()
