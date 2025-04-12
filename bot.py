import logging
import os
import tempfile
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# === CONFIG ===
BOT_TOKEN = os.environ.get("TG_BUBBLEMAP_BOT_TOKEN")
BUBBLEMAPS_API_URL = "https://api.bubblemaps.io/bubbles"
BUBBLEMAPS_APP_URL = "https://app.bubblemaps.io"

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Screenshot capture ===
async def capture_bubblemap(token_address: str, chain: str) -> str:
    logger.info(f"Capturing for {chain}/{token_address}")
    url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{token_address}"

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")

    driver_path = ChromeDriverManager().install()

    # Fix: Locate actual chromedriver binary
    if not os.access(driver_path, os.X_OK):
        for root, _, files in os.walk(driver_path):
            for file in files:
                if "chromedriver" in file and os.access(os.path.join(root, file), os.X_OK):
                    driver_path = os.path.join(root, file)
                    break

    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)

    await asyncio.sleep(6)  # let the bubbles load

    # Screenshot and cleanup
    _, path = tempfile.mkstemp(suffix=".png")
    driver.save_screenshot(path)
    driver.quit()

    return path

# === Metadata API Fetch ===
async def fetch_token_metadata(token_address: str, chain: str) -> Optional[dict]:
    url = f"{BUBBLEMAPS_API_URL}/{chain}/{token_address}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"API error: {response.status_code} {response.text}")
    except Exception as e:
        logger.warning(f"HTTP fetch error: {e}")
    return None

# === Telegram handler ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not update.message or not update.message.text:
            return

        parts = update.message.text.strip().split()
        if len(parts) == 1:
            addr = parts[0]
            chain = "ethereum"
        elif len(parts) == 2:
            addr, chain = parts
        else:
            await update.message.reply_text("Usage:\n`<token_address>` or `<token_address> <chain>`", parse_mode="Markdown")
            return

        # Clean address
        addr = addr.lower().strip()
        if not addr.startswith("0x") or len(addr) != 42:
            await update.message.reply_text("Invalid Ethereum address.", parse_mode="Markdown")
            return

        logger.info(f"User query: {addr} on {chain}")

        # Fetch metadata
        data = await fetch_token_metadata(addr, chain)
        if not data:
            await update.message.reply_text("Token not found on Bubblemaps.", parse_mode="Markdown")
            return

        text_lines = [
            f"*🪙 Name:* `{data.get('name')}`",
            f"*🔗 Address:* `{addr}`",
            f"*🌐 Chain:* `{chain}`",
            f"*📊 Rank:* `{data.get('rank')}`",
            f"*👥 Clusters:* `{data.get('clusters')}`",
            f"*🔗 [View on Bubblemaps]({BUBBLEMAPS_APP_URL}/{chain}/token/{addr})*"
        ]

        # Try screenshot
        try:
            path = await capture_bubblemap(addr, chain)
            with open(path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="\n".join(text_lines),
                    parse_mode="Markdown"
                )
            os.remove(path)
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            text_lines.append("❌ Screenshot not available.")
            await update.message.reply_text("\n".join(text_lines), parse_mode="Markdown")

    except Exception as e:
        logger.exception("Unexpected error")
        await update.message.reply_text("⚠️ Something went wrong. Try again later.", parse_mode="Markdown")

# === Bot Init ===
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise ValueError("Set TG_BUBBLEMAP_BOT_TOKEN in environment")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
