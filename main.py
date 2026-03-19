import os
import json
import subprocess
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
from threading import Thread
import logging
import time
from datetime import datetime
from kaggle.api.kaggle_api_extended import KaggleApi

# --- MENGHENINGKAN LOG KOYEB ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")

bot = telebot.TeleBot(TOKEN)

# Inisialisasi Kaggle Python API (Untuk fitur Auto-Delete)
api = KaggleApi()
api.authenticate()

user_states = {}

def fmt_t(seconds):
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

# --- KODE PEKERJA CLOUD (KAGGLE) ---
KAGGLE_WORKER_CODE = r"""
import os
import subprocess
import requests
import traceback
import json
import importlib
import numpy as np

def edit_msg(text, pct):
    bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
    full_text = f"[{bar}] {pct}% - {text}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", 
                  data={"chat_id": CHAT_ID, "message_id": MSG_ID, "text": full_text})

def fmt_t(seconds):
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        raise Exception(f"Perintah Gagal:\n{res.stderr}")

def analyze_video(video_path, requested_pos):
    import cv2
    importlib.invalidate_caches()
    cap = cv2.VideoCapture(video_path)
    step = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) // 15)
    face_boxes = []
    try:
        from mediapipe.python.solutions import face_detection as mp_faces
        with mp_faces.FaceDetection(model_selection=1, min_detection_confidence=0.4) as face_detection:
            for i in range(15):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
                ret, frame = cap.read()
                if not ret: break
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_detection.process(rgb_frame)
                if results.detections:
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        x, y, w, h = bbox.xmin, bbox.ymin, bbox.width, bbox.height
                        if 0.01 < w * h < 0.8: face_boxes.append((x, y, w, h))
    except: pass
    cap.release()

    if not face_boxes:
        if requested_pos in ['br', 'bl', 'tr', 'tl']: return "split_static", requested_pos
        return "irl", 0.5 

    def calc_crop(target_faces):
        avg_box = np.mean(target_faces, axis=0)
        xmin, ymin, w, h = avg_box
        is_giant = (w * h) > 0.04 
        mult = 3.5 if is_giant else 2.5
        c_w, c_h = min(1.0, w * mult), min(1.0, h * mult)
        c_x, c_y = max(0.0, xmin - (c_w - w)/2), max(0.0, ymin - (c_h - h)/2)
        if c_x + c_w > 1.0: c_x = 1.0 - c_w
        if c_y + c_h > 1.0: c_y = 1.0 - c_h
        return ("split_giant" if is_giant else "split_dynamic"), (c_x, c_y, c_w, c_h)

    if requested_pos in ['br', 'bl', 'tr', 'tl']:
        t_faces = []
        for (x, y, w, h) in face_boxes:
            cx, cy = x + w/2, y + h/2
            if requested_pos == 'br' and cx >= 0.5 and cy >= 0.5: t_faces.append((x,y,w,h))
            elif requested_pos == 'bl' and cx <= 0.5 and cy >= 0.5: t_faces.append((x,y,w,h))
            elif requested_pos == 'tr' and cx >= 0.5 and cy <= 0.5: t_faces.append((x,y,w,h))
            elif requested_pos == 'tl' and cx <= 0.5 and cy <= 0.5: t_faces.append((x,y,w,h))
        if t_faces: return calc_crop(t_faces)
        else: return "split_static", requested_pos

    corner, center = [], []
    for (x, y, w, h) in face_boxes:
        cx, cy = x + w/2, y + h/2
        if cx < 0.25 or cx > 0.75 or cy < 0.25 or cy > 0.75: corner.append((x, y, w, h))
        else: center.append((x, y, w, h))

    if corner: return calc_crop(corner)
    elif center: return "irl", np.mean(center, axis=0)[0] + np.mean(center, axis=0)[2]/2
    else: return "irl", 0.5

def main_process():
    edit_msg("Menyiapkan Mesin Cloud & AI...", 10)
    
    if FACE_POS in ['auto', 'br', 'bl', 'tr', 'tl']:
        run_cmd("pip install -q --upgrade yt-dlp opencv-python-headless mediapipe numpy")
    else:
        run_cmd("pip install -q --upgrade yt-dlp")

    # KARENA URL SUDAH LANGSUNG MENUJU CDN (MASTER.M3U8) ATAU YOUTUBE NORMAL,
    # KITA TIDAK PERLU IMPERSONATE LAGI.
    if MANUAL_TIME != "none":
        edit_msg(f"Mengunduh cuplikan [{MANUAL_TIME}]...", 30)
        dl_cmd = f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 --download-sections "*{MANUAL_TIME}" --force-keyframes-at-cuts -o "input.mp4" "{URL}"'
        run_cmd(dl_cmd)

    else:
        edit_msg("Memindai Grafik YouTube (Mencari Top 5)...", 20)
        try:
            info_json = subprocess.check_output(f'yt-dlp --dump-json "{URL}"', shell=True, text=True)
            info = json.loads(info_json)
            heatmap = info.get('heatmap')
            if heatmap:
                heatmap_sorted = sorted(heatmap, key=lambda x: x.get('value', 0), reverse=True)
                top_peaks = []
                for p in heatmap_sorted:
                    p_time = int(p.get('start_time', 0))
                    if all(abs(p_time - existing) > 60 for existing in top_peaks): top_peaks.append(p_time)
                    if len(top_peaks) >= 5: break
                
                if top_peaks:
                    peak1_s, peak1_e = max(0, top_peaks[0] - 30), max(0, top_peaks[0] - 30) + 60
                    target_time = f"{fmt_t(peak1_s)}-{fmt_t(peak1_e)}"
                    
                    ref_text = f"🔥 *Mengambil Juara 1 otomatis:* `{target_time}`\n\n*Referensi Momen Lainnya:*\n_(Klik teks angka untuk copy manual)_\n"
                    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
                    for i, peak in enumerate(top_peaks):
                        if i == 0: continue
                        s_t, e_t = max(0, peak - 30), max(0, peak - 30) + 60
                        ref_text += f"{medals[i]} Juara {i+1}: `{fmt_t(s_t)}-{fmt_t(e_t)}`\n"
                    
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                        data={"chat_id": CHAT_ID, "text": ref_text, "parse_mode": "Markdown"})
                    
                    edit_msg(f"Mengunduh cuplikan Juara 1...", 40)
                    dl_cmd = f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 --download-sections "*{peak1_s}-{peak1_e}" --force-keyframes-at-cuts -o "input.mp4" "{URL}"'
                    run_cmd(dl_cmd)
                else:
                    edit_msg("Heatmap tidak valid. Mengunduh 1 menit pertama...", 40)
                    run_cmd(f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 --download-sections "*0-60" -o "input.mp4" "{URL}"')
            else:
                edit_msg("Video tanpa Heatmap. Mengunduh 1 menit pertama...", 40)
                run_cmd(f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 --download-sections "*0-60" -o "input.mp4" "{URL}"')
        except Exception:
            edit_msg("Gagal baca Heatmap. Mengunduh 1 menit pertama...", 40)
            run_cmd(f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 --download-sections "*0-60" -o "input.mp4" "{URL}"')

    if FACE_POS == "pad": mode, data = "pad", None
    elif FACE_POS in ['auto', 'br', 'bl', 'tr', 'tl']:
        edit_msg("AI memindai tata letak objek...", 60)
        mode, data = analyze_video("input.mp4", FACE_POS)
    else: mode, data = "irl", "bypass"

    edit_msg("Merender mahakarya video...", 80)
    if mode == "pad":
        cmd = 'ffmpeg -i input.mp4 -vf "scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
    elif mode == "split_giant":
        c_x, c_y, c_w, c_h = data
        fc = f"[0:v]crop=ih*(9/8):ih:(iw-ow)/2:0,scale=1080:960[top]; [0:v]crop=iw*{c_w}:ih*{c_h}:iw*{c_x}:ih*{c_y},scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom]; [top][bottom]vstack[outv]"
        cmd = f'ffmpeg -i input.mp4 -filter_complex "{fc}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
    elif mode == "split_dynamic":
        c_x, c_y, c_w, c_h = data
        fc = f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; [0:v]crop=iw*{c_w}:ih*{c_h}:iw*{c_x}:ih*{c_y},scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720[bottom]; [top][bottom]vstack[outv]"
        cmd = f'ffmpeg -i input.mp4 -filter_complex "{fc}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
    elif mode == "split_static":
        p = "iw-ow:ih-oh" if data=="br" else "0:ih-oh" if data=="bl" else "iw-ow:0" if data=="tr" else "0:0"
        fc = f"[0:v]crop=ih*0.9:ih:(iw-ow)/2:0,scale=1080:1200[top]; [0:v]crop=ih*0.5:ih*0.333:{p},scale=1080:720[bottom]; [top][bottom]vstack[outv]"
        cmd = f'ffmpeg -i input.mp4 -filter_complex "{fc}" -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
    elif mode == "irl" and FACE_POS == "irl":
        cmd = 'ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
    else:
        fx = data if isinstance(data, (float, int)) else 0.5
        cmd = f'ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih:iw*{fx}-ow/2:0" -c:v libx264 -preset fast -crf 23 -c:a copy -y output.mp4'
        
    run_cmd(cmd)
    edit_msg("Selesai! Mengunggah hasil ke Telegram...", 100)
    with open("output.mp4", 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", data={"chat_id": CHAT_ID, "caption": "✅ Berhasil diproses oleh Mesin Cloud!"}, files={"video": f})

try:
    main_process()
except Exception as e:
    error_trace = traceback.format_exc()
    safe_error = error_trace[:800]
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", 
        data={"chat_id": CHAT_ID, "message_id": MSG_ID, "text": f"❌ Terjadi Kesalahan Sistem:\n\n{safe_error}"})
"""

# --- 3. ALUR BOT TELEGRAM & AUTO DELETE API ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id != ALLOWED_USER_ID: return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📺 YouTube", callback_data="platform_youtube"),
        InlineKeyboardButton("🟢 Kick (VOD)", callback_data="platform_kick")
    )
    bot.reply_to(message, "🤖 *Pabrik Video Aktif!*\n\nSilakan pilih platform sumber video:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('platform_'))
def handle_platform_selection(call):
    chat_id = call.message.chat.id
    platform = call.data.replace('platform_', '')
    
    # Cek apakah sedang ada proses berjalan
    if chat_id in user_states and user_states[chat_id].get('status') == 'processing':
        bot.answer_callback_query(call.id, "⏳ Harap tunggu proses sebelumnya selesai!", show_alert=True)
        return

    if platform == "youtube":
        user_states[chat_id] = {'platform': 'youtube', 'status': 'waiting_url'}
        bot.edit_message_text("📺 *Mode YouTube*\nSilakan kirimkan link YouTube yang valid.", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    elif platform == "kick":
        user_states[chat_id] = {'platform': 'kick', 'status': 'waiting_url'}
        bot.edit_message_text("🟢 *Mode Kick*\nSilakan kirimkan URL `master.m3u8` yang Anda dapatkan dari Developer Tools (F12).", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text.strip().startswith("http"))
def handle_url(message):
    chat_id = message.chat.id
    if chat_id != ALLOWED_USER_ID: return
    
    # Jika belum klik /start atau tidak ada state
    if chat_id not in user_states or user_states[chat_id].get('status') not in ['waiting_url', 'waiting_layout']:
        bot.reply_to(message, "⚠️ Silakan ketik /start dan pilih platform terlebih dahulu.")
        return

    url = message.text.strip().split()[0]
    platform = user_states[chat_id].get('platform')

    # VALIDASI KETAT YOUTUBE
    if platform == "youtube" and not any(domain in url.lower() for domain in ['youtube.com', 'youtu.be']):
        bot.reply_to(message, "❌ Link salah! Kirimkan link YouTube, atau ulangi /start untuk mengganti platform.")
        return
        
    # VALIDASI KETAT KICK M3U8
    if platform == "kick" and "master.m3u8" not in url.lower():
        bot.reply_to(message, "❌ Link salah! Anda berada di Mode Kick. Anda HARUS mengirimkan link berekstensi `master.m3u8`.")
        return

    user_states[chat_id]['url'] = url
    user_states[chat_id]['status'] = 'waiting_layout'

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🤖 AI Full Auto", callback_data="mode_auto"),
        InlineKeyboardButton("⬛ Pad 16:9 (Hitam)", callback_data="mode_pad"),
        InlineKeyboardButton("👤 Tengah (IRL)", callback_data="mode_irl"),
        InlineKeyboardButton("🎯 Facecam Kanan", callback_data="mode_br"),
        InlineKeyboardButton("🎯 Facecam Kiri", callback_data="mode_bl")
    )
    bot.reply_to(message, "⚙️ *Langkah 1: Pilih Tata Letak Layar*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mode_'))
def handle_mode_selection(call):
    chat_id = call.message.chat.id
    if chat_id not in user_states: return

    user_states[chat_id]['mode'] = call.data.replace('mode_', '')
    platform = user_states[chat_id].get('platform')
    
    markup = InlineKeyboardMarkup()
    if platform == "youtube":
        markup.add(InlineKeyboardButton("🚀 Proses Auto Viral", callback_data="run_auto"))
        msg_text = "⏱️ *Langkah 2: Pilih Durasi Waktu*\n\nKlik tombol *Proses Auto* untuk memotong momen teramai, *ATAU* ketik langsung durasi manual di chat ini (Contoh: `01:10:00-01:11:00`)."
    else:
        msg_text = "⏱️ *Langkah 2: Masukkan Durasi Manual*\n\nSilakan ketik langsung rentang waktu video di chat ini untuk dipotong (Contoh: `01:10:00-01:11:00`)."
    
    bot.edit_message_text(text=msg_text, chat_id=chat_id, message_id=call.message.message_id, 
                          reply_markup=markup if platform == "youtube" else None, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == 'run_auto')
def trigger_auto_run(call):
    chat_id = call.message.chat.id
    if chat_id not in user_states: return
        
    msg = bot.edit_message_text("[░░░░░░░░░░] 0% - Mengirim tugas ke Mesin Cloud...", 
                          chat_id=chat_id, message_id=call.message.message_id)
    dispatch_kaggle_task(chat_id, msg.message_id, manual_time="none")

@bot.message_handler(func=lambda message: "-" in message.text and message.chat.id in user_states and 'mode' in user_states[message.chat.id])
def handle_manual_time(message):
    chat_id = message.chat.id
    manual_time = message.text.strip()
    msg = bot.send_message(chat_id, "[░░░░░░░░░░] 0% - Mengirim tugas manual ke Mesin Cloud...")
    dispatch_kaggle_task(chat_id, msg.message_id, manual_time=manual_time)

def monitor_kaggle_task(chat_id, slug_id):
    fail_count = 0
    while fail_count < 15:
        time.sleep(20)
        try:
            res = subprocess.check_output(["kaggle", "kernels", "status", f"{KAGGLE_USERNAME}/{slug_id}"], text=True)
            if any(x in res.lower() for x in ["complete", "error", "cancel"]):
                if chat_id in user_states: del user_states[chat_id]
                
                # PENGHANCURAN OTOMATIS MENGGUNAKAN PYTHON API (BUKAN CLI)
                try:
                    api.kernel_delete(KAGGLE_USERNAME, slug_id)
                    print(f"✅ Kaggle Task {slug_id} berhasil dihancurkan dari server.")
                except Exception as e:
                    print(f"⚠️ Gagal menghapus task via API: {str(e)}")
                break
        except Exception:
            fail_count += 1
            if fail_count >= 15:
                if chat_id in user_states: del user_states[chat_id]
                try:
                    api.kernel_delete(KAGGLE_USERNAME, slug_id)
                except: pass
                break

def dispatch_kaggle_task(chat_id, msg_id, manual_time):
    state = user_states.get(chat_id, {})
    url = state.get('url', '')
    face_pos = state.get('mode', 'auto')
    
    user_states[chat_id]['status'] = 'processing'
    
    os.makedirs("kaggle_task", exist_ok=True)
    worker_vars = f'URL = "{url}"\nCHAT_ID = "{chat_id}"\nMSG_ID = "{msg_id}"\nBOT_TOKEN = "{TOKEN}"\nMANUAL_TIME = "{manual_time}"\nFACE_POS = "{face_pos}"\n'
    
    with open("kaggle_task/script.py", "w") as f: f.write(worker_vars + KAGGLE_WORKER_CODE)
    
    slug_id = f"worker-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    metadata = {
      "id": f"{KAGGLE_USERNAME}/{slug_id}", "title": slug_id, "code_file": "script.py",
      "language": "python", "kernel_type": "script", "is_private": "true",
      "enable_gpu": "true", "enable_internet": "true"
    }
    with open("kaggle_task/kernel-metadata.json", "w") as f: json.dump(metadata, f)

    try:
        subprocess.run(["kaggle", "kernels", "push", "-p", "kaggle_task"], check=True)
        Thread(target=monitor_kaggle_task, args=(chat_id, slug_id)).start()
    except Exception:
        bot.edit_message_text("❌ Gagal terhubung ke Cloud Engine.", chat_id=chat_id, message_id=msg_id)
        if chat_id in user_states: del user_states[chat_id]

# --- 4. WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Sistem Aktif"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))).start()
    bot.infinity_polling()
