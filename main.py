import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread

# --- 1. VARIABEL RAHASIA ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA KAGGLE (DENGAN ERROR HANDLING) ---
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback

URL = "{url}"
CHAT_ID = "{chat_id}"
BOT_TOKEN = "{bot_token}"

def send_telegram_msg(text):
    # Fungsi pembantu untuk mengirim teks biasa ke Telegram
    url_api = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendMessage"
    requests.post(url_api, data={{"chat_id": CHAT_ID, "text": text}})

def run_worker():
    try:
        # Beri kabar bahwa mesin Kaggle sudah berhasil menyala
        send_telegram_msg("⚙️ Mesin Kaggle menyala! Memulai proses instalasi dan unduh...")
        
        # 1. Install library (check=True agar jika gagal internet, masuk ke error)
        subprocess.run("pip install -q yt-dlp", shell=True, check=True)
        
        # 2. Unduh Video
        send_telegram_msg("⬇️ Sedang mengunduh video dari YouTube...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" --download-sections "*00:00:00-00:01:00" -o "input.mp4" {{URL}}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        # 3. Potong Vertikal 9:16
        send_telegram_msg("✂️ Sedang memotong video ke rasio vertikal (9:16)...")
        ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:a copy -y output.mp4'
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        # 4. Kirim Video
        send_telegram_msg("🚀 Proses selesai! Mengirim video ke chat Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendVideo"
            requests.post(url_api, data={{"chat_id": CHAT_ID, "caption": "✅ Video berhasil diproses!"}}, files={{"video": video_file}})
            
    except subprocess.CalledProcessError as e:
        # Menangkap error jika yt-dlp atau ffmpeg gagal jalan
        error_msg = f"❌ Gagal saat menjalankan perintah (yt-dlp/ffmpeg).\\nKode Error: {{e.returncode}}"
        send_telegram_msg(error_msg)
        
    except Exception as e:
        # Menangkap semua jenis error sistem (termasuk internet gagal, dll)
        error_trace = traceback.format_exc()
        error_msg = f"❌ ERROR FATAL DI KAGGLE:\\n\\n{{str(e)}}\\n\\nTraceback (Detail):\\n{{error_trace[:800]}}"
        send_telegram_msg(error_msg)

run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID:
        return bot.reply_to(message, "⛔ Akses Ditolak.")
    bot.reply_to(message, "🤖 Bot YouTube Clipper Ready!\nKirimkan link YouTube untuk memulai.")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    url = message.text
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    bot.reply_to(message, "⏳ Link diterima! Mengirim tugas ke Pabrik GPU Kaggle...")

    os.makedirs("kaggle_task", exist_ok=True)

    script_content = KAGGLE_WORKER_CODE.format(url=url, chat_id=message.chat.id, bot_token=TOKEN)
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    metadata = {
      "id": f"{KAGGLE_USERNAME}/yt-clipper-task",
      "title": "YT Clipper Auto Task",
      "code_file": "script.py",
      "language": "python",
      "kernel_type": "script",
      "is_private": True,
      "enable_gpu": True,
      "enable_internet": True
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f:
        json.dump(metadata, f)

    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True)
        bot.send_message(message.chat.id, "✅ Tugas sukses dikirim ke Kaggle! Bot akan memberikan update status secara real-time.")
    except subprocess.CalledProcessError as e:
        bot.send_message(message.chat.id, f"❌ Gagal mengirim tugas dari Koyeb ke Kaggle. Error: {e}")

# --- 4. DUMMY WEB SERVER UNTUK KOYEB ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot YouTube Clipper berjalan aktif!"

def run_web_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    print("Bot menyala dan memantau chat...")
    bot.infinity_polling()
