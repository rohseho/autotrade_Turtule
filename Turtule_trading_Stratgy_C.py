#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Turtule Trading Strategy C Bot

- Strategy based on "catching crypto trends" and YouTube channel.
- Trades BTC and top 10 altcoins on Binance Futures (Hedge Mode).
- Uses Donchian Channel strategy with multiple periods (5, 10, 20, 30, 60).
- Position sizing is dynamically adjusted based on 90-day volatility.
- Each coin/period pair is treated as a separate sub-strategy for entry and exit.
- Designed for cron job execution (runs once and exits).
'''

import ccxt
import time
import json
import pandas as pd
import numpy as np
import csv
from datetime import datetime
import os
import sys
import platform

# File locking for cron job safety
if platform.system() == "Windows":
    import msvcrt
else:
    import fcntl

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path: str = ".env"):
        # Fallback if python-dotenv is not installed
        env_path = dotenv_path
        if not os.path.isabs(env_path):
            env_path = os.path.join(os.getcwd(), env_path)
        if not os.path.exists(env_path):
            return
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass

from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Import custom modules
import FINAL_myBinance as myBinance
import FINAL_discord_alert as discord_alert

class TurtleTradingBot:
    def __init__(self):
        """Initialize the bot"""
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_SECRET_KEY')
        
        if not self.api_key or not self.api_secret:
            raise ValueError("❌ Binance API keys not found in .env file!")
        
        self.binance = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })
        
        self.set_hedge_mode()
        
        self.bot_name = "Turtule_trading_Stratgy_C_Bot"
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        self.json_files = {
            'config': "Turtule_trading_Stratgy_C_Config.json",
            'positions': logs_dir / f"{self.bot_name}_CurrentPositions.json",
            'trading_log_csv': logs_dir / f"{self.bot_name}_TradingLog.csv",
            'lock': f"{self.bot_name}_lock.txt"
        }
        
        if not self.acquire_lock():
            print("⚠️ Another instance of the bot is running. Exiting.")
            sys.exit(0)
            
        self.config = self.load_json_file(self.json_files['config'])
        if not self.config:
            raise ValueError("❌ Configuration file could not be loaded!")
            
        self.load_config_settings()
        
        self.current_positions = self.load_json_file(self.json_files['positions'])
        self.init_csv_log()
        
        print("🚀 Turtle Trading Strategy C Bot initialized successfully!")

    def load_config_settings(self):
        """Load settings from the config dictionary"""
        inv_alloc = self.config.get('investment_allocation', {})
        self.total_account_usage_ratio = inv_alloc.get('total_account_usage_ratio', 0.5)
        
        strat_settings = self.config.get('strategy_settings', {})
        self.donchian_periods = strat_settings.get('donchian_periods', [5, 10, 20, 30, 60])
        self.volatility_period = strat_settings.get('volatility_period', 90)
        self.volatility_target = strat_settings.get('volatility_target', 0.25)
        
        self.coin_allocation = self.config.get('coin_allocation', {})
        self.active_coins = [coin for coin, settings in self.coin_allocation.items() if settings.get('active', False)]
        
        print(f"📈 Account Usage Ratio: {self.total_account_usage_ratio * 100}%")
        print(f"🎯 Active Coins ({len(self.active_coins)}): {', '.join(self.active_coins)}")

    def set_hedge_mode(self):
        """Enable Hedge Mode for futures trading."""
        try:
            self.binance.set_position_mode(hedged=True)
            print("✅ Hedge Mode enabled successfully.")
        except Exception as e:
            if "No need to change position side" in str(e):
                print("ℹ️ Hedge Mode is already enabled.")
            else:
                print(f"⚠️ Could not set Hedge Mode: {e}")

    def acquire_lock(self):
        """Acquire a process lock to prevent duplicate instances."""
        self.lock_file_handle = open(self.json_files['lock'], 'w')
        try:
            if platform.system() == "Windows":
                msvcrt.locking(self.lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file_handle.write(str(os.getpid()))
            self.lock_file_handle.flush()
            return True
        except (IOError, OSError):
            self.lock_file_handle.close()
            return False

    def release_lock(self):
        """Release the process lock."""
        try:
            if platform.system() == "Windows":
                msvcrt.locking(self.lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.lock_file_handle.fileno(), fcntl.LOCK_UN)
            self.lock_file_handle.close()
            os.remove(self.json_files['lock'])
        except Exception as e:
            print(f"⚠️ Error releasing lock: {e}")

    def load_json_file(self, filepath):
        """Load data from a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            print(f"❌ Error loading {filepath}: {e}")
            return {}

    def save_json_file(self, filepath, data):
        """Save data to a JSON file."""
        try:
            temp_filepath = f"{filepath}.tmp"
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_filepath, filepath)
            return True
        except Exception as e:
            print(f"❌ Error saving {filepath}: {e}")
            return False

    def init_csv_log(self):
        """Initialize the CSV log file with a header if it doesn't exist."""
        csv_file = self.json_files['trading_log_csv']
        if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
            with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Ticker', 'Donchian Period', 'Action', 'Side', 'Amount', 'Price', 'Value', 'Leverage', 'PNL'])

    def add_csv_log(self, log_data):
        """Append a new record to the CSV log file."""
        try:
            with open(self.json_files['trading_log_csv'], 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    log_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    log_data.get('ticker'),
                    log_data.get('period'),
                    log_data.get('action'),
                    log_data.get('side'),
                    f"{log_data.get('amount', 0):.8f}",
                    f"{log_data.get('price', 0):.4f}",
                    f"{log_data.get('value', 0):.2f}",
                    log_data.get('leverage'),
                    f"{log_data.get('pnl', 0):.2f}"
                ])
        except Exception as e:
            print(f"❌ Error writing to CSV log: {e}")

    def get_account_balance(self):
        """Fetch the total account balance in USDT."""
        try:
            balance = self.binance.fetch_balance(params={'type': 'future'})
            total_balance = float(balance['info']['totalWalletBalance'])
            return total_balance
        except Exception as e:
            print(f"❌ Could not fetch account balance: {e}")
            return 0.0

    def calculate_volatility(self, ticker):
        """Calculate the 90-day volatility."""
        try:
            ohlcv = myBinance.GetOhlcv(self.binance, ticker, '1d', self.volatility_period + 1)
            if ohlcv.empty or len(ohlcv) < self.volatility_period:
                print(f"⚠️ Not enough data for {ticker} to calculate volatility.")
                return None
            
            daily_returns = ohlcv['close'].pct_change().dropna()
            # Daily standard deviation (like STDEV in Excel)
            daily_std_dev = daily_returns.std()
            # 90-day volatility
            period_90_volatility = daily_std_dev * np.sqrt(90)
            print(f"📈 {ticker} 90-day Volatility: {period_90_volatility:.2%}")
            return period_90_volatility
        except Exception as e:
            print(f"❌ Volatility calculation failed for {ticker}: {e}")
            return None

    def get_donchian_channel(self, ticker, period):
        """Calculate Donchian Channel values based on completed candles only."""
        try:
            # Need period + 2 candles: period for calculation + 1 completed + 1 current (incomplete)
            ohlcv = myBinance.GetOhlcv(self.binance, ticker, '1d', period + 2)
            if ohlcv.empty or len(ohlcv) < period + 2:
                return None, None, None, None

            # Use only completed candles (exclude the current incomplete candle)
            completed_ohlcv = ohlcv.iloc[:-1]
            
            # Calculate Donchian Channel using the last 'period' completed candles
            channel_data = completed_ohlcv.tail(period)
            high = channel_data['high'].max()
            low = channel_data['low'].min()
            midline = (high + low) / 2
            
            # Get the last completed candle's close price for signal generation
            last_completed_close = completed_ohlcv['close'].iloc[-1]
            
            print(f"📊 {ticker}-{period}d | High: {high:.4f} | Low: {low:.4f} | Mid: {midline:.4f} | Last Close: {last_completed_close:.4f}")
            
            return high, low, midline, last_completed_close
        except Exception as e:
            print(f"❌ Donchian Channel calculation failed for {ticker} with period {period}: {e}")
            return None, None, None, None

    def run(self):
        """Main trading cycle."""
        print(f"\n🔄 Starting trading cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        total_balance = self.get_account_balance()
        if total_balance == 0:
            print("❌ Cannot proceed with zero balance.")
            return

        strategy_capital = total_balance * self.total_account_usage_ratio
        base_capital_per_coin = strategy_capital / len(self.active_coins) if self.active_coins else 0
        
        print(f"💰 Total Balance: ${total_balance:,.2f} | Strategy Capital: ${strategy_capital:,.2f} | Base Capital/Coin: ${base_capital_per_coin:,.2f}")

        for ticker in self.active_coins:
            volatility = self.calculate_volatility(ticker)
            if volatility is None or volatility == 0:
                continue

            # Adjust capital based on volatility
            # Formula: Allocated Capital * (Target Volatility / Actual Volatility)
            volatility_adj_factor = self.volatility_target / volatility
            adjusted_capital = base_capital_per_coin * volatility_adj_factor
            
            capital_per_period = adjusted_capital / len(self.donchian_periods)
            
            print(f"⚖️ {ticker} | Vol Adj Factor: {volatility_adj_factor:.2f} | Adjusted Capital: ${adjusted_capital:,.2f} | Capital/Period: ${capital_per_period:,.2f}")

            coin_settings = self.coin_allocation.get(ticker, {})

            for period in self.donchian_periods:
                high, low, midline, last_completed_close = self.get_donchian_channel(ticker, period)
                if last_completed_close is None:
                    continue

                # Get current position for this specific sub-strategy
                position_key = f"{ticker}-{period}"
                current_pos = self.current_positions.get(position_key, {})
                
                # --- Signal Detection Logic (based on completed candles) ---
                long_signal = last_completed_close > high
                short_signal = last_completed_close < low and not coin_settings.get('long_only', False)
                long_exit_signal = last_completed_close < midline
                short_exit_signal = last_completed_close > midline
                
                # --- Entry Logic (execute in next candle) ---
                if not current_pos:
                    if long_signal:
                        print(f"🟢 {ticker}-{period}d | LONG SIGNAL: {last_completed_close:.4f} > {high:.4f}")
                        self.open_position(ticker, period, 'LONG', capital_per_period, coin_settings)
                    elif short_signal:
                        print(f"🔴 {ticker}-{period}d | SHORT SIGNAL: {last_completed_close:.4f} < {low:.4f}")
                        self.open_position(ticker, period, 'SHORT', capital_per_period, coin_settings)

                # --- Exit Logic (execute in next candle) ---
                elif current_pos:
                    if current_pos.get('side') == 'LONG' and long_exit_signal:
                        print(f"🟡 {ticker}-{period}d | LONG EXIT: {last_completed_close:.4f} < {midline:.4f}")
                        self.close_position(ticker, period, current_pos)
                    elif current_pos.get('side') == 'SHORT' and short_exit_signal:
                        print(f"🟡 {ticker}-{period}d | SHORT EXIT: {last_completed_close:.4f} > {midline:.4f}")
                        self.close_position(ticker, period, current_pos)
                
                time.sleep(1) # API rate limit

        print("✅ Trading cycle finished.")

    def open_position(self, ticker, period, side, capital, settings):
        """Open a new long or short position at market price (next candle execution)."""
        leverage = settings.get('long_leverage' if side == 'LONG' else 'short_leverage', 1)
        
        try:
            self.binance.set_leverage(leverage, ticker.replace('/', ''))
        except Exception as e:
            print(f"⚠️ Could not set leverage for {ticker} to {leverage}x: {e}")

        # Get current market price for order execution
        current_price = myBinance.GetCoinNowPrice(self.binance, ticker)
        if current_price <= 0:
            print(f"❌ Could not get current price for {ticker}")
            return
            
        notional_value = capital * leverage
        amount = notional_value / current_price
        
        print(f"📩 {ticker}-{period}d | EXECUTING {side} | Market Price: ${current_price:.4f}")

        try:
            order_side = 'buy' if side == 'LONG' else 'sell'
            params = {'positionSide': side}
            order = self.binance.create_market_order(ticker, order_side, amount, params=params)
            
            # Update state
            self.current_positions[f"{ticker}-{period}"] = {
                'side': side,
                'amount': float(order['amount']),
                'entry_price': float(order['price']),
                'leverage': leverage,
                'entry_time': datetime.now().isoformat()
            }
            self.save_json_file(self.json_files['positions'], self.current_positions)
            
            # Log and notify
            log_data = {
                'ticker': ticker, 'period': period, 'action': 'OPEN', 'side': side, 
                'amount': order['amount'], 'price': order['price'], 'value': order['cost'], 'leverage': leverage
            }
            self.add_csv_log(log_data)
            discord_alert.SendMessage(f"📈 OPEN {side} | {ticker} ({period}d) | Size: {order['amount']:.4f} | Price: ${order['price']:.2f}")

        except Exception as e:
            print(f"❌ Failed to open {side} position for {ticker}-{period}: {e}")

    def close_position(self, ticker, period, position_data):
        """Close an existing position at market price (next candle execution)."""
        side = position_data.get('side')
        amount = position_data.get('amount')
        entry_price = position_data.get('entry_price')
        leverage = position_data.get('leverage')

        # Get current market price for order execution
        current_price = myBinance.GetCoinNowPrice(self.binance, ticker)
        if current_price <= 0:
            print(f"❌ Could not get current price for {ticker}")
            return

        print(f"📩 {ticker}-{period}d | EXECUTING {side} CLOSE | Market Price: ${current_price:.4f}")

        try:
            order_side = 'sell' if side == 'LONG' else 'buy'
            params = {'positionSide': side}
            order = self.binance.create_market_order(ticker, order_side, amount, params=params)

            # Calculate PNL
            if side == 'LONG':
                pnl = (float(order['price']) - entry_price) * amount * leverage
            else: # SHORT
                pnl = (entry_price - float(order['price'])) * amount * leverage
            
            # Update state
            del self.current_positions[f"{ticker}-{period}"]
            self.save_json_file(self.json_files['positions'], self.current_positions)
            
            # Log and notify
            log_data = {
                'ticker': ticker, 'period': period, 'action': 'CLOSE', 'side': side,
                'amount': order['amount'], 'price': order['price'], 'value': order['cost'], 
                'leverage': leverage, 'pnl': pnl
            }
            self.add_csv_log(log_data)
            pnl_emoji = "✅" if pnl >= 0 else "🔻"
            discord_alert.SendMessage(f"📉 CLOSE {side} | {ticker} ({period}d) | PNL: {pnl_emoji} ${pnl:,.2f}")

        except Exception as e:
            print(f"❌ Failed to close {side} position for {ticker}-{period}: {e}")
            
    def __del__(self):
        """Destructor to ensure lock is released."""
        self.release_lock()

def main():
    bot = None
    try:
        bot = TurtleTradingBot()
        bot.run()
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        discord_alert.SendMessage(f"🚨 BOT CRASHED: {e}")
    finally:
        if bot:
            bot.release_lock()
        print("Bot execution finished.")

if __name__ == "__main__":
    main()
