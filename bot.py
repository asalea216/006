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

# Binance bağlantısı (otomatik yeniden bağlanma destekli)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'timeout': 30000,
})


def is_trading_hour():
    """Londra ve New York seans saatlerini kontrol eder."""
    now_time = datetime.now()
    hour = now_time.hour
    minute = now_time.minute

    # 1. Londra Aralığı: 10:00 - 13:00
    if 10 <= hour < 13:
        return True

    # 2. New York Aralığı: 15:30 - 21:00
    if hour == 15 and minute >= 30:
        return True
    if 16 <= hour < 21:
        return True

    return False


def send_telegram_msg(text):
    """Telegram'a mesaj gönderir. Başarısız olursa tekrar dener."""
    for attempt in range(3):
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {
                'chat_id': CHAT_ID,
                'text': text,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Telegram mesajı gönderildi.")
                return True
            else:
                logger.warning(f"⚠️ Telegram yanıtı: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Mesaj Hatası (Deneme {attempt+1}/3): {e}")
            time.sleep(2)
    return False


def get_rsi(symbol, timeframe):
    """Belirtilen zaman dilimine göre RSI ve fiyatı hesaplar."""
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi'] = ta.rsi(df['close'], length=14)
    rsi = df['rsi'].iloc[-1]
    price = df['close'].iloc[-1]
    return round(rsi, 2), round(price, 4)


def run_bot():
    """Ana bot döngüsü."""
    logger.info("🚀 SAAT FİLTRELİ SNIPER BOT BAŞLATILDI...")
    
    # Başlangıçta Telegram'a bildirim gönder
    send_telegram_msg(
        f"🤖 <b>Bot Başlatıldı!</b>\n"
        f"📊 Sembol: {SYMBOL}\n"
        f"🕐 Saat: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📡 Sunucu üzerinde çalışıyor..."
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

                logger.info(
                    f"[{current_time_str}] Fiyat: {price} | "
                    f"RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}"
                )

                # GÜÇLÜ ALIŞ SİNYALİ
                if rsi_5m <= LOWER_RSI and rsi_15m <= 35 and last_alert != "oversold":
                    msg = (
                        f"🟢 <b>GÜÇLÜ ALIŞ SİNYALİ!</b>\n"
                        f"💰 Fiyat: <b>{price}</b>\n"
                        f"📉 RSI 5m: {rsi_5m}\n"
                        f"📉 RSI 15m: {rsi_15m}\n"
                        f"⚠️ 15m OB Bölgesini kontrol et!\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "oversold"
                    logger.info("🟢 ALIŞ SİNYALİ GÖNDERİLDİ")

                # GÜÇLÜ SATIŞ SİNYALİ
                elif rsi_5m >= UPPER_RSI and rsi_15m >= 65 and last_alert != "overbought":
                    msg = (
                        f"🔴 <b>GÜÇLÜ SATIŞ SİNYALİ!</b>\n"
                        f"💰 Fiyat: <b>{price}</b>\n"
                        f"📈 RSI 5m: {rsi_5m}\n"
                        f"📈 RSI 15m: {rsi_15m}\n"
                        f"⚠️ 15m OB Bölgesini kontrol et!\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "overbought"
                    logger.info("🔴 SATIŞ SİNYALİ GÖNDERİLDİ")

                # Nötr bölge — alert sıfırla
                elif 45 < rsi_5m < 55:
                    last_alert = ""

            else:
                if datetime.now().second % 30 == 0:
                    logger.info(f"[{current_time_str}] 💤 İşlem saati değil. Beklemede...")

            consecutive_errors = 0  # Başarılı döngüde hata sayacını sıfırla
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
            logger.error(f"⚠️ Beklenmeyen Hata ({consecutive_errors}/{MAX_ERRORS}): {e}")
            time.sleep(10)

        # Çok fazla ardışık hata varsa Telegram'a bildir
        if consecutive_errors >= MAX_ERRORS:
            send_telegram_msg(
                f"🚨 <b>BOT KRİTİK HATA!</b>\n"
                f"{MAX_ERRORS} ardışık hata oluştu.\n"
                f"Bot durabilir, kontrol et!"
            )
            consecutive_errors = 0


if __name__ == "__main__":
    run_bot()
