import json
import urllib.request
import re
import time
from datetime import datetime, timedelta, timezone

CITIES = {
    "London": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London", "peak_msk": "18:00 MSK", "icao": "EGLC", "penalty": 0.6},
    "NYC": {"lat": 40.7769, "lon": -73.8740, "tz": "America/New_York", "f": True, "peak_msk": "23:00 MSK", "icao": "KLGA", "penalty": 0.3},
    "Chicago": {"lat": 41.8781, "lon": -87.6298, "tz": "America/Chicago", "f": True, "peak_msk": "00:00 MSK", "icao": "KORD", "penalty": 0.5},
    "Miami": {"lat": 25.7617, "lon": -80.1918, "tz": "America/New_York", "f": True, "peak_msk": "23:00 MSK", "icao": "KMIA", "penalty": 0.0},
    "Sao Paulo": {"lat": -23.5505, "lon": -46.6333, "tz": "America/Sao_Paulo", "peak_msk": "21:00 MSK", "icao": "SBGR", "penalty": 0.3},
    "Buenos Aires": {"lat": -34.6037, "lon": -58.3816, "tz": "America/Argentina/Buenos_Aires", "peak_msk": "21:00 MSK", "icao": "SAEZ", "penalty": 0.0},
    "Dallas": {"lat": 32.7767, "lon": -96.7970, "tz": "America/Chicago", "f": True, "peak_msk": "00:00 MSK", "icao": "KDFW", "penalty": 0.5},
    "Paris": {"lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris", "peak_msk": "17:00 MSK", "icao": "LFPG", "penalty": 0.3},
    "Seoul": {"lat": 37.5665, "lon": 126.9780, "tz": "Asia/Seoul", "peak_msk": "09:00 MSK", "icao": "RKSI", "penalty": 0.3},
    "Toronto": {"lat": 43.6510, "lon": -79.3470, "tz": "America/Toronto", "peak_msk": "23:00 MSK", "icao": "CYYZ", "penalty": 0.0},
    "Seattle": {"lat": 47.6062, "lon": -122.3321, "tz": "America/Los_Angeles", "f": True, "peak_msk": "02:00 MSK", "icao": "KSEA", "penalty": 0.0},
    "Ankara": {"lat": 39.9334, "lon": 32.8597, "tz": "Europe/Istanbul", "peak_msk": "15:00 MSK", "icao": "LTAC", "penalty": 0.5},
    "Sydney": {"lat": -33.8688, "lon": 151.2093, "tz": "Australia/Sydney", "peak_msk": "07:00 MSK", "icao": "YSSY", "penalty": 0.7},
    "Wellington": {"lat": -41.2865, "lon": 174.7762, "tz": "Pacific/Auckland", "peak_msk": "05:00 MSK", "icao": "NZWN", "penalty": 0.7},
    "Boston": {"lat": 42.3601, "lon": -71.0589, "tz": "America/New_York", "f": True, "peak_msk": "23:00 MSK", "icao": "KBOS", "penalty": 0.7}
}

MODEL_WEIGHTS = {"gem_seamless": 0.45, "icon_seamless": 0.30, "gfs_seamless": 0.15, "jma_seamless": 0.10}

def f_to_c(f): return round((f - 32) * 5.0/9.0, 1)

forecast_cache = {}

def fetch_open_meteo(lat, lon, tz):
    cache_key = f"{lat}_{lon}_{tz}"
    if cache_key in forecast_cache:
        cached_data, timestamp = forecast_cache[cache_key]
        if time.time() - timestamp < 300: return cached_data
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,cloud_cover_max&hourly=cloud_cover&timezone={tz.replace('/', '%2F')}&models=icon_seamless,gem_seamless,jma_seamless,gfs_seamless"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode()); forecast_cache[cache_key] = (data, time.time()); return data
    except: return None

def fetch_polymarket_events(city, date_str):
    slug_city = city.lower().replace(" ", "-")
    url = f"https://gamma-api.polymarket.com/events?slug=highest-temperature-in-{slug_city}-on-{date_str}-2026"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data[0].get("markets", []) if data else []
    except: return []

def extract_bounds(title):
    is_f = "°F" in title; is_higher = "higher" in title.lower(); is_below = "below" in title.lower()
    # Remove metadata that could contain numbers (dates/years)
    cleaned = re.sub(r'202[56]', '', title)
    cleaned = re.sub(r'on [A-Z][a-z]+ \d+', '', cleaned)
    
    nums = re.findall(r'-?\d+', cleaned)
    if not nums: return None
    nums = [int(n) for n in nums]
    
    if len(nums) >= 2: return {"type": "range", "low": nums[0], "high": nums[1], "f": is_f}
    elif is_higher: return {"type": "higher", "val": nums[0], "f": is_f}
    elif is_below: return {"type": "below", "val": nums[0], "f": is_f}
    else: return {"type": "exact", "val": nums[0], "f": is_f}

def calculate_margin(bounds, c_val):
    if bounds["type"] == "range":
        low_c = f_to_c(bounds["low"]) if bounds["f"] else bounds["low"]
        high_c = f_to_c(bounds["high"]) if bounds["f"] else bounds["high"]
        if low_c <= c_val <= high_c: return -min(c_val - low_c, high_c - c_val)
        else: return min(abs(c_val - low_c), abs(c_val - high_c))
    elif bounds["type"] == "exact":
        val_c = f_to_c(bounds["val"]) if bounds["f"] else bounds["val"]
        # Для NO на точную цифру маржа — это расстояние до этой цифры.
        # Если прогноз 24, а рынок на 27, то маржа 3 градуса (мы далеко от опасной точки).
        return abs(c_val - val_c)
    elif bounds["type"] == "higher":
        # Рынок: NO на "21 or higher" (т.е. мы ставим на то, что будет НИЖЕ 21)
        val_c = f_to_c(bounds["val"]) if bounds["f"] else bounds["val"]
        # Если прогноз 18, а граница 21, маржа = 21 - 18 = 3 градуса (запас вниз).
        return val_c - c_val
    elif bounds["type"] == "below":
        # Рынок: NO на "25 or below" (т.е. мы ставим на то, что будет ВЫШЕ 25)
        val_c = f_to_c(bounds["val"]) if bounds["f"] else bounds["val"]
        # Если прогноз 28, а граница 25, маржа = 28 - 25 = 3 градуса (запас вверх).
        return c_val - val_c
    return 0

def get_risk_info(margin, cloud_cover, consensus_c):
    """
    Рассчитывает уровень риска и возвращает его вместе с эмодзи.
    """
    # Штраф за ясное небо (если облачность < 10%, риск перегрева +0.5 градуса)
    effective_margin = margin - (0.5 if cloud_cover <= 10 else 0)
    
    if effective_margin >= 2.5: risk_label = "БЕТОН"; risk_emoji = "🛡"
    elif effective_margin >= 1.5: risk_label = "БЕЗОПАСНО"; risk_emoji = "🟢"
    elif effective_margin >= 0.8: risk_label = "РИСКОВАННО"; risk_emoji = "🟡"
    elif effective_margin >= 0.4: risk_label = "ОПАСНО"; risk_emoji = "🔥"
    else: risk_label = "АХТУНГ"; risk_emoji = "💀"
    
    return f"{risk_emoji} {risk_label}", effective_margin

def convert_title_to_c(title):
    if "°F" not in title: return title
    def repl(match): return f"{f_to_c(int(match.group(0)))}°C"
    return re.sub(r'-?\\d+', repl, title).replace("°F", "")

def get_weighted_consensus(daily_data, idx):
    total_weight = 0; weighted_sum = 0
    for model, weight in MODEL_WEIGHTS.items():
        k = f"temperature_2m_max_{model}"
        if k in daily_data and daily_data[k][idx] is not None: weighted_sum += daily_data[k][idx] * weight; total_weight += weight
    return weighted_sum / total_weight if total_weight > 0 else None

def find_good_bets():
    now = datetime.now(timezone.utc); all_candidates = []
    dates = [now.strftime("%B-%-d").lower(), (now + timedelta(days=1)).strftime("%B-%-d").lower()]
    iso_dates = [now.strftime("%Y-%m-%d"), (now + timedelta(days=1)).strftime("%Y-%m-%d")]
    for city, geo in CITIES.items():
        meteo = fetch_open_meteo(geo["lat"], geo["lon"], geo["tz"])
        if not meteo: continue
        for d_idx, d_str in enumerate(dates):
            iso_d = iso_dates[d_idx]
            if iso_d not in meteo["daily"]["time"]: continue
            idx = meteo["daily"]["time"].index(iso_d)
            
            # Weighted cloud cover from models
            cloud_total = 0; cloud_weight = 0
            for m_name, weight in MODEL_WEIGHTS.items():
                k = f"cloud_cover_max_{m_name}"
                if k in meteo["daily"] and meteo["daily"][k][idx] is not None:
                    cloud_total += meteo["daily"][k][idx] * weight
                    cloud_weight += weight
            cloud_max = round(cloud_total / cloud_weight) if cloud_weight > 0 else 0

            cloud_at_peak = 0
            if "hourly" in meteo:
                try: 
                    h_idx = meteo["hourly"]["time"].index(f"{iso_d}T15:00")
                    h_total = 0; h_weight = 0
                    for m_name, weight in MODEL_WEIGHTS.items():
                        k = f"cloud_cover_{m_name}"
                        if k in meteo["hourly"] and meteo["hourly"][k][h_idx] is not None:
                            h_total += meteo["hourly"][k][h_idx] * weight
                            h_weight += weight
                    cloud_at_peak = round(h_total / h_weight) if h_weight > 0 else cloud_max
                except: cloud_at_peak = cloud_max
                
            consensus = get_weighted_consensus(meteo["daily"], idx)
            if consensus is None: continue
            model_vals = [meteo["daily"].get(f"temperature_2m_max_{m}", [None]*10)[idx] or "N/A" for m in ["icon_seamless", "gem_seamless", "jma_seamless", "gfs_seamless"]]
            models_str = f"(ICON: {model_vals[0]}, GEM: {model_vals[1]}, JMA: {model_vals[2]}, GFS: {model_vals[3]} °C)"
            markets = fetch_polymarket_events(city, d_str)
            for m in markets:
                try:
                    p_no = float(json.loads(m.get("outcomePrices", "[]"))[1])
                    bounds = extract_bounds(m["groupItemTitle"])
                    if not bounds or not (0.05 <= p_no <= 0.87): continue
                    margin = calculate_margin(bounds, consensus)
                    effective_margin = round(margin - (0.5 if cloud_at_peak <= 10 else 0) - geo.get("penalty", 0), 2)
                    if margin >= 0.5: all_candidates.append({"city": city, "date": iso_d, "title": m["groupItemTitle"], "display_title": convert_title_to_c(m["groupItemTitle"]), "coeff": round(1 / p_no, 2), "margin": effective_margin, "raw_margin": round(margin, 2), "cloud_cover": cloud_at_peak, "price": p_no, "token_id": json.loads(m["clobTokenIds"])[1], "market_id": m["conditionId"], "models_str": models_str, "peak_msk": geo["peak_msk"], "consensus_c": round(consensus, 2)})
                except: pass
    
    final_results = []
    by_city = {}
    for c in all_candidates:
        if c["city"] not in by_city: by_city[c["city"]] = []
        by_city[c["city"]].append(c)
    for city, candidates in by_city.items():
        safe = [c for c in candidates if c["margin"] >= 1.5]
        red = sorted([c for c in candidates if 1.0 <= c["margin"] < 1.5], key=lambda x: x["margin"], reverse=True)
        if safe: final_results.extend(safe)
        elif red: final_results.append(red[0])
    final_results.sort(key=lambda x: x["margin"])
    return final_results

def get_market_by_temp(city, iso_date, target_temp_c):
    geo = CITIES.get(city)
    if not geo: return None
    dt = datetime.strptime(iso_date, "%Y-%m-%d"); date_str = dt.strftime("%B-%-d").lower()
    meteo = fetch_open_meteo(geo["lat"], geo["lon"], geo["tz"])
    if not meteo: return None
    idx = meteo["daily"]["time"].index(iso_date); consensus = get_weighted_consensus(meteo["daily"], idx)
    cloud_penalty = 0.5 if (meteo["daily"].get("cloud_cover_max") and meteo["daily"]["cloud_cover_max"][idx] is not None and meteo["daily"]["cloud_cover_max"][idx] <= 10) else 0.0
    cloud_at_peak = 0
    if "hourly" in meteo and "cloud_cover" in meteo["hourly"]:
        try: h_idx = meteo["hourly"]["time"].index(f"{iso_date}T15:00"); cloud_at_peak = meteo["hourly"]["cloud_cover"][h_idx]
        except: cloud_at_peak = meteo["daily"]["cloud_cover_max"][idx] if "cloud_cover_max" in meteo["daily"] else 0
    markets = fetch_polymarket_events(city, date_str)
    for m in markets:
        bounds = extract_bounds(m["groupItemTitle"])
        if not bounds: continue
        m_temp = bounds.get("high") if bounds["type"] == "range" else bounds.get("val")
        m_temp_c = f_to_c(m_temp) if bounds["f"] else m_temp
        if abs(m_temp_c - target_temp_c) < 0.1: 
            p_no = float(json.loads(m.get("outcomePrices", "[]"))[1])
            margin = calculate_margin(bounds, consensus); effective_margin = round(margin - cloud_penalty - geo.get("penalty", 0), 2)
            model_vals = [meteo["daily"].get(f"temperature_2m_max_{m}", [None]*10)[idx] or "N/A" for m in ["icon_seamless", "gem_seamless", "jma_seamless", "gfs_seamless"]]
            models_str = f"(ICON: {model_vals[0]}, GEM: {model_vals[1]}, JMA: {model_vals[2]}, GFS: {model_vals[3]} °C)"
            return {"city": city, "date": iso_date, "title": m["groupItemTitle"], "display_title": convert_title_to_c(m["groupItemTitle"]), "coeff": round(1 / p_no, 2) if p_no > 0 else 0, "margin": effective_margin, "raw_margin": round(margin, 2), "cloud_penalty": cloud_penalty, "cloud_cover": cloud_at_peak, "price": p_no, "token_id": json.loads(m["clobTokenIds"])[1], "market_id": m["conditionId"], "models_str": models_str, "peak_msk": geo["peak_msk"], "consensus_c": round(consensus, 2)}
    return None

def get_current_margin(city, iso_date, bounds_title):
    geo = CITIES.get(city)
    if not geo: return None
    meteo = fetch_open_meteo(geo["lat"], geo["lon"], geo["tz"])
    if not meteo or iso_date not in meteo["daily"]["time"]: return None
    idx = meteo["daily"]["time"].index(iso_date); cloud_penalty = 0.5 if (meteo["daily"].get("cloud_cover_max") and meteo["daily"]["cloud_cover_max"][idx] is not None and meteo["daily"]["cloud_cover_max"][idx] <= 10) else 0.0
    consensus = get_weighted_consensus(meteo["daily"], idx)
    if consensus is None: return None
    bounds = extract_bounds(bounds_title)
    if not bounds: return None
    return round(calculate_margin(bounds, consensus) - cloud_penalty - geo.get("penalty", 0), 2)

def get_realtime_weather(city, bounds_title):
    geo = CITIES.get(city)
    if not geo: return None, None, None
    icao = geo.get("icao")
    if icao:
        try:
            url = f"https://wttr.in/{icao}?format=j1"
            data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=5).read().decode())
            cur_temp = float(data["current_condition"][0]["temp_C"]); cur_cloud = float(data["current_condition"][0]["cloudcover"]); bounds = extract_bounds(bounds_title)
            if not bounds: return cur_temp, None, cur_cloud
            return cur_temp, round(calculate_margin(bounds, cur_temp) - geo.get("penalty", 0), 2), cur_cloud
        except: pass
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={geo['lat']}&longitude={geo['lon']}&current=temperature_2m,cloud_cover&timezone={geo['tz'].replace('/', '%2F')}"
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=5).read().decode())
        cur_temp = data["current"]["temperature_2m"]; cur_cloud = data["current"]["cloud_cover"]; bounds = extract_bounds(bounds_title)
        if not bounds: return cur_temp, None, cur_cloud
        return cur_temp, round(calculate_margin(bounds, cur_temp) - geo.get("penalty", 0), 2), cur_cloud
    except: return None, None, None
