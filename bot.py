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

CHECK_INTERVAL = 5  # saniye

exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'timeout': 30000,
})


def is_trading_hour():
    now = datetime.now()
    h, m = now.hour, now.minute
    if 10 <= h < 13:
        return True
    if h == 15 and m >= 30:
        return True
    if 16 <= h < 21:
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
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi']   = ta.rsi(df['close'], length=14)
    df['ema9']  = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['ema10'] = ta.ema(df['close'], length=10)
    df['ema50'] = ta.ema(df['close'], length=50)
    return df


def analyze(df_1m, df_5m):
    price   = round(df_1m['close'].iloc[-1], 2)
    rsi_1m  = round(df_1m['rsi'].iloc[-1], 2)
    ema9    = round(df_1m['ema9'].iloc[-1], 2)
    ema21   = round(df_1m['ema21'].iloc[-1], 2)
    rsi_5m  = round(df_5m['rsi'].iloc[-1], 2)
    ema10   = round(df_5m['ema10'].iloc[-1], 2)
    ema50   = round(df_5m['ema50'].iloc[-1], 2)

    fast_bull = rsi_1m <= 40 and ema9 > ema21
    fast_bear = rsi_1m >= 60 and ema9 < ema21
    slow_bull = rsi_5m <= 45 and ema10 > ema50
    slow_bear = rsi_5m >= 55 and ema10 < ema50

    if fast_bull and slow_bull:
        return "BUY", "GÜÇLÜ", price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50
    elif fast_bear and slow_bear:
        return "SELL", "GÜÇLÜ", price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50
    elif fast_bull:
        return "BUY", "ZAYIF", price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50
    elif fast_bear:
        return "SELL", "ZAYIF", price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50
    else:
        return None, None, price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50


def build_msg(direction, strength, price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50, current_time_str, upgraded=False):
    if direction == "BUY":
        emoji = "🟢🟢" if strength == "GÜÇLÜ" else "🟡"
        label = "ALIŞ"
    else:
        emoji = "🔴🔴" if strength == "GÜÇLÜ" else "🟠"
        label = "SATIŞ"

    upgrade_line = "\n⬆️ <b>Zayıf → Güçlü sinyale yükseldi!</b>" if upgraded else ""

    return (
        f"{emoji} <b>{strength} {label} SİNYALİ — XAU/USD</b>{upgrade_line}\n"
        f"💰 PAXG Fiyat: <b>{price}</b>\n\n"
        f"⚡ <b>Hızlı Sistem (1m)</b>\n"
        f"RSI 1m: {rsi_1m} | EMA9: {ema9} | EMA21: {ema21}\n\n"
        f"🐢 <b>Yavaş Sistem (5m)</b>\n"
        f"RSI 5m: {rsi_5m} | EMA10: {ema10} | EMA50: {ema50}\n\n"
        f"🎯 TP: +10/20$ | SL: -5$\n"
        f"🕐 {current_time_str}"
    )


def run_bot():
    logger.info("🚀 XAU/USD ÇIFT SİSTEM BOT BAŞLATILDI")
    send_telegram_msg(
        f"🤖 <b>XAU Çift Sistem Bot Başlatıldı!</b>\n"
        f"📊 PAXG/USDT → XAU/USD sinyali\n"
        f"⚡ Hızlı: 1m RSI + EMA 9/21\n"
        f"🐢 Yavaş: 5m RSI + EMA 10/50\n"
        f"💪 İkisi uyuşursa → GÜÇLÜ sinyal\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )

    # last_alert: None, "buy_zayıf", "buy_güçlü", "sell_zayıf", "sell_güçlü"
    last_alert = None
    consecutive_errors = 0
    MAX_ERRORS = 10

    while True:
        try:
            current_time_str = datetime.now().strftime('%H:%M:%S')

            if is_trading_hour():
                df_1m = get_data(SYMBOL, '1m')
                df_5m = get_data(SYMBOL, '5m')

                signal, strength, price, rsi_1m, rsi_5m, ema9, ema21, ema10, ema50 = analyze(df_1m, df_5m)

                logger.info(
                    f"[{current_time_str}] Fiyat: {price} | "
                    f"RSI 1m: {rsi_1m} | RSI 5m: {rsi_5m} | "
                    f"Sinyal: {signal} ({strength})"
                )

                if signal:
                    alert_key = f"{signal.lower()}_{strength.lower()}"

                    # Zayıf sinyal → henüz bu yönde hiç sinyal yoksa gönder
                    # Güçlü sinyal → zayıf gönderilmiş olsa bile gönder
                    upgraded = (
                        signal == "BUY" and last_alert == "buy_zayıf" and strength == "GÜÇLÜ"
                        or
                        signal == "SELL" and last_alert == "sell_zayıf" and strength == "GÜÇLÜ"
                    )

                    should_send = (
                        last_alert != alert_key and (
                            last_alert is None or
                            upgraded or
                            not last_alert.startswith(signal.lower())
                        )
                    )

                    if should_send:
                        msg = build_msg(signal, strength, price, rsi_1m, rsi_5m,
                                        ema9, ema21, ema10, ema50, current_time_str, upgraded)
                        send_telegram_msg(msg)
                        last_alert = alert_key

                elif signal is None and 48 < rsi_1m < 52:
                    last_alert = None

            else:
                if datetime.now().second % 30 == 0:
                    logger.info(f"[{current_time_str}] 💤 İşlem saati değil.")

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
