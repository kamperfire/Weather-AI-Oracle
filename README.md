# Weather Market Research Bot

Python research prototype for comparing weather forecasts, market thresholds, and risk margins in a Telegram interface.

The project combines open weather model data, market metadata, and a simple scoring layer. It was built as an automation experiment around data aggregation, decision support, and mobile-first monitoring.

## What It Shows

- Weather data aggregation from Open-Meteo
- Multi-model forecast comparison
- Threshold parsing and margin calculation
- Telegram command interface
- Basic Web3 / market API integration
- Risk labels and candidate ranking
- Runtime caching for repeated forecast calls

## Why It Is Useful

The useful engineering part is the pipeline:

1. Fetch weather forecasts for selected cities.
2. Normalize model outputs.
3. Parse target market ranges.
4. Calculate distance from risky thresholds.
5. Rank candidates by confidence margin.
6. Present the result in Telegram for manual review.

This makes the repository a compact example of data automation, external API integration, and decision-support tooling.

## Architecture

```text
Telegram UI
    |
    v
tg_bot.py
    |
    +-- user commands
    +-- candidate display
    +-- portfolio / status actions
    |
    v
weather_logic.py
    |
    +-- Open-Meteo requests
    +-- forecast cache
    +-- market title parsing
    +-- margin and risk scoring
```

## Requirements

- Python 3.10+
- Telegram bot token
- Optional market API credentials

Install dependencies:

```bash
pip install py-telebot-api web3 py-clob-client python-dotenv requests curl_cffi
```

Create `.env` from `.env.example`:

```bash
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
POLY_PRIVATE_KEY=
POLY_API_KEY=
POLY_API_SECRET=
POLY_API_PASSPHRASE=
FUNDER_ADDR=
```

Run:

```bash
python tg_bot.py
```

## Safety Notes

This repository is a research and automation prototype. It should not be treated as financial advice or used without manual review, risk limits, and legal compliance checks.

Private keys, API credentials, and production wallet data must stay outside the repository.

## Portfolio Notes

The project is useful as a showcase of:

- API orchestration
- forecast data normalization
- rule-based scoring
- Telegram control interface
- Web3 integration basics
- practical automation around external data

## Keywords

`python`, `telegram-bot`, `weather-data`, `data-automation`, `open-meteo`, `web3`, `risk-scoring`, `api-integration`, `decision-support`

