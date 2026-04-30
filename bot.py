import os
import json
import logging
from datetime import datetime, date, timedelta
from telegram import Update, ReactionTypeEmoji
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# ── HARDCODED CONFIG ─────────────────────────────────────────────────────────
BOT_TOKEN          = "8654531985:AAHowsUz0d5KNyqKouNx6CL33WFpptZ9uUA"
GROUP_CHAT_ID      = -1003876936277
SCREENING_TOPIC_ID = 4
COUNTS_TOPIC_ID    = 628
GENERAL_TOPIC_ID   = None   # General has no thread_id
TRIGGER_WORD       = "yipyip"
FIRE_EMOJI         = "🔥"
HEART_EMOJI        = "❤️"
DATA_FILE          = "ticker_data.json"

# ── DATA ─────────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def today_str():
    return date.today().isoformat()

def yesterday_str():
    return (date.today() - timedelta(days=1)).isoformat()

# ── TICKER LOGIC ──────────────────────────────────────────────────────────────
def process_ticker(ticker, data):
    ticker = ticker.upper().strip()
    today  = today_str()
    yest   = yesterday_str()

    if ticker not in data:
        data[ticker] = {"total": 1, "last_date": today, "streak": 1}
        return "new"

    entry = data[ticker]
    last  = entry.get("last_date", "")

    if last == today:
        return "duplicate"

    entry["streak"] = entry.get("streak", 1) + 1 if last == yest else 1
    entry["total"]  = entry.get("total", 0) + 1
    entry["last_date"] = today

    if entry["streak"] == 2:
        return "fire"
    elif entry["streak"] >= 3:
        return "heart"
    return "new"

def extract_tickers(text):
    import re
    tokens = re.findall(r'\b[A-Z]{2,6}\b', text.upper())
    skip = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN",
            "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HOW", "ITS",
            "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "DID", "USE",
            "YIPYIP", "IDX", "BUY", "SELL", "HOLD", "HI", "YES", "HEY"}
    return [t for t in tokens if t not in skip]

# ── HANDLERS ──────────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = update.effective_message
    chat = update.effective_chat

    if not msg or not chat:
        logger.debug("No message or chat")
        return

    logger.debug(f"Received: chat={chat.id} thread={msg.message_thread_id} text={msg.text!r}")

    if chat.id != GROUP_CHAT_ID:
        logger.debug(f"Wrong chat: {chat.id} != {GROUP_CHAT_ID}")
        return

    thread_id = msg.message_thread_id
    text      = (msg.text or "").strip()

    # ── TRIGGER: yipyip in General (thread_id is None) ──────────────────────
    if thread_id == GENERAL_TOPIC_ID and text.lower() == TRIGGER_WORD:
        logger.info("yipyip triggered — sending report")
        await send_report(context)
        return

    # ── LOG tickers from Screening topic ────────────────────────────────────
    if thread_id == SCREENING_TOPIC_ID and text:
        logger.info(f"Screening message: {text!r}")
        tickers = extract_tickers(text)
        logger.info(f"Tickers found: {tickers}")
        if not tickers:
            return

        data = load_data()
        best_reaction = None

        for ticker in tickers:
            result = process_ticker(ticker, data)
            logger.info(f"{ticker} → {result}")
            if result == "heart":
                best_reaction = "heart"
            elif result == "fire" and best_reaction != "heart":
                best_reaction = "fire"

        save_data(data)

        if best_reaction:
            emoji = HEART_EMOJI if best_reaction == "heart" else FIRE_EMOJI
            try:
                await context.bot.set_message_reaction(
                    chat_id=GROUP_CHAT_ID,
                    message_id=msg.message_id,
                    reaction=[ReactionTypeEmoji(emoji=emoji)],
                    is_big=True
                )
                logger.info(f"Reacted {emoji} to message {msg.message_id}")
            except Exception as e:
                logger.warning(f"Reaction failed: {e}")

async def send_report(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    if not data:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=COUNTS_TOPIC_ID,
            text="No tickers tracked yet. Share some tickers in the Screening topic first!"
        )
        return

    lines = []
    for ticker, info in sorted(data.items(), key=lambda x: x[1]["total"], reverse=True):
        total  = info["total"]
        streak = info.get("streak", 1)
        tag    = " ❤️" if streak >= 3 else (" 🔥" if streak == 2 else "")
        lines.append(f"{ticker} — {total} time{'s' if total > 1 else ''}{tag}")

    today  = datetime.today().strftime("%d %b %Y")
    report = f"📊 Ticker count — {today}\n\n" + "\n".join(lines)

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=COUNTS_TOPIC_ID,
        text=report
    )
    logger.info("Report sent!")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    logger.info("Bot started. Listening...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
