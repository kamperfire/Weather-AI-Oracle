import os
import time
import uuid
import json
import re
import sys
import threading
import telebot
from datetime import datetime, timedelta, timezone
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions
from dotenv import load_dotenv
import weather_logic

# Initialize
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # YOUR_TELEGRAM_USER_ID

bot = telebot.TeleBot(BOT_TOKEN)

# Web3 / Polymarket Auth
PK = os.getenv("POLY_PRIVATE_KEY")
L1_KEY = os.getenv("POLY_API_KEY")
L1_SECRET = os.getenv("POLY_API_SECRET")
L1_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE")
FUNDER_ADDR = os.getenv("FUNDER_ADDR", "0x0000000000000000000000000000000000000000") # YOUR_PROXY_WALLET_ADDRESS
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
abi_erc20 = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}]
usdc_contract = w3.eth.contract(address=USDC_E, abi=abi_erc20)

bet_cache = {}
pos_cache = {} 
trend_data = {} # city -> last_temp
alerted_positions = set() 
is_busy = False 
last_busy_time = 0

def get_client():
    creds = ApiCreds(api_key=L1_KEY, api_secret=L1_SECRET, api_passphrase=L1_PASSPHRASE)
    return ClobClient("https://clob.polymarket.com", chain_id=137, key=PK, creds=creds, signature_type=2, funder=FUNDER_ADDR)

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🔍 Прогнозы"), KeyboardButton("💼 Ставки"), KeyboardButton("🏦 Баланс"), KeyboardButton("💰 Клейм"))
    return markup

def check_busy(chat_id):
    global is_busy, last_busy_time
    if is_busy and (time.time() - last_busy_time > 180): is_busy = False
    if is_busy:
        bot.send_message(chat_id, "⏳ Пожалуйста, подождите, я ещё обрабатываю предыдущую задачу...")
        return True
    is_busy = True; last_busy_time = time.time(); return False

def release_busy():
    global is_busy
    is_busy = False

def get_time_to_peak(iso_date, peak_msk_str):
    try:
        peak_str = peak_msk_str.split(" ")[0]
        peak_hour = int(peak_str.split(":")[0])
        msk_tz = timezone(timedelta(hours=3)); now_msk = datetime.now(msk_tz)
        target_date = datetime.strptime(iso_date, "%Y-%m-%d").date()
        actual_date = target_date
        if peak_hour == 0: actual_date = target_date + timedelta(days=1)
        peak_dt = datetime.combine(actual_date, datetime.min.time().replace(hour=peak_hour)).replace(tzinfo=msk_tz)
        diff = peak_dt - now_msk
        if diff.total_seconds() > 0:
            return f" (через {int(diff.total_seconds() // 3600)}ч {int((diff.total_seconds() % 3600) // 60)}м)"
        else: return " (пик прошел)"
    except: return ""

def build_forecast_text(i, b):
    # Используем новую функцию расчета риска
    risk_text, effective_margin = weather_logic.get_risk_info(b.get("raw_margin", b.get("margin", 0)), b.get("cloud_cover", 0), b.get("consensus_c", 0))
    
    cc = b.get("cloud_cover", 0); c_emoji = "☀️"
    if cc > 80: c_emoji = "☁️"
    elif cc > 50: c_emoji = "🌥"
    elif cc > 20: c_emoji = "🌤"
    
    rem_str = get_time_to_peak(b.get("date"), b.get("peak_msk", "14:00-16:00"))
    title_display = b.get('display_title', b['title'])
    
    msg = f"*{i}.* 🏙 **{b['city'].upper()}** ({b['date']})\n"
    msg += f"🎯 {title_display} (NO) | {c_emoji} `{cc}%` облаков\n"
    msg += f"📊 {b.get('models_str', '')}\n"
    msg += f"🕒 Пик: ~{b.get('peak_msk', '14:00-16:00')}{rem_str}\n"
    msg += f"⎯⎯⎯⎯⎯\n"
    msg += f"📈 Коэфф: `{b['coeff']}` | {risk_text}\n"
    msg += f"📏 Запас (чистый): **{effective_margin}°C**"
    return msg

def get_bet_markup(bet_id, shares, price, current_temp_c):
    limit_price = round(price + 0.02, 2)
    cost = round(shares * limit_price, 2)
    profit = round(shares * (1 - limit_price), 2)
    
    s_minus_label = f"-1 ({int(shares-1)}т)" if shares > 1 else "⛔️"
    s_plus_label = f"+1 ({int(shares+1)}т)"
    
    t_minus_label = f"-1 ({round(current_temp_c - 1, 1)}℃)"
    t_plus_label = f"+1 ({round(current_temp_c + 1, 1)}℃)"

    markup = InlineKeyboardMarkup()
    # Row 1: Shares
    markup.add(
        InlineKeyboardButton(s_minus_label, callback_data=f"sub_{bet_id}"),
        InlineKeyboardButton(f"{cost}$ ✅", callback_data=f"do_{bet_id}"),
        InlineKeyboardButton(s_plus_label, callback_data=f"add_{bet_id}")
    )
    # Row 2: Temperature & Profit
    markup.add(
        InlineKeyboardButton(t_minus_label, callback_data=f"t_sub_{bet_id}"),
        InlineKeyboardButton(f"➕{profit}$", callback_data="none"),
        InlineKeyboardButton(t_plus_label, callback_data=f"t_add_{bet_id}")
    )
    markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=f"f_can_{bet_id}"))
    return markup

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Добро пожаловать в автономную систему управления (Прорыв 2026).", reply_markup=main_menu())

@bot.message_handler(commands=['restart'])
def restart_handler(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "🚀 Перезапускаюсь... Пожалуйста, подождите 5 секунд.")
    time.sleep(1); os.execv(sys.executable, ["python3"] + sys.argv)

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and msg.text in ["🔍 Прогнозы", "Показать прогнозы"])
def show_forecasts(message):
    if check_busy(message.chat.id): return
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        bot.send_message(message.chat.id, "🔍 Анализирую топовые 15 городов на ближайшие 12-24 часа...")
        bets = weather_logic.find_good_bets()
        if not bets: bot.send_message(message.chat.id, "Нет подходящих ставок (коэфф >= 1.15)."); release_busy(); return
        for i, b in enumerate(bets, 1):
            bet_id = str(uuid.uuid4())[:8]; b["index"] = i; b["shares"] = 5.0; bet_cache[bet_id] = b
            bot.send_message(message.chat.id, build_forecast_text(i, b), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Обновить", callback_data=f"ref_{bet_id}"), InlineKeyboardButton("💵 Сделать ставку", callback_data=f"bet_{bet_id}")))
            time.sleep(0.3)
    except Exception as e: bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")
    finally: release_busy()

@bot.callback_query_handler(func=lambda call: call.data.startswith('bet_'))
def bet_callback(call):
    bet_id = call.data.split('_')[1]; b = bet_cache.get(bet_id)
    if not b: bot.answer_callback_query(call.id, "Данные устарели."); return
    
    bounds = weather_logic.extract_bounds(b['title'])
    temp_val = bounds.get("high") if bounds["type"] == "range" else bounds.get("val")
    temp_c = weather_logic.f_to_c(temp_val) if bounds["f"] else temp_val
    b['current_temp_c'] = temp_c
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_bet_markup(bet_id, b.get('shares', 5.0), b['price'], b['current_temp_c']))

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_') or call.data.startswith('sub_'))
def adjust_shares_callback(call):
    action, bet_id = call.data.split('_'); b = bet_cache.get(bet_id)
    if not b: return
    b['shares'] = b['shares'] + 1.0 if action == 'add' else max(1.0, b['shares'] - 1.0)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_bet_markup(bet_id, b['shares'], b['price'], b['current_temp_c']))

@bot.callback_query_handler(func=lambda call: call.data.startswith('t_add_') or call.data.startswith('t_sub_'))
def adjust_temp_callback(call):
    parts = call.data.split('_'); direction = parts[1]; bet_id = parts[2]; b = bet_cache.get(bet_id)
    if not b: return
    
    bot.answer_callback_query(call.id, "Ищу соседний рынок...")
    target_temp = b['current_temp_c'] + (1.0 if direction == 'add' else -1.0)
    
    new_market = weather_logic.get_market_by_temp(b['city'], b['date'], target_temp)
    if new_market:
        new_market['index'] = b['index']; new_market['shares'] = b['shares']; new_market['current_temp_c'] = target_temp
        bet_cache[bet_id] = new_market
        bot.edit_message_text(build_forecast_text(new_market['index'], new_market), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_bet_markup(bet_id, new_market['shares'], new_market['price'], target_temp))
    else:
        bot.answer_callback_query(call.id, "Рынок на эту температуру не найден.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('f_can_'))
def cancel_forecast_bet(call):
    bet_id = call.data.split('_')[2]; b = bet_cache.get(bet_id)
    if not b: return
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Обновить", callback_data=f"ref_{bet_id}"), InlineKeyboardButton("💵 Сделать ставку", callback_data=f"bet_{bet_id}"))
    bot.edit_message_text(build_forecast_text(b['index'], b), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ref_'))
def ref_callback(call):
    bet_id = call.data.split('_')[1]; b = bet_cache.get(bet_id)
    if not b: return
    bot.answer_callback_query(call.id, "Обновляю...")
    try:
        new_b = weather_logic.refresh_bet(b["city"], b["date"])
        if new_b:
            new_b["index"] = b["index"]; new_b["shares"] = b.get("shares", 5.0); bet_cache[bet_id] = new_b
            bot.edit_message_text(build_forecast_text(new_b["index"], new_b), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Обновить", callback_data=f"ref_{bet_id}"), InlineKeyboardButton("💵 Сделать ставку", callback_data=f"bet_{bet_id}")))
    except Exception as e:
        bot.answer_callback_query(call.id, "Данные не изменились." if "not modified" in str(e).lower() else "Ошибка.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('do_'))
def do_bet_callback(call):
    if check_busy(call.message.chat.id): return
    bet_id = call.data.split('_')[1]; b = bet_cache.get(bet_id)
    if not b: release_busy(); return
    limit_price = round(b['price'] + 0.02, 2); shares = b['shares']
    bot.answer_callback_query(call.id, "Отправка ордера...")
    try:
        from curl_cffi import requests; from py_clob_client.utilities import order_to_json; from py_clob_client.clob_types import RequestArgs; from py_clob_client.headers.headers import create_level_2_headers
        client = get_client(); order = client.create_order(OrderArgs(price=limit_price, size=shares, side="BUY", token_id=b['token_id']), PartialCreateOrderOptions(tick_size="0.01"))
        body_dict = order_to_json(order, L1_KEY, OrderType.GTC, False); body_str = json.dumps(body_dict, separators=(",", ":"))
        req_args = RequestArgs(method="POST", request_path="/order", body=body_dict, serialized_body=body_str)
        headers = create_level_2_headers(client.signer, client.creds, req_args); headers.update({"Referer": "https://polymarket.com/", "Origin": "https://polymarket.com", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        resp = requests.post("https://clob.polymarket.com/order", data=body_str, headers=headers, impersonate="chrome110", proxies={}, timeout=30)
        rj = resp.json()
        if rj.get("success") or rj.get("orderID"): bot.send_message(call.message.chat.id, f"🚀 **Ставка на {b['city']} принята!**\n🆔 ID: `{rj.get('orderID')}`\n📈 Кол-во: {shares} шт.\n💵 Сумма: ${round(shares * limit_price, 2)}")
        else: bot.send_message(call.message.chat.id, f"❌ Ошибка биржи: {rj}")
    except Exception as e: bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")
    finally: release_busy()

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and msg.text in ["💼 Ставки", "Активные ставки"])
def active_bets(message):
    if check_busy(message.chat.id): return
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        l_msg = bot.send_message(message.chat.id, "🔄 Пожалуйста, подождите, загружаю список активных позиций и проверяю погоду...")
        from curl_cffi import requests; client = get_client(); orders = client.get_orders()
        resp = requests.get(f"https://data-api.polymarket.com/positions?user={FUNDER_ADDR}", headers={"User-Agent": "Mozilla/5.0"}, impersonate="chrome110", proxies={}, timeout=15)
        if resp.status_code != 200: bot.delete_message(message.chat.id, l_msg.message_id); bot.send_message(message.chat.id, f"❌ Ошибка API: {resp.status_code}"); release_busy(); return
        data = resp.json(); positions = [d for d in data if float(d.get("size", 0)) > 0.1]; redeemables = [d for d in data if d.get("redeemable")]
        if not orders and not positions and not redeemables: bot.delete_message(message.chat.id, l_msg.message_id); bot.send_message(message.chat.id, "У вас нет активных ордеров."); release_busy(); return
        msg_text = ""; active_list = ""; finished_list = ""; pos_cache.clear(); weather_results = {}
        for i, p in enumerate(positions, 1):
            pid = str(uuid.uuid4())[:8]; pos_cache[pid] = p; title = p.get('title', ''); city = None; peak_msk = "14:00-16:00 MSK"
            for c, info in weather_logic.CITIES.items():
                if c in title: city = c; peak_msk = info.get('peak_msk', peak_msk); break
            iso_date = p.get('endDate'); match = re.search(r"be (.*) on", title); bt = match.group(1) if match else ""
            cache_key = f"{city}_{iso_date}_{bt}"
            if cache_key in weather_results: m, cur_t, m2, cur_cc = weather_results[cache_key]
            else:
                m = weather_logic.get_current_margin(city, iso_date, bt); res_w = weather_logic.get_realtime_weather(city, bt)
                cur_t, m2, cur_cc = res_w; weather_results[cache_key] = (m, cur_t, m2, cur_cc)
            # Используем новую функцию расчета риска
            risk_text, _ = weather_logic.get_risk_info(m, cur_cc, 0)
            m2_text = f"\n   📏 Зазор (факт): {m2}°C {'☀️' if cur_cc < 20 else '⛅️'}" if cur_t else ""
            rem_str = get_time_to_peak(iso_date, peak_msk); p['short_label'] = f"{i}. {city[:3].upper() if city else '???' } {re.findall(r'-?\\d+', title)[0] if re.findall(r'-?\\d+', title) else ''}"
            in_val = float(p.get('avgPrice', 0)) * float(p.get('size', 0)); cur_val = float(p.get('currentValue', 0)); diff = cur_val - in_val
            entry = f"*{i}.* {title} | {risk_text} | {m}°C{m2_text}\n   Вход: `${in_val:.2f}` ➔ Тек: `${cur_val:.2f}` {'✅' if diff >= 0 else '❌'} ({diff:+.2f})\n   🕒 Пик: ~{peak_msk}{rem_str}\n"
            if "пик прошел" in rem_str: finished_list += entry
            else: active_list += entry
        if active_list: msg_text += "💼 **Твой портфель (актив):**\n\n" + active_list
        if finished_list: msg_text += "\n⌛️ **Пик пройден (ожидание):**\n\n" + finished_list
        if redeemables: msg_text += "\n💰 **Доступно для клейма:**\n" + "\n".join([f"- {r.get('title')} ({r.get('size')} шт.)" for r in redeemables])
        bot.delete_message(message.chat.id, l_msg.message_id); bot.send_message(message.chat.id, msg_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔥 ЗАКРЫТЬ ПОЗИЦИЮ", callback_data="close_menu")))
    except Exception as e: bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
    finally: release_busy()

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and msg.text in ["🏦 Баланс", "Баланс"])
def show_balance(message):
    try:
        from curl_cffi import requests; proxy_bal = usdc_contract.functions.balanceOf(FUNDER_ADDR).call() / 1e6
        resp = requests.get(f"https://data-api.polymarket.com/positions?user={FUNDER_ADDR}", headers={"User-Agent": "Mozilla/5.0"}, impersonate="chrome110", timeout=10)
        portfolio_val = sum(float(d.get("currentValue", 0)) for d in resp.json() if float(d.get("size", 0)) > 0.1) if resp.status_code == 200 else 0.0
        bot.send_message(message.chat.id, f"📊 **Статистика банка:**\n\n🏦 **Баланс Proxy:** `{proxy_bal:.2f} USDC.e` (Свободно)\n💼 **Портфель:** `{portfolio_val:.2f} USDC.e` (В ставках)\n📈 **ОБЩИЙ БАНК:** `{proxy_bal + portfolio_val:.2f} USDC.e`", parse_mode="Markdown")
    except Exception as e: bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and msg.text in ["💰 Клейм", "Клейм"])
def claim_winnings(message):
    bot.send_message(message.chat.id, "🔄 Запускаю автоматический сбор прибыли (Gnosis Safe)...")
    try:
        import subprocess; env = os.environ.copy(); env["POLYMARKET_PROXY_ADDRESS"] = FUNDER_ADDR
        res_pos = subprocess.run(["polymarket", "-o", "json", "data", "positions", FUNDER_ADDR], capture_output=True, text=True)
        redeemables = [d for d in json.loads(res_pos.stdout) if d.get("redeemable")]
        if not redeemables: bot.send_message(message.chat.id, "💎 Пока клеймить нечего."); return
        for r in redeemables:
            cid = r.get("condition_id"); idx_set = "2" if r.get("outcome_index") == 1 else "1"
            bot.send_message(message.chat.id, f"📦 Клеймлю: {r.get('title')}...")
            subprocess.run(["polymarket", "ctf", "redeem", "--private-key", PK, "--signature-type", "gnosis-safe", "--condition", cid, "--index-sets", idx_set], env=env)
        bot.send_message(message.chat.id, f"✅ Клейм завершен! 💋")
    except Exception as e: bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

if __name__ == "__main__":
    try: bot.send_message(ADMIN_ID, "🚀 **Бот успешно перезапущен и готов!** 💋")
    except: pass
    threading.Thread(target=weather_logic.find_good_bets, daemon=True).start()
    bot.infinity_polling()
