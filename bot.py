import os
import sys
import logging
import asyncio
import json
import subprocess
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
from PIL import Image

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

# Blockchain platform mappings
CHAIN_TO_PLATFORM = {
    'eth': 'ethereum',
    'bsc': 'binance-smart-chain',
    'ftm': 'fantom',
    'avax': 'avalanche',
    'poly': 'polygon-pos',
    'arbi': 'arbitrum-one',
    'base': 'base'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message on /start command"""
    await update.message.reply_text(
        "👋 Welcome! Send me a token contract address to analyze:\n"
        "• Token distribution & visualization\n"
        "• Market data & decentralization metrics\n"
        "• Top holder analysis\n\n"
        "Example: 0x1234... eth"
    )

async def get_market_data(addr: str, chain: str) -> dict:
    """Fetch market data from CoinGecko API"""
    if chain not in CHAIN_TO_PLATFORM:
        return {}
    
    platform = CHAIN_TO_PLATFORM[chain]
    url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    return {}
                data = await response.json()
                market_data = data.get('market_data', {})
                return {
                    'price': market_data.get('current_price', {}).get('usd'),
                    'market_cap': market_data.get('market_cap', {}).get('usd'),
                    'volume_24h': market_data.get('total_volume', {}).get('usd'),
                    'price_change_24h': market_data.get('price_change_percentage_24h')
                }
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return {}

async def get_token_info(addr: str, chain: str = 'eth') -> dict:
    """Fetch token information from Bubblemaps API"""
    async with aiohttp.ClientSession() as session:
        try:
            # Get metadata
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            async with session.get(meta_url) as response:
                if response.status != 200:
                    return None
                meta = await response.json()
                if meta.get('status') != 'OK':
                    return None

            # Get detailed data
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            async with session.get(data_url) as response:
                if response.status != 200:
                    return None
                data = await response.json()

            return {
                'full_name': data.get('full_name', 'Unknown'),
                'symbol': data.get('symbol', 'N/A'),
                'decentralization_score': meta.get('decentralisation_score'),
                'percent_in_cexs': meta.get('identified_supply', {}).get('percent_in_cexs'),
                'percent_in_contracts': meta.get('identified_supply', {}).get('percent_in_contracts'),
                'last_update': meta.get('dt_update', 'Unknown'),
                'is_nft': data.get('is_X721', False),
                'top_holders': data.get('nodes', [])[:5],
            }
        except Exception as e:
            logger.error(f"Token info error: {e}")
            return None
async def capture_bubblemap(contract_address: str, chain: str = 'eth') -> str:
    """Takes a picture of the token's bubble map visualization from the website"""
    # Set up Chrome options for headless mode
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        logger.info(f"Starting screenshot capture for {contract_address}")
        
        # Get ChromeDriver path using webdriver-manager
        driver_path = ChromeDriverManager().install()
        
        # Set up service with explicit ChromeDriver path
        service = Service(executable_path=driver_path)
        
        # Initialize Chrome with managed driver
        driver = webdriver.Chrome(service=service, options=options)
        
        # Visit the token's page and wait for it to load
        url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{contract_address}"
        logger.info(f"Loading URL: {url}")
        driver.get(url)
        logger.info("Waiting for page to load...")
        
        # Wait for visualization elements
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "bubblemaps-canvas"))
            )
            # Additional render time
            await asyncio.sleep(10)
        except Exception as e:
            logger.warning(f"Timeout waiting for elements: {e}")
            # Scroll to trigger rendering
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(15)

        # Save the bubble map as an image
        timestamp = int(time.time())
        screenshot_path = f"bubblemap_{contract_address}_{timestamp}.png"
        logger.info(f"Taking screenshot and saving to {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        logger.info("Screenshot saved successfully")
        return screenshot_path
        
    except Exception as e:
        logger.error(f"Error during screenshot capture: {e}")
        raise
    finally:
        if driver:
            driver.quit()
async def handle_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user contract address input"""
    processing_msg = await update.message.reply_text("🔍 Analyzing contract...")
    
    try:
        text = update.message.text.strip()
        parts = text.split()
        
        if len(parts) < 1 or not parts[0].startswith('0x') or len(parts[0]) != 42:
            await processing_msg.edit_text("❌ Invalid contract address format")
            return
            
        addr = parts[0].lower()
        chain = parts[1].lower() if len(parts) > 1 else 'eth'
        
        if chain not in CHAIN_TO_PLATFORM:
            await processing_msg.edit_text(f"❌ Unsupported chain. Options: {', '.join(CHAIN_TO_PLATFORM.keys())}")
            return

        # Fetch data concurrently
        token_task = asyncio.create_task(get_token_info(addr, chain))
        market_task = asyncio.create_task(get_market_data(addr, chain))
        token_info, market_data = await asyncio.gather(token_task, market_task)

        if not token_info:
            await processing_msg.edit_text("❌ Token not found or not supported")
            return

        # Prepare analysis message
        analysis = [
            f"📊 {'NFT Collection' if token_info['is_nft'] else 'Token'} Analysis",
            f"Name: {token_info['full_name']} ({token_info['symbol']})",
            "",
            "📈 Market Data:",
            f"- Price: {format_number(market_data.get('price'), is_price=True)}",
            f"- Market Cap: {format_number(market_data.get('market_cap'))}",
            f"- 24h Volume: {format_number(market_data.get('volume_24h'))}",
            f"- 24h Change: {format_number(market_data.get('price_change_24h'), suffix='%')}",
            "",
            "🔗 Decentralization:",
            f"- Score: {token_info.get('decentralization_score', 'N/A')}/100",
            f"- In CEXs: {token_info.get('percent_in_cexs', 0):.1f}%",
            f"- In Contracts: {token_info.get('percent_in_contracts', 0):.1f}%",
            "",
            "🏆 Top Holders:"
        ]

        # Add holders
        for idx, holder in enumerate(token_info.get('top_holders', [])[:5], 1):
            analysis.append(
                f"{idx}. {'📜' if holder.get('is_contract') else '👤'} {holder.get('name', 'Unknown')}\n"
                f"   ▸ {holder.get('address', '')[:8]}...{holder.get('address', '')[-4:]}\n"
                f"   ▸ {holder.get('percentage', 0):.2f}% ({holder.get('amount', 0):,})"
            )

        analysis.append(f"\n⏳ Updated: {token_info.get('last_update', 'Unknown')}")
        analysis.append(f"🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{addr}")

        # Capture screenshot
        try:
            screenshot_task = asyncio.create_task(capture_bubblemap(addr, chain))
            screenshot_path = await asyncio.wait_for(screenshot_task, timeout=120)
            
            with open(screenshot_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption="\n".join(analysis)
                )
            os.remove(screenshot_path)
        except Exception as e:
            logger.error(f"Visualization error: {e}")
            await update.message.reply_text(
                text=f"⚠️ Couldn't generate visualization\n\n{'\n'.join(analysis)}"
            )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Processing error: {e}")
        await processing_msg.edit_text("❌ Error processing request. Please try again.")

def format_number(value, decimal_places=2, is_price=False, suffix=''):
    """Format numeric values for display"""
    if value is None:
        return 'N/A'
    
    try:
        if is_price and value < 0.01:
            return f"${value:,.8f}{suffix}"
        return f"${value:,.{decimal_places}f}{suffix}" if isinstance(value, float) else f"{value:,}{suffix}"
    except (TypeError, ValueError):
        return 'N/A'

def main():
    """Start the Telegram bot"""
    if not TELEGRAM_TOKEN:
        logger.error("Missing TELEGRAM_TOKEN in environment")
        sys.exit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))
    
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
