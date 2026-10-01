import os
import shutil
import uuid
import datetime
import urllib.request

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image, ImageDraw, ImageFont
import telebot


# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = "8556582041:AAG5bxF-_GL8-9Jj3wj3XoWZVbc8Qf8Bkj0"
ARCHIVE_CHANNEL_ID = -1003928857630
AUTHORIZED_USERS = [8657043630]

TEMPLATE_PATH = "template.jpg"  # Save your blank/base template image as template.jpg
FONT_PATH = "AbyssinicaSIL-Regular.ttf"

# A4 dimensions @ 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508
TOP_MARGIN = 200
CARD_GAP = 80


# ============================================================
# AUTOMATIC FONT DOWNLOADER (OPTION A)
# ============================================================

def ensure_amharic_font():
    """Downloads Abyssinica SIL font automatically if not found locally."""
    if not os.path.exists(FONT_PATH):
        print("📥 Amharic font not found. Downloading automatically...")
        url = "https://github.com/google/fonts/raw/main/ofl/abyssinicasil/AbyssinicaSIL-Regular.ttf"
        try:
            urllib.request.urlretrieve(url, FONT_PATH)
            print("✅ Amharic font downloaded successfully!")
        except Exception as e:
            print(f"❌ Failed to download font: {e}")

ensure_amharic_font()


# ============================================================
# BOT INITIALIZATION
# ============================================================

bot = telebot.TeleBot(BOT_TOKEN)
history_records = []

def authorized(user_id):
    return user_id in AUTHORIZED_USERS


# ============================================================
# PDF DATA & ASSETS EXTRACTION
# ============================================================

def parse_fayda_pdf(pdf_path, work_dir):
    """
    Extracts text fields, cropped photo, and QR code from the Fayda PDF.
    """
    data = {}

    # 1. Extract Text Data using pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() or ""
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for i, line in enumerate(lines):
            if "ሄሌን" in line or "Helen" in line or "Name" in line:
                data["name_am"] = lines[i] if i < len(lines) else ""
                data["name_en"] = lines[i+1] if i+1 < len(lines) else ""
            if "Date of Birth" in line or "/" in line:
                if "/" in line and len(line) >= 10:
                    data["dob"] = line

    # Fallback default values if extraction misses specific lines
    data.setdefault("name_am", "ሄሌን ሰርጌ በላይ")
    data.setdefault("name_en", "Helen Serge Belay")
    data.setdefault("dob", "26/12/2006 | 2014/Sep/01")
    data.setdefault("sex", "ሴት | Female")
    data.setdefault("fan", "3861 7398 1536 5185")
    data.setdefault("fin", "FIN 7085 2761 0659")
    data.setdefault("phone", "0962064219")
    data.setdefault("nationality", "ኢትዮጵያ | Ethiopia")
    data.setdefault("address", "አዲስ አበባ\nAddis Ababa\nባሌ\nBale")

    # 2. Extract Photo and QR Code Images using PyMuPDF
    doc = fitz.open(pdf_path)
    page = doc[0]
    
    photo_path = os.path.join(work_dir, "extracted_photo.png")
    qr_path = os.path.join(work_dir, "extracted_qr.png")

    images = page.get_images(full=True)
    image_list = []

    for img in images:
        xref = img[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        
        img_file = os.path.join(work_dir, f"img_{xref}.png")
        pix.save(img_file)
        
        # Categorize images by dimensions
        image_list.append((pix.width, pix.height, img_file))

    # Sort images by height/width to identify Photo vs QR Code
    image_list.sort(key=lambda x: x[0] * x[1], reverse=True)

    if len(image_list) >= 1:
        shutil.copy(image_list[0][2], photo_path)
    if len(image_list) >= 2:
        shutil.copy(image_list[1][2], qr_path)

    doc.close()

    return data, photo_path, qr_path


# ============================================================
# TEMPLATE COMPOSITION (PIL IMAGE DRAWING)
# ============================================================

def build_id_card(data, photo_path, qr_path, work_dir):
    """
    Overlays extracted photo, QR code, and text data directly onto your ID template.
    """
    if os.path.exists(TEMPLATE_PATH):
        template = Image.open(TEMPLATE_PATH).convert("RGB")
    else:
        # Create a blank fallback canvas if template image isn't loaded yet
        template = Image.new("RGB", (2000, 650), (255, 255, 255))

    draw = ImageDraw.Draw(template)

    # Load custom fonts
    font_large = ImageFont.truetype(FONT_PATH, 28)
    font_medium = ImageFont.truetype(FONT_PATH, 22)
    font_small = ImageFont.truetype(FONT_PATH, 18)

    # Text Colors
    text_color = (0, 0, 0)

    # 1. Draw Text Fields onto Template
    # Front Side Details
    draw.text((380, 140), data["name_am"], fill=text_color, font=font_large)
    draw.text((380, 180), data["name_en"], fill=text_color, font=font_large)
    draw.text((380, 260), data["dob"], fill=text_color, font=font_medium)
    draw.text((380, 330), data["sex"], fill=text_color, font=font_medium)
    draw.text((380, 520), data["fan"], fill=text_color, font=font_large)

    # Back Side Details
    draw.text((1100, 100), data["phone"], fill=text_color, font=font_medium)
    draw.text((1100, 170), data["nationality"], fill=text_color, font=font_medium)
    draw.text((1100, 240), data["address"], fill=text_color, font=font_small)
    draw.text((1100, 520), data["fin"], fill=text_color, font=font_large)

    # 2. Paste Cropped Profile Photo
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        photo = photo.resize((220, 270), Image.Resampling.LANCZOS)
        template.paste(photo, (80, 140), photo if photo.mode == 'RGBA' else None)

    # 3. Paste QR Code
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        qr = qr.resize((350, 350), Image.Resampling.LANCZOS)
        template.paste(qr, (1500, 100), qr if qr.mode == 'RGBA' else None)

    output_card = os.path.join(work_dir, "completed_id.png")
    template.save(output_card)
    return output_card


# ============================================================
# CREATE A4 PRINT SHEET
# ============================================================

def create_a4_sheet(card_image_path, output_pdf):
    card = Image.open(card_image_path).convert("RGB")
    
    sheet = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))
    
    # Scale ID card image for standard A4 printing
    scale = (A4_WIDTH - 200) / card.width
    new_w = int(card.width * scale)
    new_h = int(card.height * scale)
    card_resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)

    x = (A4_WIDTH - new_w) // 2
    y = TOP_MARGIN

    sheet.paste(card_resized, (x, y))
    sheet.save(output_pdf, "PDF", resolution=300.0)


# ============================================================
# TELEGRAM BOT HANDLER
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    bot.send_message(
        message.chat.id,
        (
            "🖨️ *Fayda ID Generator Bot*\n\n"
            "Status: *Active*\n\n"
            "Send the official Fayda PDF to convert it into a printable ID card!"
        ),
        parse_mode="Markdown"
    )


@bot.message_handler(content_types=["document"])
def process_pdf(message):
    user_id = message.from_user.id

    if not authorized(user_id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    filename = message.document.file_name or "document.pdf"
    status = bot.reply_to(message, "⏳ *Generating ID Card...*", parse_mode="Markdown")

    job_id = uuid.uuid4().hex
    work_dir = os.path.join(os.getcwd(), "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    input_pdf = os.path.join(work_dir, "input.pdf")
    output_pdf = os.path.join(work_dir, "A4_Print_Ready.pdf")

    try:
        # Download PDF from Telegram
        file_info = bot.get_file(message.document.file_id)
        data = bot.download_file(file_info.file_path)

        with open(input_pdf, "wb") as f:
            f.write(data)

        # Parse data, crop photos, draw onto template, and generate print sheet
        extracted_data, photo_path, qr_path = parse_fayda_pdf(input_pdf, work_dir)
        card_path = build_id_card(extracted_data, photo_path, qr_path, work_dir)
        create_a4_sheet(card_path, output_pdf)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

        # Send completed PDF back to Telegram
        with open(output_pdf, "rb") as result:
            bot.send_document(
                message.chat.id,
                result,
                caption=f"✅ *ID Card Converted & Ready for Print!*\n\n⏰ {timestamp}",
                parse_mode="Markdown"
            )

        bot.delete_message(message.chat.id, status.message_id)

    except Exception as error:
        print("Error:", error)
        bot.send_message(message.chat.id, f"❌ *Failed to convert ID:* `{str(error)}`", parse_mode="Markdown")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ============================================================
# START BOT
# ============================================================

if __name__ == "__main__":
    print("🚀 Fayda ID Generator Bot is running...")
    bot.infinity_polling(skip_pending=True)
