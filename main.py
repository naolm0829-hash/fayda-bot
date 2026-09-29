import os
import shutil
import uuid
import datetime

import fitz  # PyMuPDF
from PIL import Image
import telebot


# ============================================================
# CONFIGURATION
# ============================================================

# Paste your existing Telegram bot token here locally.
BOT_TOKEN = "8556582041:AAG5bxF-_GL8-9Jj3wj3XoWZVbc8Qf8Bkj0"

ARCHIVE_CHANNEL_ID = -1003928857630

AUTHORIZED_USERS = [
    8657043630
]

# A4 @ 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508

# Layout
TOP_MARGIN = 100
CARD_GAP = 100
TARGET_HEIGHT = 1100


# ============================================================
# BOT
# ============================================================

bot = telebot.TeleBot(BOT_TOKEN)

history_records = []


# ============================================================
# AUTHORIZATION
# ============================================================

def authorized(user_id):
    return user_id in AUTHORIZED_USERS


# ============================================================
# EXTRACT ORIGINAL EMBEDDED IMAGES
# ============================================================

def extract_original_images(pdf_path, work_dir):

    doc = fitz.open(pdf_path)

    if len(doc) == 0:
        doc.close()
        raise ValueError("PDF contains no pages.")

    page = doc[0]

    candidates = []

    for image in page.get_images(full=True):

        xref = image[0]
        width = image[2]
        height = image[3]

        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue

        if not rects:
            continue

        rect = rects[0]

        # Find the large embedded images on the
        # right side of the original Fayda PDF.
        if (
            width >= 1000
            and height >= 1500
            and rect.x0 >= page.rect.width * 0.55
        ):
            candidates.append({
                "xref": xref,
                "width": width,
                "height": height,
                "rect": rect
            })

    candidates.sort(
        key=lambda item: item["rect"].y0
    )

    if len(candidates) < 2:
        doc.close()
        raise ValueError(
            f"Could not find two large original images. "
            f"Found {len(candidates)}."
        )

    front_info = candidates[0]
    back_info = candidates[1]

    front_path = os.path.join(
        work_dir,
        "original_front.png"
    )

    back_path = os.path.join(
        work_dir,
        "original_back.png"
    )

    front_pixmap = fitz.Pixmap(
        doc,
        front_info["xref"]
    )

    back_pixmap = fitz.Pixmap(
        doc,
        back_info["xref"]
    )

    # Convert non-RGB images to RGB when necessary.
    if front_pixmap.colorspace is not None:
        if front_pixmap.colorspace.n != 3:
            front_pixmap = fitz.Pixmap(
                fitz.csRGB,
                front_pixmap
            )

    if back_pixmap.colorspace is not None:
        if back_pixmap.colorspace.n != 3:
            back_pixmap = fitz.Pixmap(
                fitz.csRGB,
                back_pixmap
            )

    front_pixmap.save(front_path)
    back_pixmap.save(back_path)

    front_pixmap = None
    back_pixmap = None

    doc.close()

    return front_path, back_path


# ============================================================
# RESIZE WITHOUT DISTORTION
# ============================================================

def resize_keep_ratio(image, target_height):

    width, height = image.size

    scale = target_height / height

    new_width = round(width * scale)

    return image.resize(
        (new_width, target_height),
        Image.Resampling.LANCZOS
    )


# ============================================================
# CREATE A4 PRINT SHEET
# ============================================================

def create_a4_sheet(
    front_path,
    back_path,
    output_pdf
):

    front = Image.open(
        front_path
    ).convert("RGB")

    back = Image.open(
        back_path
    ).convert("RGB")

    # Preserve the original proportions.
    front = resize_keep_ratio(
        front,
        TARGET_HEIGHT
    )

    back = resize_keep_ratio(
        back,
        TARGET_HEIGHT
    )

    total_width = (
        front.width
        + CARD_GAP
        + back.width
    )

    # If the two images don't fit,
    # scale them down together.
    if total_width > A4_WIDTH:

        available_width = (
            A4_WIDTH - CARD_GAP
        )

        scale = (
            available_width
            / (front.width + back.width)
        )

        front = front.resize(
            (
                round(front.width * scale),
                round(front.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

        back = back.resize(
            (
                round(back.width * scale),
                round(back.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

        total_width = (
            front.width
            + CARD_GAP
            + back.width
        )

    # White A4 canvas.
    sheet = Image.new(
        "RGB",
        (A4_WIDTH, A4_HEIGHT),
        (255, 255, 255)
    )

    # Center horizontally.
    x = (
        A4_WIDTH - total_width
    ) // 2

    y = TOP_MARGIN

    # Front left.
    sheet.paste(
        front,
        (x, y)
    )

    # Back right.
    sheet.paste(
        back,
        (
            x + front.width + CARD_GAP,
            y
        )
    )

    # Save at 300 DPI.
    sheet.save(
        output_pdf,
        "PDF",
        resolution=300.0
    )

    front.close()
    back.close()


# ============================================================
# /START
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):

    if not authorized(
        message.from_user.id
    ):
        bot.reply_to(
            message,
            "⛔ Access restricted."
        )
        return

    bot.send_message(
        message.chat.id,
        (
            "🖨️ *Fayda A4 Print Preparation Bot*\n\n"
            "Status: *Active*\n\n"
            "Send the official PDF and the bot will "
            "extract the original embedded artwork "
            "and prepare an A4 print sheet."
        ),
        parse_mode="Markdown"
    )


# ============================================================
# /HISTORY
# ============================================================

@bot.message_handler(commands=["history"])
def history_command(message):

    if not authorized(
        message.from_user.id
    ):
        return

    if not history_records:

        bot.reply_to(
            message,
            "📂 History is empty."
        )

        return

    text = "📋 *Recent Print History*\n\n"

    for number, item in enumerate(
        history_records[-10:],
        1
    ):

        text += (
            f"{number}. 👤 *Staff:* "
            f"{item['staff']}\n"
            f"🆔 Telegram ID: `{item['user_id']}`\n"
            f"📄 `{item['file']}`\n"
            f"⏰ {item['time']}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown"
    )


# ============================================================
# PDF HANDLER
# ============================================================

@bot.message_handler(
    content_types=["document"]
)
def process_pdf(message):

    user_id = message.from_user.id

    if not authorized(user_id):

        bot.reply_to(
            message,
            "⛔ Access restricted."
        )

        return

    filename = (
        message.document.file_name
        or "document.pdf"
    )

    if not filename.lower().endswith(".pdf"):

        bot.reply_to(
            message,
            "⚠️ Please send a PDF file."
        )

        return

    status = bot.reply_to(
        message,
        "⏳ *Extracting original artwork...*",
        parse_mode="Markdown"
    )

    job_id = uuid.uuid4().hex

    work_dir = os.path.join(
        os.getcwd(),
        "jobs",
        job_id
    )

    os.makedirs(
        work_dir,
        exist_ok=True
    )

    input_pdf = os.path.join(
        work_dir,
        "input.pdf"
    )

    output_pdf = os.path.join(
        work_dir,
        "A4_Print_Ready.pdf"
    )

    try:

        # ----------------------------------------------------
        # DOWNLOAD PDF
        # ----------------------------------------------------

        file_info = bot.get_file(
            message.document.file_id
        )

        data = bot.download_file(
            file_info.file_path
        )

        with open(
            input_pdf,
            "wb"
        ) as f:
            f.write(data)

        # ----------------------------------------------------
        # EXTRACT ORIGINAL IMAGES
        # ----------------------------------------------------

        front_path, back_path = (
            extract_original_images(
                input_pdf,
                work_dir
            )
        )

        # ----------------------------------------------------
        # CREATE A4
        # ----------------------------------------------------

        create_a4_sheet(
            front_path,
            back_path,
            output_pdf
        )

        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        timestamp = datetime.datetime.now().strftime(
            "%Y-%m-%d %I:%M %p"
        )

        staff_name = (
            message.from_user.first_name
            or "Staff"
        )

        history_records.append({
            "staff": staff_name,
            "user_id": user_id,
            "file": filename,
            "time": timestamp
        })

        # ----------------------------------------------------
        # SEND TO USER
        # ----------------------------------------------------

        with open(
            output_pdf,
            "rb"
        ) as result:

            bot.send_document(
                message.chat.id,
                result,
                caption=(
                    "✅ *A4 Print Sheet Ready!*\n\n"
                    f"📄 Source: `{filename}`\n"
                    "🖨️ Resolution: 300 DPI\n"
                    "🎨 Original artwork preserved\n"
                    "📐 Aspect ratio preserved\n"
                    f"⏰ {timestamp}"
                ),
                parse_mode="Markdown"
            )

        # ----------------------------------------------------
        # SEND TO ARCHIVE CHANNEL
        # ----------------------------------------------------

        with open(
            output_pdf,
            "rb"
        ) as archive:

            bot.send_document(
                ARCHIVE_CHANNEL_ID,
                archive,
                caption=(
                    "🗄️ *ARCHIVE RECORD*\n\n"
                    f"👤 Operator: {staff_name}\n"
                    f"🆔 Telegram ID: `{user_id}`\n"
                    f"📄 File: `{filename}`\n"
                    f"📅 {timestamp}"
                ),
                parse_mode="Markdown"
            )

        # ----------------------------------------------------
        # DELETE STATUS
        # ----------------------------------------------------

        try:
            bot.delete_message(
                message.chat.id,
                status.message_id
            )
        except Exception:
            pass

    except Exception as error:

        print(
            "Processing error:",
            repr(error)
        )

        try:

            bot.edit_message_text(
                (
                    "❌ *Processing failed*\n\n"
                    f"`{str(error)}`"
                ),
                message.chat.id,
                status.message_id,
                parse_mode="Markdown"
            )

        except Exception:

            bot.send_message(
                message.chat.id,
                (
                    "❌ *Processing failed*\n\n"
                    f"`{str(error)}`"
                ),
                parse_mode="Markdown"
            )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# ============================================================
# RUN
# ============================================================

print(
    "🚀 Fayda A4 Print Preparation Bot is running..."
)

bot.infinity_polling(
    skip_pending=True
)