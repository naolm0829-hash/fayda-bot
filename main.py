import os
import shutil
import uuid
import datetime
import urllib.request
import time
import re

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = "8556582041:AAFw7Pz2ysPaL4gSSwe1Sb-mvmgPGPbH3O0"
AUTHORIZED_USERS = [8657043630, 7541697159, 7274301492, "8657043630", "7541697159", "7274301492" ]
ARCHIVE_CHANNEL_ID = -1003928857630

TEMPLATE_PATH = "template.jpg"
FONT_PATH = "AbyssinicaSIL-Regular.ttf"

# A4 dimensions @ 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508
TOP_MARGIN = 300

PENDING_JOBS = {}


# ============================================================
# PYTHONANYWHERE PROXY SETUP
# ============================================================

apihelper.proxy = {
    'http': 'http://proxy.server:3128',
    'https': 'http://proxy.server:3128'
}


def ensure_amharic_font():
    if not os.path.exists(FONT_PATH):
        print("📥 Downloading Amharic font...")
        url = "https://github.com/google/fonts/raw/main/ofl/abyssinicasil/AbyssinicaSIL-Regular.ttf"
        try:
            urllib.request.urlretrieve(url, FONT_PATH)
            print("✅ Amharic font downloaded!")
        except Exception as e:
            print(f"❌ Font download failed: {e}")

ensure_amharic_font()

bot = telebot.TeleBot(BOT_TOKEN)

def authorized(user_id):
    return user_id in AUTHORIZED_USERS or str(user_id) in AUTHORIZED_USERS


# ============================================================
# PARSE FAYDA PDF VALUES STRICTLY
# ============================================================

def extract_fayda_data(pdf_path, work_dir):
    data = {
        "name_am": "",
        "name_en": "",
        "dob": "",
        "sex": "",
        "fan": "",
        "fin": "",
        "phone": "",
        "region": "",
        "subcity": "",
        "woreda": ""
    }

    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        text = page.get_text("text")
        doc.close()

        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            # Extract Name (skip static header text)
            if ("FULL NAME" in line.upper() or "ሙሉ ስም" in line) and i + 2 < len(lines):
                data["name_am"] = lines[i+1]
                data["name_en"] = lines[i+2]

            # DOB
            elif "DATE OF BIRTH" in line.upper() or "የትውልድ ቀን" in line:
                match = re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', text)
                if match:
                    data["dob"] = match.group(0)

            # SEX
            elif "SEX" in line.upper() and "ESEX" not in line.upper():
                if i + 1 < len(lines):
                    val = lines[i+1]
                    if val.upper() in ["M", "MALE", "ወንድ"]:
                        data["sex"] = "M / ወንድ"
                    elif val.upper() in ["F", "FEMALE", "ሴት"]:
                        data["sex"] = "F / ሴት"

            # FAN / FCN (16 digits)
            elif "FAN" in line.upper() or "FCN" in line.upper() or "ፋን" in line:
                fan_match = re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b', text)
                if fan_match:
                    data["fan"] = fan_match.group(0)

            # FIN
            elif "FIN" in line.upper():
                fin_match = re.search(r'\b[A-Z0-9]{8,12}\b', line)
                if fin_match:
                    data["fin"] = fin_match.group(0)

            # PHONE
            elif "PHONE" in line.upper() or "ስልክ" in line:
                ph = re.search(r'(\+?251|0)9\d{8}', text)
                if ph:
                    data["phone"] = ph.group(0)

            # REGION / SUBCITY / WOREDA
            elif "REGION" in line.upper() or "ክልል" in line:
                if i + 1 < len(lines) and len(lines[i+1]) < 30:
                    data["region"] = lines[i+1]
            elif "SUBCITY" in line.upper() or "ክፍለ ከተማ" in line:
                if i + 1 < len(lines) and len(lines[i+1]) < 30:
                    data["subcity"] = lines[i+1]
            elif "WOREDA" in line.upper() or "ወረዳ" in line:
                if i + 1 < len(lines) and len(lines[i+1]) < 30:
                    data["woreda"] = lines[i+1]

    except Exception as e:
        print("Parsing Exception:", e)

    # Extract Photos
    doc = fitz.open(pdf_path)
    page = doc[0]
    photo_path = os.path.join(work_dir, "photo.png")
    qr_path = os.path.join(work_dir, "qr.png")

    extracted_imgs = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        save_file = os.path.join(work_dir, f"img_{xref}.png")
        pix.save(save_file)
        extracted_imgs.append((pix.width, pix.height, save_file))

    extracted_imgs.sort(key=lambda x: x[0] * x[1], reverse=True)

    for w, h, img_f in extracted_imgs:
        ratio = w / float(h)
        if 0.7 <= ratio <= 0.95 and not os.path.exists(photo_path):
            shutil.copy(img_f, photo_path)
        elif 0.95 <= ratio <= 1.15 and not os.path.exists(qr_path):
            shutil.copy(img_f, qr_path)

    if not os.path.exists(photo_path) and len(extracted_imgs) > 0:
        shutil.copy(extracted_imgs[0][2], photo_path)
    if not os.path.exists(qr_path) and len(extracted_imgs) > 1:
        shutil.copy(extracted_imgs[1][2], qr_path)

    doc.close()
    return data, photo_path, qr_path


# ============================================================
# TEMPLATE BUILDER WITH CLEAN COORDINATES
# ============================================================

def build_custom_template_id(data, photo_path, qr_path, work_dir, bw_mode=False):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("template.jpg file missing!")

    template = Image.open(TEMPLATE_PATH).convert("RGB")
    tw, th = template.size
    draw = ImageDraw.Draw(template)

    # Dynamic font sizing relative to exact height
    f_large = ImageFont.truetype(FONT_PATH, int(th * 0.038))
    f_med   = ImageFont.truetype(FONT_PATH, int(th * 0.030))
    f_small = ImageFont.truetype(FONT_PATH, int(th * 0.025))

    color = (0, 0, 0)

    # FRONT CARD OVERLAYS
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        pw, ph = int(tw * 0.150), int(th * 0.580)
        photo = photo.resize((pw, ph), Image.Resampling.LANCZOS)
        template.paste(photo, (int(tw * 0.025), int(th * 0.220)), photo if photo.mode == 'RGBA' else None)

    # Names
    if data["name_am"]:
        draw.text((int(tw * 0.190), int(th * 0.230)), data["name_am"], fill=color, font=f_large)
    if data["name_en"]:
        draw.text((int(tw * 0.190), int(th * 0.285)), data["name_en"], fill=color, font=f_med)

    # Sex & DOB
    if data["sex"]:
        draw.text((int(tw * 0.190), int(th * 0.440)), data["sex"], fill=color, font=f_med)
    if data["dob"]:
        draw.text((int(tw * 0.330), int(th * 0.440)), data["dob"], fill=color, font=f_med)

    # FAN
    if data["fan"]:
        draw.text((int(tw * 0.190), int(th * 0.650)), data["fan"], fill=color, font=f_large)

    # BACK CARD OVERLAYS
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        qw = int(tw * 0.220)
        qr = qr.resize((qw, qw), Image.Resampling.LANCZOS)
        template.paste(qr, (int(tw * 0.750), int(th * 0.100)), qr if qr.mode == 'RGBA' else None)

    # Region / Subcity / Woreda
    if data["region"]:
        draw.text((int(tw * 0.530), int(th * 0.130)), data["region"], fill=color, font=f_small)
    if data["subcity"]:
        draw.text((int(tw * 0.530), int(th * 0.240)), data["subcity"], fill=color, font=f_small)
    if data["woreda"]:
        draw.text((int(tw * 0.530), int(th * 0.350)), data["woreda"], fill=color, font=f_small)

    # Phone
    if data["phone"]:
        draw.text((int(tw * 0.530), int(th * 0.480)), data["phone"], fill=color, font=f_med)

    # FIN
    if data["fin"]:
        draw.text((int(tw * 0.530), int(th * 0.680)), data["fin"], fill=color, font=f_large)

    if bw_mode:
        template = template.convert("L").convert("RGB")

    output_card = os.path.join(work_dir, "final_id_card.png")
    template.save(output_card, "PNG", dpi=(300, 300))
    return output_card


# ============================================================
# 3. PRINT-READY A4 CANVAS
# ============================================================

def create_a4_sheet(card_image_path, output_pdf):
    card = Image.open(card_image_path).convert("RGB")
    sheet = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))

    scale = (A4_WIDTH - 200) / float(card.width)
    new_w = int(card.width * scale)
    new_h = int(card.height * scale)
    
    card_resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)

    x = (A4_WIDTH - new_w) // 2
    y = TOP_MARGIN

    sheet.paste(card_resized, (x, y))
    sheet.save(output_pdf, "PDF", resolution=300.0)
    card.close()


# ============================================================
# BOT HANDLERS & CALLBACKS
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return
    bot.send_message(message.chat.id, "🖨 *Fayda Card Bot Active*\nSend a PDF file to process.")


@bot.message_handler(content_types=["document"])
def handle_pdf_upload(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    job_id = uuid.uuid4().hex
    work_dir = os.path.join(os.getcwd(), "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    input_pdf = os.path.join(work_dir, "input.pdf")

    try:
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)

        with open(input_pdf, "wb") as f:
            f.write(file_bytes)

        PENDING_JOBS[job_id] = {
            "work_dir": work_dir,
            "input_pdf": input_pdf,
            "chat_id": message.chat.id,
            "user_info": message.from_user,
            "original_filename": message.document.file_name or "ID_Document.pdf"
        }

        markup = InlineKeyboardMarkup()
        btn_color = InlineKeyboardButton("🎨 Colored", callback_data=f"mode_color:{job_id}")
        btn_bw = InlineKeyboardButton("🔳 Black & White", callback_data=f"mode_bw:{job_id}")
        markup.add(btn_color, btn_bw)

        bot.reply_to(
            message,
            "📄 *PDF Received!*\nPlease select your preferred print mode:",
            reply_markup=markup,
            parse_mode="Markdown"
        )

    except Exception as error:
        print("Error saving document:", error)
        bot.reply_to(message, f"❌ *Error uploading PDF:* `{str(error)}`", parse_mode="Markdown")
        shutil.rmtree(work_dir, ignore_errors=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def process_print_choice(call):
    mode, job_id = call.data.split(":")
    is_bw = (mode == "mode_bw")

    if job_id not in PENDING_JOBS:
        bot.answer_callback_query(call.id, "Session expired. Please re-upload your PDF.")
        return

    job = PENDING_JOBS.pop(job_id)
    work_dir = job["work_dir"]
    input_pdf = job["input_pdf"]
    chat_id = job["chat_id"]
    user = job["user_info"]
    orig_filename = job["original_filename"]

    bot.edit_message_text(
        "⏳ *Generating Print-Ready ID Card...*",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode="Markdown"
    )

    output_pdf = os.path.join(work_dir, "A4_Print_Ready.pdf")

    try:
        extracted_data, photo_p, qr_p = extract_fayda_data(input_pdf, work_dir)
        card_image = build_custom_template_id(extracted_data, photo_p, qr_p, work_dir, bw_mode=is_bw)
        create_a4_sheet(card_image, output_pdf)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        mode_label = "Black & White" if is_bw else "Colored"

        with open(output_pdf, "rb") as result:
            bot.send_document(
                chat_id,
                result,
                caption=f"✅ *{mode_label} Print-Ready ID Generated!*\n⏰ {timestamp}",
                parse_mode="Markdown"
            )

        if ARCHIVE_CHANNEL_ID:
            try:
                user_display = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}".strip()
                archive_caption = (
                    f"🗄️ *ARCHIVE RECORD*\n\n"
                    f"👤 *Operator:* {user_display}\n"
                    f"🆔 *Telegram ID:* `{user.id}`\n"
                    f"📄 *File:* `{orig_filename}`\n"
                    f"🎨 *Mode:* {mode_label}\n"
                    f"📅 *Date:* {timestamp}"
                )
                with open(output_pdf, "rb") as archive_doc:
                    bot.send_document(
                        ARCHIVE_CHANNEL_ID,
                        archive_doc,
                        caption=archive_caption,
                        parse_mode="Markdown"
                    )
            except Exception as archive_err:
                print("❌ Failed to forward to Archive Channel:", archive_err)

        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass

    except Exception as error:
        print("Processing error:", error)
        bot.send_message(chat_id, f"❌ *Error:* `{str(error)}`", parse_mode="Markdown")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ============================================================
# MAIN EXECUTION LOOP WITH AUTO-RECONNECT
# ============================================================

if __name__ == "__main__":
    print("🚀 Cleaning previous Telegram sessions...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    
    time.sleep(1)
    print("🚀 Fayda Bot Active & Running through PythonAnywhere Proxy...")

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Proxy connection drop/error: {e}. Re-establishing connection in 5 seconds...")
            time.sleep(5)
