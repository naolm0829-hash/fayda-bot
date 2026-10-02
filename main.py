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
AUTHORIZED_USERS = [8657043630, 7541697159, "8657043630", "7541697159"]
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
# RELIABLE FAYDA PDF TEXT PARSER
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
        # Extract full raw text using PyMuPDF first
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()

        lines = [l.strip() for l in full_text.splitlines() if l.strip()]

        # Alternative fallback via pdfplumber
        if len(lines) < 5:
            with pdfplumber.open(pdf_path) as pdf:
                plumber_text = pdf.pages[0].extract_text() or ""
                lines = [l.strip() for l in plumber_text.splitlines() if l.strip()]

        # Parse data dynamically
        for idx, line in enumerate(lines):
            # FAN (16 digit format or preceded by FAN)
            if "FAN" in line or "FCN" in line or "ፋን" in line:
                fan_match = re.search(r'\d{4}\s?\d{4}\s?\d{4}\s?\d{4}', line)
                if fan_match:
                    data["fan"] = fan_match.group(0)
                elif idx + 1 < len(lines):
                    data["fan"] = lines[idx+1]

            # FIN
            elif "FIN" in line:
                fin_match = re.search(r'[A-Z0-9]{8,12}', line)
                if fin_match:
                    data["fin"] = fin_match.group(0)
                elif idx + 1 < len(lines):
                    data["fin"] = lines[idx+1]

            # Date of birth
            elif "Date of Birth" in line or "የትውልድ ቀን" in line:
                dob_match = re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', line)
                if dob_match:
                    data["dob"] = dob_match.group(0)
                elif idx + 1 < len(lines):
                    data["dob"] = lines[idx+1]

            # Sex / Gender
            elif "Sex" in line or "ጾታ" in line:
                if "Male" in line or "ወንድ" in line or "M" in line.split():
                    data["sex"] = "ወንድ / Male"
                elif "Female" in line or "ሴት" in line or "F" in line.split():
                    data["sex"] = "ሴት / Female"
                elif idx + 1 < len(lines):
                    data["sex"] = lines[idx+1]

            # Phone Number
            elif "Phone" in line or "ስልክ" in line:
                phone_match = re.search(r'(\+?251|0)\d{8,9}', line)
                if phone_match:
                    data["phone"] = phone_match.group(0)
                elif idx + 1 < len(lines):
                    data["phone"] = lines[idx+1]

            # Address fields
            elif "Region" in line or "ክልል" in line:
                if idx + 1 < len(lines): data["region"] = lines[idx+1]
            elif "Subcity" in line or "ክፍለ ከተማ" in line:
                if idx + 1 < len(lines): data["subcity"] = lines[idx+1]
            elif "Woreda" in line or "ወረዳ" in line:
                if idx + 1 < len(lines): data["woreda"] = lines[idx+1]

        # Extract names if present
        for idx, line in enumerate(lines):
            if "Full Name" in line or "ሙሉ ስም" in line:
                if idx + 1 < len(lines): data["name_am"] = lines[idx+1]
                if idx + 2 < len(lines): data["name_en"] = lines[idx+2]

    except Exception as e:
        print("Parsing Exception:", e)

    # Image Extraction (Photo & QR)
    doc = fitz.open(pdf_path)
    page = doc[0]
    photo_path = os.path.join(work_dir, "photo.png")
    qr_path = os.path.join(work_dir, "qr.png")

    images = page.get_images(full=True)
    extracted_imgs = []

    for img_info in images:
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
# TEMPLATE BUILDER WITH EXACT PIXEL POSITIONS
# ============================================================

def build_custom_template_id(data, photo_path, qr_path, work_dir, bw_mode=False):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("template.jpg file missing from repository!")

    template = Image.open(TEMPLATE_PATH).convert("RGB")
    tw, th = template.size
    draw = ImageDraw.Draw(template)

    # Scaled fonts based on template resolution
    base_size = int(th * 0.032)
    font_large = ImageFont.truetype(FONT_PATH, int(base_size * 1.25))
    font_medium = ImageFont.truetype(FONT_PATH, base_size)
    font_small = ImageFont.truetype(FONT_PATH, int(base_size * 0.85))

    text_color = (10, 10, 10)

    # FRONT CARD OVERLAYS
    # Photo placement
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        pw, ph = int(tw * 0.165), int(th * 0.620)
        photo = photo.resize((pw, ph), Image.Resampling.LANCZOS)
        template.paste(photo, (int(tw * 0.022), int(th * 0.220)), photo if photo.mode == 'RGBA' else None)

    # Names (Amharic & English)
    if data["name_am"]:
        draw.text((int(tw * 0.205), int(th * 0.225)), data["name_am"], fill=text_color, font=font_large)
    if data["name_en"]:
        draw.text((int(tw * 0.205), int(th * 0.280)), data["name_en"], fill=text_color, font=font_medium)

    # Date of Birth
    if data["dob"]:
        draw.text((int(tw * 0.205), int(th * 0.380)), data["dob"], fill=text_color, font=font_medium)

    # Sex
    if data["sex"]:
        draw.text((int(tw * 0.205), int(th * 0.480)), data["sex"], fill=text_color, font=font_medium)

    # FAN Number
    if data["fan"]:
        draw.text((int(tw * 0.205), int(th * 0.620)), data["fan"], fill=text_color, font=font_large)


    # BACK CARD OVERLAYS
    # QR Code
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        qw = int(tw * 0.230)
        qr = qr.resize((qw, qw), Image.Resampling.LANCZOS)
        template.paste(qr, (int(tw * 0.745), int(th * 0.080)), qr if qr.mode == 'RGBA' else None)

    # Phone Number
    if data["phone"]:
        draw.text((int(tw * 0.540), int(th * 0.150)), data["phone"], fill=text_color, font=font_medium)

    # Region / Subcity / Woreda
    if data["region"]:
        draw.text((int(tw * 0.540), int(th * 0.270)), data["region"], fill=text_color, font=font_small)
    if data["subcity"]:
        draw.text((int(tw * 0.540), int(th * 0.370)), data["subcity"], fill=text_color, font=font_small)
    if data["woreda"]:
        draw.text((int(tw * 0.540), int(th * 0.470)), data["woreda"], fill=text_color, font=font_small)

    # FIN
    if data["fin"]:
        draw.text((int(tw * 0.540), int(th * 0.650)), data["fin"], fill=text_color, font=font_large)

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
            time.sleep(5)            time.sleep(5)
