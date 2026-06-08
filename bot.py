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

CHECK_INTERVAL = 10  # saniye

exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'timeout': 30000,
})


def is_trading_hour():
    h = datetime.now().hour
    return 8 <= h <= 23


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


def get_data(symbol, timeframe, limit=500):
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df


def calculate_vwap(df):
    """Günlük VWAP hesapla — gün başından itibaren."""
    df = df.copy()
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
    today = df['date'].iloc[-1]
    today_df = df[df['date'] == today].copy()

    if len(today_df) < 2:
        return None

    today_df['tp'] = (today_df['high'] + today_df['low'] + today_df['close']) / 3
    today_df['tpv'] = today_df['tp'] * today_df['volume']
    vwap = today_df['tpv'].cumsum() / today_df['volume'].cumsum()
    return round(vwap.iloc[-1], 2)


def run_bot():
    logger.info("🚀 XAU/USD VWAP + RSI BOT BAŞLATILDI")
    send_telegram_msg(
        f"🤖 <b>XAU VWAP + RSI Bot Başlatıldı!</b>\n"
        f"📊 PAXG/USDT → XAU/USD sinyali\n"
        f"⏱ Timeframe: 5m + 15m\n"
        f"📈 RSI 30/70 + VWAP filtresi\n"
        f"🕐 Aktif: 08:00 - 23:59\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )

    last_alert = None  # "buy_rsi", "buy_vwap", "sell_rsi", "sell_vwap"
    consecutive_errors = 0
    MAX_ERRORS = 10

    while True:
        try:
            current_time_str = datetime.now().strftime('%H:%M:%S')

            if is_trading_hour():
                df_5m  = get_data(SYMBOL, '5m',  limit=500)
                df_15m = get_data(SYMBOL, '15m', limit=200)

                rsi_5m  = round(df_5m['rsi'].iloc[-1], 2)
                rsi_15m = round(df_15m['rsi'].iloc[-1], 2)
                price   = round(df_5m['close'].iloc[-1], 2)
                vwap    = calculate_vwap(df_5m)

                vwap_bull = vwap and price < vwap   # fiyat VWAP altında → alış bölgesi
                vwap_bear = vwap and price > vwap   # fiyat VWAP üstünde → satış bölgesi
                confirm_15m_bull = rsi_15m <= 35
                confirm_15m_bear = rsi_15m >= 65

                logger.info(
                    f"[{current_time_str}] Fiyat: {price} | VWAP: {vwap} | "
                    f"RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}"
                )

                # --- ALIŞ ---
                if rsi_5m <= 30:
                    if vwap_bull and confirm_15m_bull and last_alert != "buy_vwap":
                        # GÜÇLÜ: RSI + 15m teyit + VWAP uyumlu
                        msg = (
                            f"🟢🟢 <b>GÜÇLÜ ALIŞ SİNYALİ — XAU/USD</b>\n"
                            f"💰 PAXG Fiyat: <b>{price}</b>\n"
                            f"📊 VWAP: {vwap} — Fiyat VWAP <b>altında</b> ✅\n"
                            f"📉 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                            f"💪 Tüm koşullar uyumlu!\n"
                            f"🎯 TP: +10/20$ | SL: -5$\n"
                            f"🕐 {current_time_str}"
                        )
                        send_telegram_msg(msg)
                        last_alert = "buy_vwap"

                    elif last_alert not in ("buy_rsi", "buy_vwap"):
                        # ZAYIF: Sadece RSI sinyali
                        vwap_note = f"⚠️ VWAP: {vwap} — Fiyat VWAP üstünde, dikkatli ol!" if vwap_bear else f"📊 VWAP: {vwap}"
                        msg = (
                            f"🟡 <b>RSI ALIŞ SİNYALİ — XAU/USD</b>\n"
                            f"💰 PAXG Fiyat: <b>{price}</b>\n"
                            f"{vwap_note}\n"
                            f"📉 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                            f"⚠️ VWAP teyidi yok, dikkatli gir!\n"
                            f"🎯 TP: +10/20$ | SL: -5$\n"
                            f"🕐 {current_time_str}"
                        )
                        send_telegram_msg(msg)
                        last_alert = "buy_rsi"

                # --- SATIŞ ---
                elif rsi_5m >= 70:
                    if vwap_bear and confirm_15m_bear and last_alert != "sell_vwap":
                        # GÜÇLÜ: RSI + 15m teyit + VWAP uyumlu
                        msg = (
                            f"🔴🔴 <b>GÜÇLÜ SATIŞ SİNYALİ — XAU/USD</b>\n"
                            f"💰 PAXG Fiyat: <b>{price}</b>\n"
                            f"📊 VWAP: {vwap} — Fiyat VWAP <b>üstünde</b> ✅\n"
                            f"📈 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                            f"💪 Tüm koşullar uyumlu!\n"
                            f"🎯 TP: +10/20$ | SL: -5$\n"
                            f"🕐 {current_time_str}"
                        )
                        send_telegram_msg(msg)
                        last_alert = "sell_vwap"

                    elif last_alert not in ("sell_rsi", "sell_vwap"):
                        # ZAYIF: Sadece RSI sinyali
                        vwap_note = f"⚠️ VWAP: {vwap} — Fiyat VWAP altında, dikkatli ol!" if vwap_bull else f"📊 VWAP: {vwap}"
                        msg = (
                            f"🟠 <b>RSI SATIŞ SİNYALİ — XAU/USD</b>\n"
                            f"💰 PAXG Fiyat: <b>{price}</b>\n"
                            f"{vwap_note}\n"
                            f"📈 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                            f"⚠️ VWAP teyidi yok, dikkatli gir!\n"
                            f"🎯 TP: +10/20$ | SL: -5$\n"
                            f"🕐 {current_time_str}"
                        )
                        send_telegram_msg(msg)
                        last_alert = "sell_rsi"

                # RSI sinyalden sonra VWAP da uydu → güçlüye yükselt
                elif last_alert == "buy_rsi" and vwap_bull and confirm_15m_bull:
                    msg = (
                        f"🟢🟢 <b>GÜÇLÜ ALIŞ — VWAP Teyidi Geldi!</b>\n"
                        f"💰 PAXG Fiyat: <b>{price}</b>\n"
                        f"📊 VWAP: {vwap} — Fiyat VWAP <b>altında</b> ✅\n"
                        f"📉 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                        f"⬆️ RSI sinyali VWAP ile güçlendi!\n"
                        f"🎯 TP: +10/20$ | SL: -5$\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "buy_vwap"

                elif last_alert == "sell_rsi" and vwap_bear and confirm_15m_bear:
                    msg = (
                        f"🔴🔴 <b>GÜÇLÜ SATIŞ — VWAP Teyidi Geldi!</b>\n"
                        f"💰 PAXG Fiyat: <b>{price}</b>\n"
                        f"📊 VWAP: {vwap} — Fiyat VWAP <b>üstünde</b> ✅\n"
                        f"📈 RSI 5m: {rsi_5m} | RSI 15m: {rsi_15m}\n"
                        f"⬆️ RSI sinyali VWAP ile güçlendi!\n"
                        f"🎯 TP: +10/20$ | SL: -5$\n"
                        f"🕐 {current_time_str}"
                    )
                    send_telegram_msg(msg)
                    last_alert = "sell_vwap"

                # Nötr bölge — sıfırla
                if 45 < rsi_5m < 55:
                    last_alert = None

            else:
                if datetime.now().second % 30 == 0:
                    logger.info(f"[{current_time_str}] 💤 Saat 08:00'i bekliyor...")

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
