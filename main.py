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

TEMPLATE_PATH = "template.jpg"
FONT_PATH = "AbyssinicaSIL-Regular.ttf"

# A4 dimensions @ 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508
TOP_MARGIN = 200


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
history_records = []

def authorized(user_id):
    return user_id in AUTHORIZED_USERS


# ============================================================
# EXTRACTION & CLEAN RENDERING
# ============================================================

def process_fayda(pdf_path, work_dir):
    """
    Renders high-res cards from PDF and overlays dynamic elements cleanly.
    """
    doc = fitz.open(pdf_path)
    page = doc[0]

    # Render PDF page at 300 DPI
    zoom = 300 / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    rendered_path = os.path.join(work_dir, "rendered.png")
    pix.save(rendered_path)
    doc.close()

    full_img = Image.open(rendered_path)
    w, h = full_img.size

    # Crop Front and Back cards directly from Fayda layout
    front_box = (int(w * 0.535), int(h * 0.08), int(w * 0.985), int(h * 0.485))
    back_box  = (int(w * 0.535), int(h * 0.505), int(w * 0.985), int(h * 0.91))

    front_img = full_img.crop(front_box)
    back_img  = full_img.crop(back_box)

    # Clean combined side-by-side card canvas
    card_w, card_h = front_img.size
    gap = 40
    combined = Image.new("RGB", (card_w * 2 + gap, card_h), (255, 255, 255))
    combined.paste(front_img, (0, 0))
    combined.paste(back_img, (card_w + gap, 0))

    output_card = os.path.join(work_dir, "id_combined.png")
    combined.save(output_card, "PNG", dpi=(300, 300))
    
    full_img.close()
    return output_card


# ============================================================
# CREATE A4 SHEET
# ============================================================

def create_a4_sheet(card_image_path, output_pdf):
    card = Image.open(card_image_path).convert("RGB")
    sheet = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))

    scale = (A4_WIDTH - 160) / card.width
    new_w = int(card.width * scale)
    new_h = int(card.height * scale)
    card_resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)

    x = (A4_WIDTH - new_w) // 2
    y = TOP_MARGIN

    sheet.paste(card_resized, (x, y))
    sheet.save(output_pdf, "PDF", resolution=300.0)
    card.close()


# ============================================================
# BOT HANDLER
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return
    bot.send_message(message.chat.id, "🖨️ *Fayda ID Converter Active*\nSend a PDF file to process.")


@bot.message_handler(content_types=["document"])
def process_pdf(message):
    if not authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Access restricted.")
        return

    filename = message.document.file_name or "document.pdf"
    status = bot.reply_to(message, "⏳ *Converting ID Card...*", parse_mode="Markdown")

    job_id = uuid.uuid4().hex
    work_dir = os.path.join(os.getcwd(), "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    input_pdf = os.path.join(work_dir, "input.pdf")
    output_pdf = os.path.join(work_dir, "A4_Print_Ready.pdf")

    try:
        file_info = bot.get_file(message.document.file_id)
        data = bot.download_file(file_info.file_path)

        with open(input_pdf, "wb") as f:
            f.write(data)

        card_path = process_fayda(input_pdf, work_dir)
        create_a4_sheet(card_path, output_pdf)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

        with open(output_pdf, "rb") as result:
            bot.send_document(
                message.chat.id,
                result,
                caption=f"✅ *Print Ready ID Card Generated!*\n⏰ {timestamp}",
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
    print("🚀 Fayda ID Bot Running...")
    bot.infinity_polling(skip_pending=True)
