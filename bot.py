import ccxt
import pandas_ta as ta
import pandas as pd
import time
import requests
import logging
from datetime import datetime

# --- LOGGING AYARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- BİLGİLERİN ---
TOKEN = "8607888019:AAH_9KT13bI_K3JjdSi52o_DTNxL2nWkRKc"
CHAT_ID = "6220442563"
SYMBOL = 'PAXG/USDT'

# SCALP PARAMETRELERİ
UPPER_RSI = 60   # Aşırı alım (scalp için gevşek)
LOWER_RSI = 40   # Aşırı satım (scalp için gevşek)
CHECK_INTERVAL = 5  # saniye

# KuCoin bağlantısı
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'timeout': 30000,
})


def is_trading_hour():
    now_time = datetime.now()
    hour = now_time.hour
    minute = now_time.minute
    # Londra: 10:00 - 13:00
    if 10 <= hour < 13:
        return True
    # New York: 15:30 - 21:00
    if hour == 15 and minute >= 30:
        return True
    if 16 <= hour < 21:
        return True
    return False


def send_telegram_msg(text):
    for attempt in range(3):
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Telegram mesajı gönderildi.")
                return True
        except Exception as e:
            logger.error(f"❌ Mesaj Hatası (Deneme {attempt+1}/3): {e}")
            time.sleep(2)
    return False


def get_data(symbol, timeframe, limit=250):
    """OHLCV verisi çek, RSI + EMA 9/21 hesapla."""
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    return df


def get_trend(df):
    """EMA 9/21'e göre trend yönü."""
    price = df['close'].iloc[-1]
    ema9 = df['ema9'].iloc[-1]
    ema21 = df['ema21'].iloc[-1]
    if ema9 > ema21 and price > ema9:
        return "📈 Yukarı", True, False
    elif ema9 < ema21 and price < ema9:
        return "📉 Aşağı", False, True
    else:
        return "➡️ Yatay", False, False


def run_bot():
    logger.info("🚀 XAU/USD SCALP BOT BAŞLATILDI (PAXG RSI)")
    send_telegram_msg(
        f"🤖 <b>XAU Scalp Bot Başlatıldı!</b>\n"
        f"📊 PAXG/USDT → XAU/USD sinyali\n"
        f"⏱ Timeframe: 1m + 3m\n"
        f"📈 RSI 40/60 | EMA 9/21\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )

    last_alert = ""
    consecutive_errors = 0
    MAX_ERRORS = 10

    while True:
        try:
            current_time_str = datetime.now().strftime('%H:%M:%S')

            if is_trading_hour():
                # 1m ve 3m veri çek
                df_1m = get_data(SYMBOL, '1m')
                df_3m = get_data(SYMBOL, '3m')

                rsi_1m = round(df_1m['rsi'].iloc[-1], 2)
                rsi_3m = round(df_3m['rsi'].iloc[-1], 2)
                price = round(df_1m['close'].iloc[-1], 2)
                ema9 = round(df_1m['ema9'].iloc[-1], 2)
                ema21 = round(df_1m['ema21'].iloc[-1], 2)

                trend_label, trend_up, trend_down = get_trend(df_1m)

                logger.info(
                    f"[{current_time_str}] Fiyat: {price} | "
                    f"RSI 1m: {rsi_1m} | RSI 3m: {rsi_3m} | {trend_label}"
                )

                # ALIŞ SİNYALİ — RSI aşırı satım + trend yukarı
                if rsi_1m <= LOWER_RSI and rsi_3m <= 45 and last_alert != "oversold":
                    ema_note = "✅ EMA trend destekliyor!" if trend_up else "⚠️ Trende karşı, dikkatli ol!"
                    msg = (
                        f"🟢 <b>XAU/USD ALIŞ SİNYALİ</b>\n"
                        f"💰 PAXG Fiyat: <b>{price}</b>\n"
                        f"📉 RSI 1m: {rsi_1m} | RSI 3m: {rsi_3m}\n"
                        f"📊 EMA9: {ema9} | EMA21: {ema21}\n"
                        f"{trend_label}\n"
                        f"{ema_note}\n"
                        f"🎯 TP: +10/20$ | SL: -5$\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "oversold"

                # SATIŞ SİNYALİ — RSI aşırı alım + trend aşağı
                elif rsi_1m >= UPPER_RSI and rsi_3m >= 55 and last_alert != "overbought":
                    ema_note = "✅ EMA trend destekliyor!" if trend_down else "⚠️ Trende karşı, dikkatli ol!"
                    msg = (
                        f"🔴 <b>XAU/USD SATIŞ SİNYALİ</b>\n"
                        f"💰 PAXG Fiyat: <b>{price}</b>\n"
                        f"📈 RSI 1m: {rsi_1m} | RSI 3m: {rsi_3m}\n"
                        f"📊 EMA9: {ema9} | EMA21: {ema21}\n"
                        f"{trend_label}\n"
                        f"{ema_note}\n"
                        f"🎯 TP: +10/20$ | SL: -5$\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "overbought"

                # Nötr bölge — sıfırla
                elif 48 < rsi_1m < 52:
                    last_alert = ""

            else:
                if datetime.now().second % 30 == 0:
                    logger.info(f"[{current_time_str}] 💤 İşlem saati değil. Beklemede...")

            consecutive_errors = 0
            time.sleep(CHECK_INTERVAL)

        except ccxt.NetworkError as e:
            consecutive_errors += 1
            logger.error(f"🌐 Ağ Hatası ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(30)
        except ccxt.ExchangeError as e:
            consecutive_errors += 1
            logger.error(f"🏦 Borsa Hatası ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(60)
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"⚠️ Hata ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(10)

        if consecutive_errors >= MAX_ERRORS:
            send_telegram_msg(f"🚨 <b>BOT KRİTİK HATA!</b>\n{MAX_ERRORS} ardışık hata oluştu!")
            consecutive_errors = 0


if __name__ == "__main__":
    run_bot()
