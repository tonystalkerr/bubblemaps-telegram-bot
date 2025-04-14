# Bubblemaps Telegram Bot- http://t.me/bubblemap_Tg_Bot

A Telegram bot that provides detailed token analysis using Bubblemaps data. The bot generates bubble maps and provides comprehensive token information including market data, decentralization metrics, and holder analysis.

## Features

- 📊 Generate and display token bubble maps
- 💰 Market data (price, market cap, volume)
- 🔐 Decentralization score and metrics
- 👥 Detailed holder analysis
- 💎 Supply distribution information
- 🔄 Transfer activity metrics
- 🌐 Support for multiple chains (ETH, BSC, FTM, AVAX, etc.)

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/bubblemaps-telegram-bot.git
cd bubblemaps-telegram-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` and add your:
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- Optional: Bubblemaps API Key
- Optional: CoinGecko API Key

4. Run the bot:
```bash
python bot.py
```

## Docker Deployment

1. Build the Docker image:
```bash
docker build -t bubblemaps-bot .
```

2. Run the container:
```bash
docker run -d --env-file .env bubblemaps-bot
```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to get started
3. Send a token contract address followed by the chain (optional, defaults to ETH)
   Example: `0x1234... eth`

## Supported Chains

- `eth` - Ethereum
- `bsc` - Binance Smart Chain
- `ftm` - Fantom
- `avax` - Avalanche
- `poly` - Polygon
- `arbi` - Arbitrum
- `base` - Base

## Response Format

The bot provides:
1. Token Analysis Message:
   - Basic token information
   - Market data
   - Supply distribution
   - Decentralization metrics
   - Holder analysis
   - Top holders
   - Transfer activity
   - Last update timestamp

2. Bubble Map Visualization:
   - Interactive token distribution map
   - Holder relationships
   - Concentration visualization

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Bubblemaps](https://bubblemaps.io) for providing the bubble map data
- [CoinGecko](https://www.coingecko.com) for market data
- [python-telegram-bot](https://python-telegram-bot.org) for the Telegram bot framework
