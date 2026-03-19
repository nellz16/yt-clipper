import os
import json
import subprocess
import telebot
from flask import Flask
from threading import Thread
from datetime import datetime

# --- 1. VARIABEL RAHASIA ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# --- 2. KODE PEKERJA KAGGLE ---
KAGGLE_WORKER_CODE = """
import os
import subprocess
import requests
import traceback
import json

def send_telegram_msg(text):
    url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_api, data={"chat_id": CHAT_ID, "text": text})

def run_worker():
    try:
        send_telegram_msg("⚙️ Mesin Kaggle menyala! Memulai instalasi yt-dlp...")
        subprocess.run("pip install -q yt-dlp", shell=True, check=True)
        
        # --- LOGIKA MODE MANUAL VS HEATMAP ---
        if MANUAL_TIME != "none":
            send_telegram_msg(f"⏱️ Mode Manual Aktif! Memotong pada durasi: {MANUAL_TIME}")
            # Format yt-dlp untuk time-range adalah *START-END
            download_section = f'--download-sections "*{MANUAL_TIME}"'
        else:
            send_telegram_msg("🔍 Memindai Heatmap untuk mencari momen paling viral...")
            info_cmd = f'yt-dlp --dump-json {URL}'
            try:
                info_json = subprocess.check_output(info_cmd, shell=True, text=True)
                info = json.loads(info_json)
                heatmap = info.get('heatmap')
                
                if heatmap:
                    # Urutkan heatmap dari skor tertinggi ke terendah
                    heatmap_sorted = sorted(heatmap, key=lambda x: x.get('value', 0), reverse=True)
                    
                    top_peaks = []
                    # Filter agar momen tidak berdekatan (minimal jarak 60 detik antar momen)
                    for p in heatmap_sorted:
                        p_time = int(p.get('start_time', 0))
                        if all(abs(p_time - existing) > 60 for existing in top_peaks):
                            top_peaks.append(p_time)
                        if len(top_peaks) >= 3:
                            break
                    
                    if top_peaks:
                        # Buat daftar Top 3 untuk dikirim ke Telegram
                        msg = "🔥 Top Momen Paling Replayed:\\n"
                        for i, t in enumerate(top_peaks, 1):
                            mins, secs = divmod(t, 60)
                            msg += f"{i}. Menit {mins:02d}:{secs:02d}\\n"
                        send_telegram_msg(msg)
                        
                        # Pilih Juara 1 (Tertinggi)
                        peak_time = top_peaks[0]
                        
                        # Taruh Puncak Klimaks di TENGAH (Mundur 30 detik dari puncak)
                        start_time = max(0, peak_time - 30)
                        end_time = start_time + 60  # Total durasi 60 detik
                        
                        mins_s, secs_s = divmod(start_time, 60)
                        mins_e, secs_e = divmod(end_time, 60)
                        send_telegram_msg(f"✂️ Mengambil Juara 1: Dipotong dari {mins_s:02d}:{secs_s:02d} - {mins_e:02d}:{secs_e:02d} (Klimaks di tengah!)")
                        
                        download_section = f'--download-sections "*{start_time}-{end_time}"'
                    else:
                        send_telegram_msg("⚠️ Heatmap tidak valid. Memotong 1 menit pertama...")
                        download_section = '--download-sections "*0-60"'
                else:
                    send_telegram_msg("⚠️ Video ini tidak memiliki Heatmap (Video baru/Sepi). Memotong 1 menit pertama...")
                    download_section = '--download-sections "*0-60"'
            except Exception as e:
                send_telegram_msg("⚠️ Gagal membaca Heatmap. Memotong 1 menit pertama...")
                download_section = '--download-sections "*0-60"'
        
        # --- PROSES UNDUH & FFmpeg ---
        send_telegram_msg("⬇️ Sedang mengunduh video...")
        download_cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" {download_section} -o "input.mp4" {URL}'
        subprocess.run(download_cmd, shell=True, check=True)
        
        if FACE_POS in ['br', 'bl', 'tr', 'tl']:
            send_telegram_msg(f"✂️ Menerapkan Split Screen Facecam ({FACE_POS.upper()})...")
            if FACE_POS == "br": face_pos_str = "iw-ow:ih-oh"
            elif FACE_POS == "bl": face_pos_str = "0:ih-oh"
            elif FACE_POS == "tr": face_pos_str = "iw-ow:0"
            elif FACE_POS == "tl": face_pos_str = "0:0"
            
            filter_complex = (
                f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; "
                f"[0:v]crop=ih*0.5:ih*0.333:{face_pos_str},scale=1080:720[bottom]; "
                f"[top][bottom]vstack[outv]"
            )
            ffmpeg_cmd = f'ffmpeg -i input.mp4 -filter_complex "{filter_complex}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        else:
            send_telegram_msg("✂️ Memotong vertikal standar (Tengah Layar)...")
            ffmpeg_cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*(9/16):ih" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
            
        subprocess.run(ffmpeg_cmd, shell=True, check=True)
        
        send_telegram_msg("🚀 Selesai! Mengirim video Shorts ke Anda...")
        with open('output.mp4', 'rb') as video_file:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(url_api, data={"chat_id": CHAT_ID, "caption": "✅ Video berhasil diproses!"}, files={"video": video_file})
            
    except Exception as e:
        error_trace = traceback.format_exc()
        send_telegram_msg(f"❌ ERROR DI KAGGLE:\\n{str(e)}\\n\\nTraceback:\\n{error_trace[:800]}")

run_worker()
"""

# --- 3. LOGIKA BOT TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID: return bot.reply_to(message, "⛔ Akses Ditolak.")
    pesan_bantuan = (
        "🤖 *Bot YouTube Clipper Pro*\n\n"
        "Kirim link YouTube untuk dipotong!\n\n"
        "🛠️ *Cara Penggunaan Ekstra:*\n"
        "Kamu bisa gabungkan posisi wajah & menit manual.\n"
        "- *Posisi Wajah:* `br`, `bl`, `tr`, `tl`\n"
        "- *Waktu Manual:* `01:10-02:00`\n\n"
        "Contoh Auto Heatmap:\n`https://youtu.be/xyz br`\n\n"
        "Contoh Manual Cut:\n`https://youtu.be/xyz br 09:10-10:01`"
    )
    bot.reply_to(message, pesan_bantuan, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_youtube_link(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    args = message.text.strip().split()
    url = args[0]
    
    if "youtube.com" not in url and "youtu.be" not in url:
        return bot.reply_to(message, "⚠️ Mohon kirimkan link YouTube yang valid.")

    # PARSING PARAMETER PINTAR (Face Position & Manual Time)
    face_pos = "none"
    manual_time = "none"
    
    for arg in args[1:]:
        if arg.lower() in ['br', 'bl', 'tr', 'tl']:
            face_pos = arg.lower()
        elif "-" in arg and (":" in arg or arg.replace("-", "").isdigit()):
            manual_time = arg

    bot.reply_to(message, f"⏳ Link diterima!\nPosisi Wajah: {face_pos.upper()}\nWaktu: {'Otomatis (Heatmap)' if manual_time == 'none' else manual_time}\nMengirim ke mesin Kaggle...")

    os.makedirs("kaggle_task", exist_ok=True)

    worker_vars = f"""
URL = "{url}"
CHAT_ID = "{message.chat.id}"
BOT_TOKEN = "{TOKEN}"
FACE_POS = "{face_pos}"
MANUAL_TIME = "{manual_time}"
"""
    script_content = worker_vars + KAGGLE_WORKER_CODE
    
    with open("kaggle_task/script.py", "w") as f:
        f.write(script_content)

    # NAMA TASK DINAMIS BERDASARKAN JAM SAAT INI
    task_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug_id = f"yt-clipper-{task_time}"

    metadata = {
      "id": f"{KAGGLE_USERNAME}/{slug_id}",
      "title": slug_id,
      "code_file": "script.py",
      "language": "python",
      "kernel_type": "script",
      "is_private": "true",
      "enable_gpu": "true",
      "enable_internet": "true"
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f:
        json.dump(metadata, f)

    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True, capture_output=True, text=True)
        bot.send_message(message.chat.id, f"✅ Tugas `{slug_id}` sukses dikirim ke Kaggle!")
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr if e.stderr else e.stdout
        bot.send_message(message.chat.id, f"❌ Gagal mengirim tugas.\n\nDetail:\n{error_detail}")

# --- 4. WEB SERVER UNTUK KOYEB ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Clipper Aktif!"
def run_web_server(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
