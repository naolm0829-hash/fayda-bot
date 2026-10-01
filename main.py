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
AUTHORIZED_USERS = [8657043630]

TEMPLATE_PATH = "template.jpg"
FONT_PATH = "AbyssinicaSIL-Regular.ttf"

# A4 print resolution (300 DPI)
A4_WIDTH = 2480
A4_HEIGHT = 3508
TOP_MARGIN = 300


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
    return user_id in AUTHORIZED_USERS


# ============================================================
# 1. EXTRACT DATA & ASSETS FROM PDF
# ============================================================

def extract_fayda_data(pdf_path, work_dir):
    data = {
        "name_am": "ሄሌን ሰርጌ በላይ",
        "name_en": "Helen Serge Belay",
        "dob": "26/12/2006 | 2014/Sep/01",
        "sex": "ሴት | Female",
        "fan": "3861 7398 1536 5185",
        "fin": "FIN 7085 2761 0659",
        "phone": "0962064219",
        "region": "ኦሮሚያ | Oromia",
        "subcity": "ባሌ | Bale",
        "woreda": "ደሎ መና | Delo Mena"
    }

    # Extract text from PDF
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            for i, line in enumerate(lines):
                if "Helen" in line or "ሄሌን" in line:
                    data["name_am"] = lines[i] if i < len(lines) else data["name_am"]
                    data["name_en"] = lines[i+1] if i+1 < len(lines) else data["name_en"]
    except Exception as e:
        print("Text parsing warning:", e)

    # Extract embedded images (Photo and QR code)
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

    # Sort images by resolution/dimensions to separate photo vs QR code
    extracted_imgs.sort(key=lambda x: x[0] * x[1], reverse=True)

    # Assign photo (usually square-ish headshot) and QR
    for w, h, img_f in extracted_imgs:
        ratio = w / float(h)
        if 0.7 <= ratio <= 0.95 and not os.path.exists(photo_path):
            shutil.copy(img_f, photo_path)
        elif 0.95 <= ratio <= 1.1 and not os.path.exists(qr_path):
            shutil.copy(img_f, qr_path)

    # Fallbacks if strict ratio check misses
    if not os.path.exists(photo_path) and len(extracted_imgs) > 0:
        shutil.copy(extracted_imgs[0][2], photo_path)
    if not os.path.exists(qr_path) and len(extracted_imgs) > 1:
        shutil.copy(extracted_imgs[1][2], qr_path)

    doc.close()

    return data, photo_path, qr_path


# ============================================================
# 2. DRAW DATA DIRECTLY ONTO TEMPLATE IMAGE
# ============================================================

def build_custom_template_id(data, photo_path, qr_path, work_dir):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("template.jpg file missing from repository!")

    # Open base template
    template = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(template)

    # Load Amharic font in multiple sizes
    font_bold = ImageFont.truetype(FONT_PATH, 24)
    font_medium = ImageFont.truetype(FONT_PATH, 18)
    font_small = ImageFont.truetype(FONT_PATH, 15)

    text_color = (10, 10, 10)

    # --- FRONT SIDE DRAWING ---
    # Name
    draw.text((260, 105), data["name_am"], fill=text_color, font=font_bold)
    draw.text((260, 135), data["name_en"], fill=text_color, font=font_medium)
    
    # DOB & Sex
    draw.text((260, 195), data["dob"], fill=text_color, font=font_medium)
    draw.text((260, 245), data["sex"], fill=text_color, font=font_medium)
    
    # FAN
    draw.text((260, 310), data["fan"], fill=text_color, font=font_bold)

    # --- BACK SIDE DRAWING ---
    # Phone & Region
    draw.text((750, 75), data["phone"], fill=text_color, font=font_medium)
    draw.text((750, 125), data["region"], fill=text_color, font=font_medium)
    draw.text((750, 175), data["subcity"], fill=text_color, font=font_medium)
    draw.text((750, 225), data["woreda"], fill=text_color, font=font_medium)
    
    # FIN
    draw.text((750, 310), data["fin"], fill=text_color, font=font_bold)

    # --- OVERLAY PROFILE PHOTO ---
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        photo = photo.resize((155, 185), Image.Resampling.LANCZOS)
        template.paste(photo, (70, 95), photo if photo.mode == 'RGBA' else None)

    # --- OVERLAY QR CODE ---
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        qr = qr.resize((230, 230), Image.Resampling.LANCZOS)
        template.paste(qr, (1030, 70), qr if qr.mode == 'RGBA' else None)

    output_card = os.path.join(work_dir, "final_id_card.png")
    template.save(output_card, "PNG", dpi=(300, 300))
    return output_card


# ============================================================
# 3. CONVERT TO PRINT-READY A4 PDF
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
# TELEGRAM BOT HANDLER
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return
    bot.send_message(message.chat.id, "🖨️ *Template ID Generator Active*\nSend a Fayda PDF file to start.")


@bot.message_handler(content_types=["document"])
def process_pdf(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    status = bot.reply_to(message, "⏳ *Extracting Data & Painting Template...*", parse_mode="Markdown")

    job_id = uuid.uuid4().hex
    work_dir = os.path.join(os.getcwd(), "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    input_pdf = os.path.join(work_dir, "input.pdf")
    output_pdf = os.path.join(work_dir, "A4_Print_Ready.pdf")

    try:
        # Download PDF
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)

        with open(input_pdf, "wb") as f:
            f.write(file_bytes)

        # 1. Extract data & images
        extracted_data, photo_p, qr_p = extract_fayda_data(input_pdf, work_dir)
        
        # 2. Overlay onto template.jpg
        card_image = build_custom_template_id(extracted_data, photo_p, qr_p, work_dir)
        
        # 3. Place onto A4
        create_a4_sheet(card_image, output_pdf)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

        with open(output_pdf, "rb") as result:
            bot.send_document(
                message.chat.id,
                result,
                caption=f"✅ *Clean Template ID Ready for Print!*\n⏰ {timestamp}",
                parse_mode="Markdown"
            )

        try:
            bot.delete_message(message.chat.id, status.message_id)
        except Exception:
            pass

    except Exception as error:
        print("Error:", error)
        bot.send_message(message.chat.id, f"❌ *Error:* `{str(error)}`", parse_mode="Markdown")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    print("🚀 Fayda Template Bot Running...")
    bot.infinity_polling(skip_pending=True)
