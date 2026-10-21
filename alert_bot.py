import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime

# 텔레그램 설정 (GitHub Secrets에서 자동 로드)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_qqq_indicators():
    try:
        # 야후 파이낸스 QQQ 1년 일봉 데이터 호출
        url = "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=1d&range=1y"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        
        result = data['chart']['result'][0]
        closes = np.array([c for c in result['indicators']['quote'][0]['close'] if c is not None])
        
        if len(closes) < 200:
            return None, None, None, False
            
        price = closes[-1]
        sma200 = np.mean(closes[-200:])
        disp200 = ((price - sma200) / sma200) * 100.0
        
        # 5일 연속 200일선 -3% 이하 체류 여부
        last5 = closes[-5:]
        below_sma5 = all(((p - sma200) / sma200) * 100.0 <= -3.0 for p in last5)
        
        # Wilder's RSI(14) 계산
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:14])
        avg_loss = np.mean(losses[:14])
        for i in range(14, len(deltas)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
            
        rs = avg_gain / (avg_loss if avg_loss != 0 else 1e-10)
        rsi14 = 100.0 - (100.0 / (1.0 + rs))
        
        # Bollinger Band %B (20일, 2표준편차)
        slice_20 = closes[-20:]
        sma20 = np.mean(slice_20)
        std20 = np.std(slice_20)
        upper = sma20 + 2.0 * std20
        lower = sma20 - 2.0 * std20
        bb_pct = ((price - lower) / (upper - lower)) * 100.0 if upper != lower else 50.0
        
        return rsi14, disp200, bb_pct, below_sma5
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None, None, None, False

def evaluate_strategy(rsi, disp, bb, below_sma5):
    s_rsi = np.clip((rsi - 25.0) / 50.0 * 100.0, 0.0, 100.0)
    s_disp = np.clip((disp - (-10.0)) / 30.0 * 100.0, 0.0, 100.0)
    s_bb = np.clip(bb, 0.0, 100.0)
    
    # 최적 가중치: 200일선(51%) + RSI(23%) + 볼린저밴드(26%)
    heat = (0.51 * s_disp) + (0.23 * s_rsi) + (0.26 * s_bb)
    
    raw_lev = ((80.0 - heat) / 60.0) * 100.0
    lev_ratio = int(round(np.clip(raw_lev, 0, 100)))
    gpix_ratio = 100 - lev_ratio
    
    asset_name = "QLD"
    badge = "중립 구간"
    tip = "정기적립 (배당→QLD)"
    
    if disp >= 10.0:
        badge = "고점과열"
        tip = "💡 보유 TQQQ → QLD 환원 권장"
    elif disp <= 0.0:
        asset_name = "TQQQ"
        badge = "200일선이탈"
        tip = "🔥 QLD 대신 TQQQ 100% 매수"
    elif disp <= 2.0 and heat <= 38.0:
        asset_name = "QLD/TQQQ"
        badge = "지지선테스트"
        tip = "⚡ QLD 50% + TQQQ 50% 분할 매수"
    elif heat <= 25.0:
        badge = "극단침체"
        tip = "GPIX 일부→레버리지 전환"
    elif heat >= 75.0:
        badge = "극단과열"
        tip = "GPIX 비중 확대 구간"
        
    if below_sma5 and 30.0 <= rsi < 50.0:
        badge = "방어경보"
        asset_name = "QLD"
        tip = "보유 레버리지 40%→GPIX 대피"
        
    return heat, badge, asset_name, lev_ratio, gpix_ratio, tip

if __name__ == "__main__":
    # GitHub Action 실행 시각 (UTC 기준 또는 입력된 argument 활용 가능)
    run_type = os.environ.get("RUN_TYPE", "정기 알람")
    
    rsi, disp, bb, below_sma5 = get_qqq_indicators()
    if rsi is not None:
        heat, badge, asset, lev, gpix, tip = evaluate_strategy(rsi, disp, bb, below_sma5)
        disp_sign = "+" if disp >= 0 else ""
        
        msg = (
            f"🚨 *[QLD·GPIX+T 매수 시그널] ({run_type})*\n\n"
            f"• 시장 상태: *{badge}* (과열도 {heat:.1f}%)\n\n"
            f"📊 *[실시간 3대 지표]*\n"
            f"- 200일선 이격도: `{disp_sign}{disp:.1f}%`\n"
            f"- 일봉 RSI(14): `{rsi:.1f}`\n"
            f"- 볼린저밴드 %B: `{bb:.0f}%`\n\n"
            f"🎯 *[금월 매수 권장]*\n"
            f"👉 *{asset} {lev}% · GPIX {gpix}%*\n\n"
            f"💡 *행동 지침:*\n{tip}"
        )
        send_telegram(msg)
    else:
        send_telegram("⚠️ QQQ 데이터를 불러오는 데 실패했습니다.")
