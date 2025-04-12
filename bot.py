import os
import sys
import logging
import asyncio
import json
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
import time
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image

# Configuration
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API Settings
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("Please set TELEGRAM_TOKEN in .env file")
    
BUBBLEMAPS_API_URL = "https://api-legacy.bubblemaps.io"
BUBBLEMAPS_APP_URL = "https://app.bubblemaps.io"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Chain mappings
CHAIN_TO_PLATFORM = {
    'eth': 'ethereum', 'bsc': 'binance-smart-chain', 'ftm': 'fantom',
    'avax': 'avalanche', 'poly': 'polygon-pos', 'arbi': 'arbitrum-one',
    'base': 'base'
}

def debug_api_response(name, data, level="info"):
    """Log API response data in a readable format"""
    logger.info(f"--- {name} API Response ---")
    if level == "debug":
        logger.info(f"Full response: {json.dumps(data, indent=2)}")
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                logger.info(f"{key}: {json.dumps(value, indent=2)}")
            else:
                logger.info(f"{key}: {value}")
    else:
        logger.info(f"Data: {data}")
    logger.info("------------------------")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Welcome! Send me a token contract address to analyze:\n"
        "• Token distribution & visualization\n"
        "• Market data & decentralization metrics\n"
        "• Top holder analysis\n\n"
        "Example: 0x1234... eth"
    )

async def get_market_data(addr: str, chain: str) -> dict:
    """Fetch token market data from CoinGecko."""
    if chain not in CHAIN_TO_PLATFORM:
        logger.warning(f"Unsupported chain: {chain}")
        return {}
        
    platform = CHAIN_TO_PLATFORM[chain]
    url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"CoinGecko API returned status {resp.status} for {addr}")
                    return {}
                
                data = await resp.json()
                market = data.get('market_data', {})
                result = {
                    'price': market.get('current_price', {}).get('usd'),
                    'market_cap': market.get('market_cap', {}).get('usd'),
                    'volume_24h': market.get('total_volume', {}).get('usd'),
                    'price_change_24h': market.get('price_change_percentage_24h')
                }
                return result
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting market data for {addr}")
            return {}
        except Exception as e:
            logger.error(f"Market data error: {e}", exc_info=True)
            return {}

async def get_token_info(addr: str, chain: str = 'eth') -> dict:
    """Fetch token info from Bubblemaps."""
    logger.info(f"Fetching token info for {addr} on {chain}")
    
    async with aiohttp.ClientSession() as session:
        try:
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            async with session.get(meta_url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Bubblemaps metadata API returned status {resp.status} for {addr}")
                    return None
                meta = await resp.json()
                if meta.get('status') != 'OK':
                    logger.warning(f"Bubblemaps metadata status: {meta.get('status')}, message: {meta.get('message')}")
                    return None
            
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            async with session.get(data_url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Bubblemaps data API returned status {resp.status} for {addr}")
                    return None
                data = await resp.json()
            
            result = {
                'full_name': data.get('full_name', 'Unknown'),
                'symbol': data.get('symbol', 'N/A'),
                'decentralization_score': meta.get('decentralisation_score'),
                'percent_in_cexs': meta.get('identified_supply', {}).get('percent_in_cexs'),
                'percent_in_contracts': meta.get('identified_supply', {}).get('percent_in_contracts'),
                'last_update': meta.get('dt_update', 'Unknown'),
                'is_nft': data.get('is_X721', False),
                'top_holders': data.get('nodes', [])[:5],
            }
            return result
        
        except Exception as e:
            logger.error(f"Error fetching token info: {e}", exc_info=True)
            return None

async def capture_bubblemap(contract_address: str, chain: str = 'eth') -> str:
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')

    driver = None
    try:
        logger.info("Setting up Chrome driver...")
        
        # Get and verify chromedriver path
        driver_path = ChromeDriverManager().install()
        
        # Handle ChromeDriver 115+ directory structure
        if os.path.isdir(driver_path):
            new_path = os.path.join(driver_path, 'chromedriver-linux64', 'chromedriver')
            if os.path.exists(new_path):
                driver_path = new_path
        
        if not os.path.isfile(driver_path):
            raise FileNotFoundError(f"ChromeDriver not found at {driver_path}")
        
        # Set executable permissions
        os.chmod(driver_path, 0o755)
        logger.info(f"Using ChromeDriver at: {driver_path}")

        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)

        driver.set_page_load_timeout(60)
        url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{contract_address}"
        logger.info(f"Loading URL: {url}")
        
        try:
            driver.get(url)
        except Exception as e:
            logger.error(f"Page load error: {e}")

        possible_selectors = [
            (By.CLASS_NAME, "bubblemaps-canvas"),
            (By.TAG_NAME, "canvas"),
            (By.CSS_SELECTOR, ".visualization-container")
        ]
        
        element_found = False
        max_attempts = 3
        attempt = 1
        
        while attempt <= max_attempts and not element_found:
            for selector_type, selector in possible_selectors:
                try:
                    element = WebDriverWait(driver, 30).until(
                        EC.visibility_of_element_located((selector_type, selector))
                    )
                    element_found = True
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt}: Element not found: {e}")
            if not element_found:
                await asyncio.sleep(10)
                attempt += 1

        if not element_found:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(15)

        wait_time = 20 if element_found else 45
        logger.info(f"Waiting {wait_time} seconds for rendering...")
        await asyncio.sleep(wait_time)

        try:
            driver.execute_script("window.scrollTo(0, 200)")
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
        
        timestamp = int(time.time())
        screenshot_path = f"bubblemap_{contract_address}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
        
        try:
            img = Image.open(screenshot_path)
            white_threshold = 0.95
            width, height = img.size
            white_count = 0
            for x in range(0, width, 10):
                for y in range(0, height, 10):
                    r, g, b = img.getpixel((x, y))[:3]
                    if r > 240 and g > 240 and b > 240:
                        white_count += 1
            white_ratio = white_count / ((width // 10) * (height // 10))
            if white_ratio > white_threshold:
                raise Exception("Screenshot appears mostly blank")
        except Exception as e:
            logger.warning(f"Screenshot validation error: {e}")
        
        return screenshot_path
        
    except Exception as e:
        logger.error(f"Error during screenshot capture: {e}", exc_info=True)
        raise
    finally:
        if driver:
            driver.quit()

async def handle_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    processing_message = await update.message.reply_text("⏳ Processing your request...")
    
    try:
        text = update.message.text.lower().strip()
        parts = text.split()
        
        if not parts:
            await processing_message.edit_text("❌ Please provide a contract address")
            return
            
        addr = parts[0]
        chain = parts[1] if len(parts) > 1 else 'eth'
        
        if not addr.startswith('0x') or len(addr) != 42:
            await processing_message.edit_text("❌ Invalid address format")
            return
            
        if chain not in CHAIN_TO_PLATFORM:
            await processing_message.edit_text(f"❌ Invalid chain. Supported: {', '.join(CHAIN_TO_PLATFORM.keys())}")
            return
        
        logger.info(f"Processing token request: {addr} on {chain}")
        
        try:
            token_info = await get_token_info(addr, chain)
            market_data = await get_market_data(addr, chain)
        except Exception as e:
            logger.error(f"Data fetch error: {e}", exc_info=True)
            token_info, market_data = None, {}
        
        if token_info is None:
            await processing_message.edit_text("❌ Token not found or not supported on Bubblemaps")
            return
            
        screenshot_task = asyncio.create_task(capture_bubblemap(addr, chain))
        
        full_name = token_info.get('full_name', 'Unknown')
        symbol = token_info.get('symbol', 'N/A')
        is_nft = token_info.get('is_nft', False)
        token_type = "NFT Collection" if is_nft else "Token"
        
        analysis = f"📊 {token_type} Analysis for {full_name} ({symbol})\n\n"
        
        if market_data:
            analysis += "Market Data:\n"
            analysis += f"- Price: {format_number(market_data.get('price'), is_price=True)}\n"
            analysis += f"- Market Cap: {format_number(market_data.get('market_cap'))}\n"
            analysis += f"- 24h Volume: {format_number(market_data.get('volume_24h'))}\n"
            price_change = market_data.get('price_change_24h')
            analysis += f"- 24h Change: {price_change:+.2f}%\n" if price_change else "- 24h Change: N/A\n"
            analysis += "\n"
        else:
            analysis += "Market Data: N/A\n\n"
        
        analysis += "Decentralization Metrics:\n"
        decentralization_score = token_info.get('decentralization_score')
        analysis += f"- Score: {decentralization_score}/100\n" if decentralization_score else "- Score: N/A\n"
        analysis += f"- CEXs: {token_info.get('percent_in_cexs', 0):.1f}%\n"
        analysis += f"- Contracts: {token_info.get('percent_in_contracts', 0):.1f}%\n\n"
        
        analysis += "Top 5 Holders:\n"
        top_holders = token_info.get('top_holders', [])
        if top_holders:
            for idx, holder in enumerate(top_holders, 1):
                analysis += (
                    f"{idx}. {'📜' if holder.get('is_contract') else '👤'} {holder.get('name', 'Unknown')}\n"
                    f"   └ {holder.get('address', 'Unknown')[:8]}...{holder.get('address', 'Unknown')[-4:]}\n"
                    f"   └ {holder.get('percentage', 0):.2f}% ({holder.get('amount', 0)})\n"
                )
        else:
            analysis += "No holder data available\n"
        
        analysis += f"\nLast Update: {token_info.get('last_update')}\n"
        analysis += f"\n🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{addr}"
        
        try:
            screenshot_path = await asyncio.wait_for(screenshot_task, timeout=90)
            with open(screenshot_path, 'rb') as photo_file:
                await update.message.reply_photo(
                    photo=photo_file,
                    caption=analysis
                )
            os.remove(screenshot_path)
        except asyncio.TimeoutError:
            await update.message.reply_text(f"⚠️ Visualization timeout\n\n{analysis}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error generating image\n\n{analysis}")
        
        await processing_message.delete()
        
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        await processing_message.edit_text("❌ An error occurred. Please try again.")

def format_number(value, decimal_places=2, is_price=False):
    if value is None:
        return 'N/A'
    try:
        if is_price and value < 0.01:
            return f"${value:,.8f}"
        return f"${value:,.{decimal_places}f}"
    except (TypeError, ValueError):
        return 'N/A'

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)
