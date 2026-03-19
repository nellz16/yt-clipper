import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread

# --- 1. AMBIL VARIABEL ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA KAGGLE ---
# (Ini adalah template yang akan dikirim ke mesin Kaggle)
KAGGLE_WORKER_CODE = """
import os
import requests

URL = "{url}"
CHAT_ID = "{chat_id}"
BOT_TOKEN = "{bot_token}"

def run_worker():
    print("Memulai Pekerja di Kaggle...")
    os.system("pip install -q yt-dlp")
    
    print("Mengunduh video...")
    download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" --download-sections "*00:00:00-00:01:00" -o "input.mp4" {{URL}}'
    os.system(download_cmd)
    
    print("Memotong ke vertikal 9:16...")
    ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:a copy -y output.mp4'
    os.system(ffmpeg_cmd)
    
    print("Mengirim kembali ke Telegram...")
    with open('output.mp4', 'rb') as video_file:
        url_api = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendVideo"
        requests.post(url_api, data={{"chat_id": CHAT_ID, "caption": "✅ Video diproses dengan Kaggle!"}}, files={{"video": video_file}})
        
run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID:
        return bot.reply_to(message, "⛔ Akses Ditolak.")
    bot.reply_to(message, "🤖 Bot YT Clipper Ready!")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    url = message.text
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    bot.reply_to(message, "⏳ Link diterima! Mengontak Server...")

    os.makedirs("kaggle_task", exist_ok=True)

    # Injeksi URL ke template
    script_content = KAGGLE_WORKER_CODE.format(url=url, chat_id=message.chat.id, bot_token=TOKEN)
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    # Metadata untuk Kaggle
    metadata = {
      "id": f"{KAGGLE_USERNAME}/yt-clipper-task",
      "title": "YT Clipper Auto Task",
      "code_file": "script.py",
      "language": "python",
      "kernel_type": "script",
      "is_private": "true",
      "enable_gpu": "true",
      "enable_internet": "true"
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f:
        json.dump(metadata, f)

    # Kirim ke Kaggle! (Otomatis menggunakan KAGGLE_API_TOKEN dari env Koyeb)
    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True)
        bot.send_message(message.chat.id, "🚀 Script dikirim ke Kaggle!")
    except subprocess.CalledProcessError as e:
        bot.send_message(message.chat.id, f"❌ Gagal memicu Kaggle. Error: {e}")

# --- 4. DUMMY WEB SERVER UNTUK KOYEB ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot YT Clipper berjalan!"

def run_web_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    print("Bot menyala dan memantau chat...")
    bot.infinity_polling()
