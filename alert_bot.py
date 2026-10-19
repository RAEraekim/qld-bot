import os
import datetime
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

def get_fear_and_greed():
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{today}"
    ]
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/"
    }
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                score = data.get("fear_and_greed", {}).get("score")
                rating = data.get("fear_and_greed", {}).get("rating", "Normal")
                if score is not None:
                    return round(float(score)), str(rating)
        except Exception:
            pass
    return -1, "Error"

def calculate_wilder_rsi(closes, period=14):
    if not closes or len(closes) <= period:
        return -1.0
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff >= 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def get_yahoo_data(symbol, interval, range_str):
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    headers = {"User-Agent": UA}
    for host in hosts:
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                res = r.json()
                result = res["chart"]["result"][0]
                raw_closes = result["indicators"]["quote"][0].get("close", [])
                closes = [float(c) for c in raw_closes if c is not None]
                meta = result.get("meta", {})
                price = meta.get("regularMarketPrice", closes[-1] if closes else 0.0)
                gmtoffset = int(meta.get("gmtoffset", -14400))
                rsi = calculate_wilder_rsi(closes, 14)
                return rsi, round(float(price), 1), gmtoffset
        except Exception:
            pass
    return -1.0, 0.0, -14400

def get_us_market_info(gmtoffset):
    now_utc = datetime.datetime.utcnow()
    ny_time = now_utc + datetime.timedelta(seconds=gmtoffset)
    ny_day = ny_time.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    ny_total_min = ny_time.hour * 60 + ny_time.minute

    is_dst = (gmtoffset == -14400)
    kr_open = "22:30" if is_dst else "23:30"
    kr_close = "05:00" if is_dst else "06:00"

    pre_open = 240      # 04:00
    reg_open = 570      # 09:30
    reg_close = 960     # 16:00
    after_close = 1200  # 20:00

    is_wkday = (0 <= ny_day <= 4)

    if is_wkday and reg_open <= ny_total_min < reg_close:
        rem = reg_close - ny_total_min
        rh, rm = divmod(rem, 60)
        return f"🟢 미 정규장 진행중 (마감 {rh}시간 {rm}분 전 / {kr_close})"

    if ny_day == 5:
        days_wait = 2
    elif ny_day == 6:
        days_wait = 1
    elif ny_total_min >= reg_close:
        days_wait = 3 if ny_day == 4 else 1
    else:
        days_wait = 0

    min_wait = (days_wait * 1440) - ny_total_min + reg_open
    oh, om = divmod(min_wait, 60)

    if oh >= 24:
        od, rem_h = divmod(oh, 24)
        w_str = f"{od}일 {rem_h}시간 후 ({kr_open} 오픈)"
    else:
        w_str = f"{oh}시간 {om}분 후 ({kr_open} 오픈)"

    if is_wkday and pre_open <= ny_total_min < reg_open:
        return f"🟡 프리마켓 진행중 (정규장 {w_str})"
    if is_wkday and reg_close <= ny_total_min < after_close:
        return f"🟣 애프터마켓 진행중 (다음 정규장 {w_str})"
    return f"⚪ 미국장 휴장 (정규장 {w_str})"

def get_strategy_status(fng, d_rsi, w_rsi):
    is_fear = (fng != -1 and fng <= 25)
    has_d = (d_rsi != -1)

    if is_fear and has_d and d_rsi < 35 and ((w_rsi != -1 and w_rsi < 40) or fng <= 15):
        return (
            "🚨 [Lv.3 패닉 풀베팅 신호 ON]",
            "• 잔여 단기채권(30%) 전액 매도 ➔ QLD(TIGER 나스닥레버리지) 전환"
        )
    if is_fear and has_d and d_rsi < 30:
        return (
            "🔥 [Lv.2 2차 강력 매수 신호 ON]",
            "• 보유 단기채권 40% 매도 ➔ QLD 추가 매수"
        )
    if is_fear and has_d and d_rsi < 35:
        return (
            "⚡ [Lv.1 1차 스위칭 신호 ON]",
            "• 당월 투자금 200만 원 전액 QLD 투입\n• 보유 단기채권 30% 매도 ➔ QLD 전환"
        )
    if fng >= 75 and has_d and d_rsi >= 70:
        return (
            "💰 [과열/익절 신호 (실탄 재장전)]",
            "• QLD 수익분 30~50% 분할 매도 ➔ 단기채권(머니마켓/SGOV) 전환"
        )
    if is_fear or (has_d and d_rsi < 35):
        return (
            "👀 [매수 관심 구간 진입 (대기)]",
            "• 공포지수≤25 & 일봉RSI<35 동시 충족 대기 중 (채권 매도 대기)"
        )
    return (
        "🟢 [신호 OFF - 평상시 적립 구간]",
        "• 월 200만 원 기본 루틴 유지: GPIX 60%(120만) + 단기채권 40%(80만)"
    )

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("TELEGRAM_TOKEN 또는 CHAT_ID가 설정되지 않았습니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg
    }
    r = requests.post(url, json=payload, timeout=10)
    print("Telegram response:", r.status_code, r.text)

def main():
    fng, rating = get_fear_and_greed()
    d_rsi, price, gmtoffset = get_yahoo_data("QQQ", "1d", "6mo")
    w_rsi, _, _ = get_yahoo_data("QQQ", "1wk", "2y")

    mkt_str = get_us_market_info(gmtoffset)
    badge, action = get_strategy_status(fng, d_rsi, w_rsi)

    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    kst_str = kst_now.strftime("%Y-%m-%d %H:%M KST")

    fng_check = "🔥 충족" if (fng != -1 and fng <= 25) else "대기"
    drsi_check = "🔥 충족" if (d_rsi != -1 and d_rsi < 35) else "대기"
    wrsi_check = "🔥 충족" if (w_rsi != -1 and w_rsi < 40) else "대기"

    msg = (
        f"{badge}\n"
        f"🕒 {kst_str} | QQQ ${price}\n"
        f"{mkt_str}\n\n"
        f"📊 [핵심 지표 브리핑]\n"
        f"• CNN 공포·탐욕: {fng} (기준 ≤25 | {fng_check})\n"
        f"• QQQ 일봉 RSI: {d_rsi} (기준 <35/30 | {drsi_check})\n"
        f"• QQQ 주봉 RSI: {w_rsi} (기준 <40 | {wrsi_check})\n\n"
        f"💡 [현재 행동 지침]\n"
        f"{action}"
    )
    print(msg)
    send_telegram(msg)

if __name__ == "__main__":
    main()
