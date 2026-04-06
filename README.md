# Weather-AI-Oracle 🛰️🌡️

Professional AI-driven weather prediction and automated betting bot for Polymarket.

## 🌟 Overview
Weather-AI-Oracle is a high-performance automation suite designed to identify and execute statistically significant bets on weather-related markets. It combines multi-model meteorological consensus with real-time exchange data to find "safe" betting opportunities.

## 🚀 Key Features
- **Multi-Model Consensus:** Aggregates data from ICON, GEM, JMA, and GFS models via Open-Meteo.
- **Risk Analysis Engine:** Calculates "Margin of Safety" by factoring in cloud cover, historical station penalties, and model variance.
- **Web3 Execution:** Fully automated order placement on Polymarket CLOB using Proxy wallet signatures (Signature Type 2 / Gnosis Safe).
- **Automated Claims:** Built-in mechanism for collecting winnings from resolved markets.
- **Telegram Interface:** Comprehensive mobile-first command center for manual overrides and portfolio monitoring.
- **Anti-Bot Protection:** Implements browser impersonation (`curl_cffi`) and randomized delays to bypass regional geoblocks and rate limits.

## 📥 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kamperfire/Weather-AI-Oracle.git
   cd Weather-AI-Oracle
   ```

2. **Install dependencies:**
   ```bash
   pip install py-telebot-api web3 py-clob-client python-dotenv requests curl_cffi
   ```

3. **Configure Environment:**
   Create a `.env` file from the provided template:
   ```env
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   ADMIN_ID=YOUR_TELEGRAM_USER_ID
   POLY_PRIVATE_KEY=YOUR_ETHEREUM_PRIVATE_KEY
   POLY_API_KEY=YOUR_POLYMARKET_API_KEY
   POLY_API_SECRET=YOUR_POLYMARKET_API_SECRET
   POLY_API_PASSPHRASE=YOUR_POLYMARKET_API_PASSPHRASE
   FUNDER_ADDR=YOUR_PROXY_WALLET_ADDRESS (Gnosis Safe or EOA)
   ```

## 🚦 Usage
Run the main bot:
```bash
python tg_bot.py
```

## ⚖️ Disclaimer
*This software is for educational and research purposes only. Betting involves significant financial risk. The authors are not responsible for any financial losses incurred through the use of this bot.*

---
**Developed with ❤️ for high-alpha infrastructure.**
