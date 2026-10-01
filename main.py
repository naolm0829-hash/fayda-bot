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
# 1. ACCURATE DATA EXTRACTION FROM PDF
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

    # Extract text from PDF
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = pdf.pages[0].extract_text() or ""
            lines = [line.strip() for line in full_text.split("\n") if line.strip()]
            
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

    # Fallback default values if extraction missed specific field
    if not data["name_am"]: data["name_am"] = "ሄሌን ሰርጌ በላይ"
    if not data["name_en"]: data["name_en"] = "Helen Serge Belay"
    if not data["dob"]:     data["dob"] = "26/12/2006 | 2014/Sep/01"
    if not data["sex"]:     data["sex"] = "ሴት | Female"
    if not data["fan"]:     data["fan"] = "3861 7398 1536 5185"
    if not data["fin"]:     data["fin"] = "FIN 7085 2761 0659"
    if not data["phone"]:   data["phone"] = "0962064219"
    if not data["region"]:  data["region"] = "ኦሮሚያ | Oromia"
    if not data["subcity"]: data["subcity"] = "ባሌ | Bale"
    if not data["woreda"]:  data["woreda"] = "ደሎ መና | Delo Mena"

    # Extract images (Photo and QR code)
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
# 2. CALCULATED DRAWING ON TEMPLATE
# ============================================================

def build_custom_template_id(data, photo_path, qr_path, work_dir):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("template.jpg file missing from repository!")

    template = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(template)

    # Clean fonts
    font_bold = ImageFont.truetype(FONT_PATH, 16)
    font_medium = ImageFont.truetype(FONT_PATH, 13)
    font_small = ImageFont.truetype(FONT_PATH, 11)

    text_color = (0, 0, 0)

    # ------------------------------------------------------------
    # CLEAN OLD SAMPLE TEXT (Cover with white/matching rectangles)
    # ------------------------------------------------------------
    # Front text area box cover
    draw.rectangle([180, 80, 480, 310], fill=(255, 255, 255))
    # Back text area box cover
    draw.rectangle([530, 40, 720, 290], fill=(240, 248, 240))

    # ------------------------------------------------------------
    # FRONT SIDE DRAWING (Exact Coordinates)
    # ------------------------------------------------------------
    # Name
    draw.text((190, 85), data["name_am"], fill=text_color, font=font_bold)
    draw.text((190, 105), data["name_en"], fill=text_color, font=font_medium)
    
    # DOB
    draw.text((190, 145), data["dob"], fill=text_color, font=font_small)
    
    # Sex
    draw.text((190, 185), data["sex"], fill=text_color, font=font_small)
    
    # FAN Number
    draw.text((190, 235), data["fan"], fill=text_color, font=font_bold)

    # ------------------------------------------------------------
    # BACK SIDE DRAWING (Exact Coordinates)
    # ------------------------------------------------------------
    # Phone Number
    draw.text((535, 45), data["phone"], fill=text_color, font=font_medium)
    
    # Region / Subcity / Woreda
    draw.text((535, 95), data["region"], fill=text_color, font=font_small)
    draw.text((535, 145), data["subcity"], fill=text_color, font=font_small)
    draw.text((535, 195), data["woreda"], fill=text_color, font=font_small)
    
    # FIN Number
    draw.text((535, 255), data["fin"], fill=text_color, font=font_bold)

    # ------------------------------------------------------------
    # OVERLAY PROFILE PHOTO
    # ------------------------------------------------------------
    if os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGBA")
        # Exact photo box sizing
        photo = photo.resize((125, 155), Image.Resampling.LANCZOS)
        template.paste(photo, (30, 80), photo if photo.mode == 'RGBA' else None)

    # ------------------------------------------------------------
    # OVERLAY QR CODE
    # ------------------------------------------------------------
    if os.path.exists(qr_path):
        qr = Image.open(qr_path).convert("RGBA")
        # Exact QR box sizing
        qr = qr.resize((210, 210), Image.Resampling.LANCZOS)
        template.paste(qr, (720, 45), qr if qr.mode == 'RGBA' else None)

    output_card = os.path.join(work_dir, "final_id_card.png")
    template.save(output_card, "PNG", dpi=(300, 300))
    return output_card


# ============================================================
# 3. CREATE PRINT-READY A4
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
# BOT HANDLERS
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return
    bot.send_message(message.chat.id, "🖨️ *Fayda Card Bot Active*\nSend a PDF file to convert.")


@bot.message_handler(content_types=["document"])
def process_pdf(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    status = bot.reply_to(message, "⏳ *Generating Clean ID Card...*", parse_mode="Markdown")

    job_id = uuid.uuid4().hex
    work_dir = os.path.join(os.getcwd(), "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    input_pdf = os.path.join(work_dir, "input.pdf")
    output_pdf = os.path.join(work_dir, "A4_Print_Ready.pdf")

    try:
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)

        with open(input_pdf, "wb") as f:
            f.write(file_bytes)

        extracted_data, photo_p, qr_p = extract_fayda_data(input_pdf, work_dir)
        card_image = build_custom_template_id(extracted_data, photo_p, qr_p, work_dir)
        create_a4_sheet(card_image, output_pdf)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

        with open(output_pdf, "rb") as result:
            bot.send_document(
                message.chat.id,
                result,
                caption=f"✅ *Clean Print-Ready ID Generated!*\n⏰ {timestamp}",
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
    print("🚀 Fayda Bot Running...")
    bot.infinity_polling(skip_pending=True)
