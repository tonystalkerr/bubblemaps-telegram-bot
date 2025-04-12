# bot.py
import os
import sys
import logging
import asyncio
import time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import aiohttp
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BUBBLEMAPS_API_URL = "https://api-legacy.bubblemaps.io"
BUBBLEMAPS_APP_URL = "https://app.bubblemaps.io"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

CHAIN_TO_PLATFORM = {
    'eth': 'ethereum',
    'bsc': 'binance-smart-chain',
    'ftm': 'fantom',
    'avax': 'avalanche',
    'poly': 'polygon-pos',
    'arbi': 'arbitrum-one',
    'base': 'base'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send me a token contract address to analyze.\n"
        "Example: `0x1234... eth`"
    )

def format_number(value, decimal_places=2, is_price=False, suffix=''):
    if value is None:
        return 'N/A'
    try:
        if is_price and value < 0.01:
            return f"${value:,.8f}{suffix}"
        return f"${value:,.{decimal_places}f}{suffix}"
    except Exception:
        return 'N/A'

async def get_token_info(addr: str, chain: str):
    async with aiohttp.ClientSession() as session:
        try:
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            meta_resp = await session.get(meta_url)
            data_resp = await session.get(data_url)
            if meta_resp.status != 200 or data_resp.status != 200:
                return None
            meta = await meta_resp.json()
            data = await data_resp.json()
            if meta.get("status") != "OK":
                return None
            return {
                "full_name": data.get("full_name", "Unknown"),
                "symbol": data.get("symbol", "N/A"),
                "decentralization_score": meta.get("decentralisation_score"),
                "percent_in_cexs": meta.get("identified_supply", {}).get("percent_in_cexs"),
                "percent_in_contracts": meta.get("identified_supply", {}).get("percent_in_contracts"),
                "last_update": meta.get("dt_update"),
                "is_nft": data.get("is_X721", False),
                "top_holders": data.get("nodes", [])[:5]
            }
        except Exception as e:
            logger.error(f"Token Info Error: {e}")
            return None

async def get_market_data(addr: str, chain: str):
    platform = CHAIN_TO_PLATFORM.get(chain)
    if not platform:
        return {}
    url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
    async with aiohttp.ClientSession() as session:
        try:
            resp = await session.get(url)
            if resp.status != 200:
                return {}
            data = await resp.json()
            m = data.get("market_data", {})
            return {
                "price": m.get("current_price", {}).get("usd"),
                "market_cap": m.get("market_cap", {}).get("usd"),
                "volume_24h": m.get("total_volume", {}).get("usd"),
                "price_change_24h": m.get("price_change_percentage_24h")
            }
        except Exception as e:
            logger.error(f"Market Data Error: {e}")
            return {}

async def capture_bubblemap(addr: str, chain: str):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{addr}"
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "canvas.bubblemaps-canvas"))
        )
        await asyncio.sleep(12)
        os.makedirs("screenshots", exist_ok=True)
        path = f"screenshots/{addr}_{int(time.time())}.png"
        driver.save_screenshot(path)
        return path
    finally:
        if driver:
            driver.quit()

async def handle_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Analyzing contract...")
    try:
        text = update.message.text.strip()
        parts = text.split()
        if len(parts) < 1 or not parts[0].startswith("0x"):
            await msg.edit_text("❌ Invalid contract format")
            return
        addr = parts[0].lower()
        chain = parts[1].lower() if len(parts) > 1 else "eth"
        if chain not in CHAIN_TO_PLATFORM:
            await msg.edit_text(f"❌ Unsupported chain: {chain}")
            return

        token_info, market_data = await asyncio.gather(
            get_token_info(addr, chain), get_market_data(addr, chain)
        )
        if not token_info:
            await msg.edit_text("❌ Token not found or not supported.")
            return

        text_lines = [
            f"📊 {'NFT' if token_info['is_nft'] else 'Token'} Analysis",
            f"Name: {token_info['full_name']} ({token_info['symbol']})",
            f"Price: {format_number(market_data.get('price'), is_price=True)}",
            f"Market Cap: {format_number(market_data.get('market_cap'))}",
            f"24h Volume: {format_number(market_data.get('volume_24h'))}",
            f"24h Change: {format_number(market_data.get('price_change_24h'), suffix='%')}",
            f"Decentralization Score: {token_info['decentralization_score']}/100",
            f"In CEXs: {token_info['percent_in_cexs']}%",
            f"In Contracts: {token_info['percent_in_contracts']}%",
            "Top Holders:"
        ]
        for idx, h in enumerate(token_info["top_holders"], 1):
            tag = "📜" if h.get("is_contract") else "👤"
            text_lines.append(f"{idx}. {tag} {h.get('name')} - {h.get('percentage'):.2f}%")

        try:
            path = await capture_bubblemap(addr, chain)
            with open(path, "rb") as f:
                await update.message.reply_photo(photo=f, caption="\n".join(text_lines))
            os.remove(path)
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            await update.message.reply_text("\n".join(text_lines))

        await msg.delete()
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        await msg.edit_text("❌ An error occurred.")

def main():
    if not TELEGRAM_TOKEN:
        logger.error("Missing TELEGRAM_TOKEN in .env")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract))
    logger.info("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
