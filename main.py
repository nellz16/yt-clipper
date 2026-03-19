import os
import json
import subprocess
import telebot

# --- 1. MENGAMBIL DATA RAHASIA DARI ENVIRONMENT (KEAMANAN) ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

# Inisialisasi Bot
bot = telebot.TeleBot(TOKEN)

# --- 2. TEMPLATE KODE PEKERJA KAGGLE ---
# Kode inilah yang akan dikirim ke GPU Kaggle untuk dieksekusi
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests

URL = "{url}"
CHAT_ID = "{chat_id}"
BOT_TOKEN = "{bot_token}"

def run_worker():
    print("Mulai memproses video...")
    # 1. Install library yang dibutuhkan di mesin Kaggle
    os.system("pip install -q yt-dlp")
    
    # 2. Download Video Kualitas Terbaik (Format MP4)
    # Catatan: Di sini kita batasi download bagian awal saja agar cepat saat testing
    # Untuk versi full, hapus argumen --download-sections
    download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" --download-sections "*00:00:00-00:01:00" -o "input.mp4" {{URL}}'
    os.system(download_cmd)
    
    # 3. Proses Editing dengan FFmpeg (Crop Vertikal 9:16 untuk Shorts/TikTok)
    # Kaggle sudah memiliki FFmpeg bawaan yang sangat cepat
    ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:a copy -y output.mp4'
    os.system(ffmpeg_cmd)
    
    # 4. Kirim Hasil Kembali ke Telegram via API
    print("Mengirim video ke Telegram...")
    with open('output.mp4', 'rb') as video_file:
        url_api = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendVideo"
        data = {{"chat_id": CHAT_ID, "caption": "✅ Video Shorts Anda selesai diproses oleh GPU Kaggle!"}}
        requests.post(url_api, data=data, files={{"video": video_file}})
        
run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID:
        return bot.reply_to(message, "⛔ Akses Ditolak. Anda tidak diizinkan menggunakan bot ini.")
    bot.reply_to(message, "🤖 Bot YouTube Clipper Ready!\nKirimkan link YouTube untuk mulai memotong video.")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    # Keamanan: Cek apakah yang chat adalah pemilik bot
    if message.chat.id != ALLOWED_USER_ID:
        return

    url = message.text
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    bot.reply_to(message, "⏳ Link diterima! Sedang membangunkan server GPU Kaggle. Harap tunggu sekitar 2-5 menit...")

    # Buat direktori sementara untuk menyiapkan file Kaggle
    os.makedirs("kaggle_task", exist_ok=True)

    # Siapkan script Python dengan menyisipkan URL dan Token
    script_content = KAGGLE_WORKER_CODE.format(url=url, chat_id=message.chat.id, bot_token=TOKEN)
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    # Siapkan Metadata agar Kaggle tahu ini tugas apa (Enable GPU = true)
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

    # Dorong (Push) tugas ke Kaggle menggunakan Terminal (Subprocess)
    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True)
        bot.send_message(message.chat.id, "🚀 Tugas berhasil dikirim ke Pabrik GPU! Bot akan diam sampai Kaggle mengirimkan video ke chat ini.")
    except subprocess.CalledProcessError as e:
        bot.send_message(message.chat.id, f"❌ Gagal memicu Kaggle. Pastikan KAGGLE_USERNAME dan KAGGLE_KEY di Environment Variables sudah benar.\nError: {e}")

# Jalankan bot secara terus menerus (Polling)
print("Bot menyala dan memantau chat...")
bot.infinity_polling()
