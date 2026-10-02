import os
import shutil
import uuid
import datetime
import urllib.request

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = "8556582041:AAFw7Pz2ysPaL4gSSwe1Sb-mvmgPGPbH3O0"

# Authorized Users (supports both integer and string checks)
AUTHORIZED_USERS = [8657043630, 7541697159, "8657043630", "7541697159"]

# Your Archive Channel ID extracted from forwarded payload
ARCHIVE_CHANNEL_ID = -1003928857630

TEMPLATE_PATH = "template.jpg"
FONT_PATH = "AbyssinicaSIL-Regular.ttf"

# A4 dimensions @ 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508
TOP_MARGIN = 300

PENDING_JOBS = {}


# ============================================================
# AUTOMATIC FONT DOWNLOADER
# ============================================================

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
# 1. EXTRACT DATA & ASSETS FROM PDF
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
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            
            for i, line in enumerate(lines):
                if "Full Name" in line or "ሙሉ ስም" in line:
                    if i + 1 < len(lines): data["name_am"] = lines[i+1]
                    if i + 2 < len(lines): data["name_en"] = lines[i+2]
                elif "Date of Birth" in line or "የትውልድ ቀን" in line:
                    if i + 1 < len(lines): data["dob"] = lines[i+1]
                elif "Sex" in line or "ጾታ" in line:
                    if i + 1 < len(lines): data["sex"] = lines[i+1]
                elif "FAN" in line or "ፋን" in line:
                    if i + 1 < len(lines): data["fan"] = lines[i+1]
                elif "FIN" in line:
                    if i + 1 < len(lines): data["fin"] = lines[i+1]
                elif "Phone Number" in line or "ስልክ ቁጥር" in line:
                    if i + 1 < len(lines): data["phone"] = lines[i+1]
                elif "Region" in line or "ክልል" in line:
                    if i + 1 < len(lines): data["region"] = lines[i+1]
                elif "Subcity" in line or "ክፍለ ከተማ" in line:
                    if i + 1 < len(lines): data["subcity"] = lines[i+1]
                elif "Woreda" in line or "ወረዳ" in line:
                    if i + 1 < len(lines): data["woreda"] = lines[i+1]

    except Exception as e:
        print("Text parsing warning:", e)

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
# 2. DRAW ON BLANK TEMPLATE
# ============================================================

def build_custom_template_id(data, photo_path, qr_path, work_dir, bw_mode=False):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("template.jpg file missing from repository!")

    template = Image.open(TEMPLATE_PATH).convert("RGB")
    tw, th = template.size
    draw = ImageDraw.Draw(template)

    font_bold = ImageFont.truetype(FONT_PATH, int(th * 0.042))
    font_medium = ImageFont.truetype(FONT_PATH, int(th * 0.034))
    font_small = ImageFont.truetype(FONT_PATH, int(th * 0.028))

    text_color = (20, 20, 20)

    # FRONT SIDE TEXT
    if data["name_am"]:
        draw.text((int(tw * 0.192), int(th * 0.250)), data["name_am"], fill=text_color, font=font_bold)
    if data["name_en"]:
        draw.text((int(tw * 0.192), int(th * 0.300)), data["name_en"], fill=text_color, font=font_medium)
    if data["dob"]:
        draw.text((int(tw * 0.192), int(th * 0.430)), data["dob"], fill=text_color, font=font_small)
    if data["sex"]:
        draw.text((int(tw * 0.192), int(th * 0.540)), data["sex"], fill=text_color, font=font_small)
    if data["fan"]:
        draw.text((int(tw * 0.192), int(th * 0.690)), data["fan"], fill=text_color, font=font_bold)

    # BACK SIDE TEXT
    if data["phone"]:
        draw.text((int(tw * 0.540), int(th * 0.130)), data["phone"], fill=text_color, font=font_medium)
    if data["region"]:
        draw.text((int(tw * 0.540), int(th * 0.260)), data["region"], fill=text_color, font=font_small)
    if data["subcity"]:
        draw.text((int(tw * 0.540), int(th * 0.360)), data["subcity"], fill=text_color, font=font_small)
    if data["woreda"]:
        draw.text((int(tw * 0.540), int(th * 0.460)), data["woreda"], fill=text_color, font=font_small)
    if data["fin"]:
        draw.text((int(tw * 0.540), int(th * 0.710)), data["fin"], fill=text_color, font=font_bold)

    # PASTE PHOTO
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        pw, ph = int(tw * 0.160), int(th * 0.600)
        photo = photo.resize((pw, ph), Image.Resampling.LANCZOS)
        template.paste(photo, (int(tw * 0.020), int(th * 0.215)), photo if photo.mode == 'RGBA' else None)

    # PASTE QR CODE
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        qw = int(tw * 0.240)
        qr = qr.resize((qw, qw), Image.Resampling.LANCZOS)
        template.paste(qr, (int(tw * 0.735), int(th * 0.070)), qr if qr.mode == 'RGBA' else None)

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

        # 1. Send result to requesting user
        with open(output_pdf, "rb") as result:
            bot.send_document(
                chat_id,
                result,
                caption=f"✅ *{mode_label} Print-Ready ID Generated!*\n⏰ {timestamp}",
                parse_mode="Markdown"
            )

        # 2. Automatically archive document to private channel
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


if __name__ == "__main__":
    import time
    print("🚀 Cleaning previous Telegram sessions...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    
    time.sleep(1)
    print("🚀 Fayda Bot Active & Running with Channel Archiving...")
    bot.infinity_polling(skip_pending=True)
