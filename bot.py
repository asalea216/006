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

# PARAMETRELER
UPPER_RSI = 70
LOWER_RSI = 30
CHECK_INTERVAL = 10  # saniye

# KuCoin bağlantısı (coğrafi kısıtlama yok, ABD sunucusundan erişilebilir)
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'timeout': 30000,
})


def is_trading_hour():
    now_time = datetime.now()
    hour = now_time.hour
    minute = now_time.minute
    if 10 <= hour < 13:
        return True
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


def get_rsi(symbol, timeframe):
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi'] = ta.rsi(df['close'], length=14)
    return round(df['rsi'].iloc[-1], 2), round(df['close'].iloc[-1], 4)


def run_bot():
    logger.info("🚀 SAAT FİLTRELİ SNIPER BOT BAŞLATILDI...")
    send_telegram_msg(
        f"🤖 <b>Bot Başlatıldı!</b>\n"
        f"📊 Sembol: {SYMBOL}\n"
        f"🕐 Saat: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📡 Sunucu üzerinde çalışıyor... (KuCoin)"
    )

    last_alert = ""
    consecutive_errors = 0
    MAX_ERRORS = 10

    while True:
        try:
            current_time_str = datetime.now().strftime('%H:%M:%S')

            if is_trading_hour():
                rsi_5m, price = get_rsi(SYMBOL, '5m')
                rsi_15m, _ = get_rsi(SYMBOL, '15m')
                logger.info(f"[{current_time_str}] Fiyat: {price} | RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}")

                if rsi_5m <= LOWER_RSI and rsi_15m <= 35 and last_alert != "oversold":
                    msg = (f"🟢 <b>GÜÇLÜ ALIŞ SİNYALİ!</b>\n💰 Fiyat: <b>{price}</b>\n"
                           f"📉 RSI 5m: {rsi_5m}\n📉 RSI 15m: {rsi_15m}\n"
                           f"⚠️ 15m OB Bölgesini kontrol et!\n🕐 {current_time_str}")
                    send_telegram_msg(msg)
                    last_alert = "oversold"

                elif rsi_5m >= UPPER_RSI and rsi_15m >= 65 and last_alert != "overbought":
                    msg = (f"🔴 <b>GÜÇLÜ SATIŞ SİNYALİ!</b>\n💰 Fiyat: <b>{price}</b>\n"
                           f"📈 RSI 5m: {rsi_5m}\n📈 RSI 15m: {rsi_15m}\n"
                           f"⚠️ 15m OB Bölgesini kontrol et!\n🕐 {current_time_str}")
                    send_telegram_msg(msg)
                    last_alert = "overbought"

                elif 45 < rsi_5m < 55:
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
