#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Backtester for the Turtule Trading Strategy C

- Simulates the Turtle Trading strategy using historical data.
- Loads configuration from "Backtest_Turtule_Config.json".
- Replicates the live bot's logic:
    - Volatility-adjusted position sizing.
    - Donchian Channel entry/exit for multiple periods.
    - Per-coin, per-period position management.
- Calculates and outputs detailed performance metrics and graphs.
'''

import ccxt
import time
import json
import pandas as pd
import numpy as np
import os
import csv
from datetime import datetime
from pathlib import Path
import sys

# Import custom modules
import FINAL_myBinance as myBinance
import FINAL_discord_alert as discord_alert

# --- Matplotlib setup for non-GUI environments ---
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# --- Constants and Global Settings ---
CONFIG_FILE = "Backtest_Turtule_Config.json"

# --- Font and Language Setup for Graphs ---
def setup_korean_font():
    try:
        available_fonts = [f.name for f in font_manager.fontManager.ttflist]
        korean_fonts = ['Noto Sans CJK KR', 'NanumGothic', 'Malgun Gothic', 'AppleGothic']
        for font in korean_fonts:
            if font in available_fonts:
                plt.rcParams['font.family'] = [font, 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
                return True
        return False
    except Exception:
        return False

HAS_KOREAN_FONT = setup_korean_font()
LABELS = {
    'mdd_area': 'MDD 영역' if HAS_KOREAN_FONT else 'MDD Area',
    'mdd_trend': 'MDD 추이' if HAS_KOREAN_FONT else 'MDD Trend',
    'month': '월' if HAS_KOREAN_FONT else 'Month',
    'returns': '수익률 (%)' if HAS_KOREAN_FONT else 'Returns (%)',
    'date': '날짜' if HAS_KOREAN_FONT else 'Date',
    'monthly_returns_by_asset': '종목별 월간 수익률 (%)' if HAS_KOREAN_FONT else 'Monthly Returns by Asset (%)',
    'total_portfolio_monthly': '전체 포트폴리오 월간 수익률 (%)' if HAS_KOREAN_FONT else 'Total Portfolio Monthly Returns (%)',
    'mdd_by_asset': '종목별 최대 낙폭(MDD) 추이' if HAS_KOREAN_FONT else 'Maximum Drawdown by Asset',
    'total_portfolio_mdd': '전체 포트폴리오 최대 낙폭(MDD) 추이' if HAS_KOREAN_FONT else 'Total Portfolio Maximum Drawdown',
    'returns_timeline_by_asset': '종목별 수익률 변화 추이 (%)' if HAS_KOREAN_FONT else 'Returns Timeline by Asset (%)',
    'total_portfolio_returns_timeline': '전체 포트폴리오 수익률 변화 추이 (%)' if HAS_KOREAN_FONT else 'Total Portfolio Returns Timeline (%)'
}


class TurtleStrategyBacktester:
    def __init__(self):
        """Initializes the backtester by loading configuration and setting up environment."""
        # Load configuration
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"❌ Configuration file '{CONFIG_FILE}' not found.")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"❌ Error decoding JSON from '{CONFIG_FILE}'.")
            sys.exit(1)

        # --- Set backtest parameters from config ---
        bt_settings = self.config['backtest_settings']
        strat_settings = self.config['strategy_settings']
        coin_settings = self.config['backtest_coin_settings']
        
        # Use dynamic date range - automatically set end_date to today if configured date is in future
        config_start = pd.to_datetime(bt_settings['start_date'])
        config_end = pd.to_datetime(bt_settings['end_date'])
        today = pd.Timestamp.now().normalize()
        
        # Automatically adjust end_date to today if configured end_date is in the future
        self.start_date = config_start
        self.end_date = min(config_end, today)
        
        if config_end > today:
            print(f"📅 백테스트 종료일을 오늘로 자동 조정: {config_end.date()} → {today.date()}")
        self.initial_capital = float(bt_settings['initial_capital'])
        self.fee_rate = float(bt_settings['fee_rate'])

        # --- Strategy and Coin Settings ---
        self.donchian_periods = strat_settings['donchian_periods']
        self.volatility_period = strat_settings['volatility_period']
        self.max_positions_per_coin = strat_settings['max_positions_per_coin']
        
        self.active_coins = coin_settings['target_coins']
        self.long_only = coin_settings['long_only']
        self.leverage_long = coin_settings['leverage_long']
        self.leverage_short = coin_settings['leverage_short']

        # --- Calculate and distribute initial capital ---
        inv_alloc = self.config.get('investment_allocation', {})
        self.total_account_usage_ratio = inv_alloc.get('total_account_usage_ratio', 0.5)
        self.strategy_investment = self.initial_capital * self.total_account_usage_ratio
        base_capital_per_coin = self.strategy_investment / len(self.active_coins) if self.active_coins else 0
        
        # --- Initialize Binance client and data holder ---
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_SECRET_KEY')
        self.binance = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,  # 시간 차이 자동 조정
                'recvWindow': 10000  # 요청 유효 시간 확장 (10초)
            }
        })
        self.historical_data = {}
        
        # --- Enhanced State variables ---
        self.cash = self.initial_capital # Total cash includes non-strategy funds
        self.positions = {}
        self.portfolio_history = []
        self.trade_history = []

        # --- Initialize per-coin tracking dictionaries ---
        self.portfolio_history_by_coin = {coin: [] for coin in self.active_coins}
        
        # --- Enhanced Logging Setup ---
        self.results_dir = Path("backtest_results_turtle")
        self.results_dir.mkdir(exist_ok=True)
        self.log_paths = {
            'trading_csv': self.results_dir / "FINAL_Backtest_TradingLog_Turtle.csv",
            'portfolio_csv': self.results_dir / "FINAL_Backtest_PortfolioValues_Turtle.csv",
            'summary_log': self.results_dir / "FINAL_Backtest_Summary_Log_Turtle.txt",
            'long_short_csv': self.results_dir / "FINAL_Backtest_LongShort_Returns_Turtle.csv"
        }
        self.init_log_files()
        
        print("🚀 Turtle Strategy Backtester initialized.")

    def init_log_files(self):
        """Initialize CSV log files with headers."""
        with open(self.log_paths['trading_csv'], 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'ticker', 'period', 'action', 'side', 'amount', 'price', 'value', 'leverage', 'pnl'])
        with open(self.log_paths['portfolio_csv'], 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'value', 'cash', 'positions_count'])
        with open(self.log_paths['long_short_csv'], 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['period', 'coin', 'long_pnl', 'short_pnl', 'long_return_%', 'short_return_%'])
    
    def _fetch_data(self):
        """Fetches historical OHLCV data for all active coins."""
        print("⏳ Fetching historical data for all active coins...")
        # Calculate the total number of days of data needed
        fetch_days = (self.end_date - self.start_date).days + self.volatility_period + max(self.donchian_periods) + 5
        
        for coin in self.active_coins:
            print(f"  -> Fetching {coin}...")
            try:
                # Use myBinance module to get data
                df = myBinance.GetOhlcv(self.binance, coin, '1d', fetch_days)
                if df is not None and not df.empty:
                    self.historical_data[coin] = df
                else:
                    print(f"⚠️ No data returned for {coin}")
            except Exception as e:
                print(f"❌ Failed to fetch data for {coin}: {e}")
            time.sleep(1) # Be respectful to the API
        print("✅ Data fetching complete.")

    def _adjust_backtest_period(self):
        """Adjust backtest period based on available data."""
        if not self.historical_data:
            return
            
        # Find the common date range across all coins
        earliest_start = None
        latest_end = None
        
        for coin, df in self.historical_data.items():
            if df.empty:
                continue
                
            data_start = df.index.min()
            data_end = df.index.max()
            
            if earliest_start is None or data_start > earliest_start:
                earliest_start = data_start
            if latest_end is None or data_end < latest_end:
                latest_end = data_end
        
        if earliest_start is None or latest_end is None:
            print("❌ No valid data found for backtest period adjustment.")
            return
            
        # Add buffer for volatility and donchian calculations
        buffer_days = self.volatility_period + max(self.donchian_periods) + 5
        adjusted_start = earliest_start + pd.Timedelta(days=buffer_days)
        
        # Use the adjusted dates
        original_start = self.start_date
        original_end = self.end_date
        
        self.start_date = max(adjusted_start, earliest_start)
        self.end_date = min(latest_end, latest_end)  # Use available end date
        
        print(f"📅 백테스트 기간 조정:")
        print(f"  원래 기간: {original_start.date()} ~ {original_end.date()}")
        print(f"  데이터 범위: {earliest_start.date()} ~ {latest_end.date()}")
        print(f"  조정된 기간: {self.start_date.date()} ~ {self.end_date.date()}")

    def run_backtest(self):
        self._fetch_data()
        
        if not self.historical_data:
            print("❌ No historical data available. Cannot run backtest.")
            return

        # Adjust backtest period based on available data
        self._adjust_backtest_period()
        
        simulation_dates = pd.date_range(start=self.start_date, end=self.end_date, freq='D')

        # Initialize portfolio history for day zero
        self.update_portfolio_history(self.start_date - pd.Timedelta(days=1))

        for current_date in simulation_dates:
            # Use a consistent base capital for calculations throughout the backtest (like old version)
            base_capital_per_coin = self.strategy_investment / len(self.active_coins) if self.active_coins else 0
            
            for coin in self.active_coins:
                if base_capital_per_coin <= 0: 
                    print(f"⚠️ Base capital per coin is 0: {base_capital_per_coin}")
                    continue # Skip if coin's portfolio is depleted
                
                if coin not in self.historical_data: 
                    print(f"⚠️ {coin} not in historical_data")
                    continue

                df = self.historical_data[coin]
                data_until_today = df[df.index <= current_date]
                if data_until_today.empty: 
                    print(f"⚠️ {coin} data_until_today is empty for {current_date}")
                    continue

                vol_data = data_until_today.tail(self.volatility_period + 1)
                daily_returns = vol_data['close'].pct_change().dropna()
                print(f"🔍 {coin} on {current_date.date()}: vol_data len={len(vol_data)}, daily_returns len={len(daily_returns)}, required={self.volatility_period - 5}")
                if len(daily_returns) < self.volatility_period - 5: 
                    print(f"⚠️ {coin} insufficient daily_returns: {len(daily_returns)} < {self.volatility_period - 5}")
                    continue
                
                daily_std = daily_returns.std()
                period_90_vol = daily_std * np.sqrt(90)  # 90일 변동성으로 변경
                print(f"📊 {coin} volatility: daily_std={daily_std:.6f}, 90day_vol={period_90_vol:.6f}")
                if period_90_vol == 0: 
                    print(f"⚠️ {coin} 90day_vol is 0")
                    continue
                
                vol_adj_factor = self.config['strategy_settings']['volatility_target'] / period_90_vol
                adjusted_capital = base_capital_per_coin * vol_adj_factor
                capital_per_period = adjusted_capital / len(self.donchian_periods)

                # --- DEBUG PRINT ---
                print(f"[{current_date.date()}] [{coin}] Base Capital: ${base_capital_per_coin:,.2f}, Adjusted Capital: ${adjusted_capital:,.2f}, Capital per Period: ${capital_per_period:,.2f}")

                # --- This was the missing critical part ---
                # The new config structure is simpler, so we create a temporary
                # coin_settings dict that matches the old structure the functions expect.
                coin_settings = {
                    'long_only': self.long_only,
                    'long_leverage': self.leverage_long,
                    'short_leverage': self.leverage_short
                }

                for period in self.donchian_periods:
                    # Ensure we have enough data for calculation (period for channel + previous day)
                    if len(data_until_today) < period + 2:
                        continue

                    # Use OLD version logic: Signal based on current day's close, execute at current day's close
                    channel_data = data_until_today.tail(period + 1)
                    if len(channel_data) < period + 1:
                        continue
                    
                    # Calculate Donchian Channel (exclude last candle from calculation, like OLD version)
                    relevant_data = channel_data.iloc[:-1]
                    high = relevant_data['high'].rolling(window=period).max().iloc[-1]
                    low = relevant_data['low'].rolling(window=period).min().iloc[-1]
                    midline = (high + low) / 2
                    
                    # Use current day's close for signal generation (like OLD version)
                    last_close = channel_data['close'].iloc[-1]

                    # --- DEBUG PRINT ---
                    print(f"  - Period: {period}d | High: {high:.4f}, Low: {low:.4f}, Last Close: {last_close:.4f}")

                    position_key = f"{coin}-{period}"
                    current_pos = self.positions.get(position_key)

                    if not current_pos:
                        # Entry Logic: Signal and execution based on current day's close (like OLD version)
                        if last_close > high:
                            print(f"    ✅ LONG ENTRY SIGNAL: {last_close:.4f} > {high:.4f} → Execute at {last_close:.4f}")
                            self.simulate_open(current_date, coin, period, 'LONG', capital_per_period, coin_settings, last_close)
                        elif not coin_settings.get('long_only') and last_close < low:
                            print(f"    ✅ SHORT ENTRY SIGNAL: {last_close:.4f} < {low:.4f} → Execute at {last_close:.4f}")
                            self.simulate_open(current_date, coin, period, 'SHORT', capital_per_period, coin_settings, last_close)
                        else:
                            # No signal detected - this is normal
                            pass
                    
                    elif current_pos:
                        # Exit Logic: Signal and execution based on current day's close (like OLD version)
                        if current_pos['side'] == 'LONG' and last_close < midline:
                            print(f"    🟡 LONG EXIT SIGNAL: {last_close:.4f} < {midline:.4f} → Execute at {last_close:.4f}")
                            self.simulate_close(current_date, position_key, last_close)
                        elif current_pos['side'] == 'SHORT' and last_close > midline:
                            print(f"    🟡 SHORT EXIT SIGNAL: {last_close:.4f} > {midline:.4f} → Execute at {last_close:.4f}")
                            self.simulate_close(current_date, position_key, last_close)
            
            # Update portfolio history at the end of the day after all trades
            self.update_portfolio_history(current_date)
            
        # Generate reports and graphs
        self._calculate_and_save_results()

        # Print backtest summary
        total_trades = len(self.trade_history)
        print(f"\n📊 백테스트 완료 요약:")
        print(f"  📅 기간: {self.start_date.date()} ~ {self.end_date.date()}")
        print(f"  📈 총 거래 수: {total_trades}개")
        if total_trades > 0:
            print(f"  💰 마지막 포트폴리오 가치: ${self.portfolio_history[-1]['value']:,.2f}")
        else:
            print(f"  ⚪ 해당 기간 동안 돈치안 브레이크아웃 신호가 발생하지 않았습니다.")
            print(f"  💡 이는 정상적인 결과입니다. 다른 기간을 시도해보세요.")

        print(f"✅ All reports and graphs saved to '{self.results_dir}' directory.")


    def update_portfolio_history(self, current_date):
        """Calculate and store portfolio value for a given date."""
        total_value, per_coin_values = self.calculate_portfolio_value(current_date)
        
        history_entry = {
            'date': current_date, 
            'value': total_value, 
            'cash': self.cash, 
            'positions_count': len(self.positions)
        }
        self.portfolio_history.append(history_entry)
        
        with open(self.log_paths['portfolio_csv'], 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(history_entry.values())
        
        for coin, coin_value in per_coin_values.items():
            self.portfolio_history_by_coin[coin].append({'date': current_date, 'value': coin_value})
            
    def calculate_portfolio_value(self, current_date):
        """Calculates the total portfolio equity and per-coin equity (fixed to match strategy investment)."""
        # Start with strategy investment instead of total cash
        total_strategy_equity = self.strategy_investment
        
        # Add all realized PnL from trades
        total_realized_pnl = sum(trade['pnl'] for trade in self.trade_history)
        total_strategy_equity += total_realized_pnl
        
        per_coin_values = {}
        
        # Initialize per-coin values with their base capital + realized PNL
        base_capital_per_coin = self.strategy_investment / len(self.active_coins) if self.active_coins else 0
        for ticker in self.active_coins:
            realized_pnl = sum(trade['pnl'] for trade in self.trade_history if trade['ticker'] == ticker)
            per_coin_values[ticker] = base_capital_per_coin + realized_pnl

        # Add unrealized PnL
        for key, pos in self.positions.items():
            ticker, period = key.split('-')
            if ticker not in self.historical_data: continue

            df = self.historical_data[ticker]
            if current_date in df.index:
                current_price = df.loc[current_date]['close']
                
                unrealized_pnl = 0
                if pos['side'] == 'LONG':
                    unrealized_pnl = (current_price - pos['entry_price']) * pos['amount'] * pos['leverage']
                else: # SHORT
                    unrealized_pnl = (pos['entry_price'] - current_price) * pos['amount'] * pos['leverage']
                
                total_strategy_equity += unrealized_pnl
                if ticker in per_coin_values:
                    per_coin_values[ticker] += unrealized_pnl
        
        return total_strategy_equity, per_coin_values

    def simulate_open(self, date, ticker, period, side, capital, settings, price):
        leverage = settings.get('long_leverage' if side == 'LONG' else 'short_leverage', 1)
        notional_value = capital * leverage
        amount = notional_value / price
        
        fee = notional_value * self.fee_rate
        self.cash -= fee

        position_key = f"{ticker}-{period}"
        self.positions[position_key] = { 'side': side, 'amount': amount, 'entry_price': price, 'leverage': leverage, 'entry_date': date, 'ticker': ticker }
        
        trade_log = {
            'date': date, 'ticker': ticker, 'period': period, 'action': 'OPEN', 'side': side, 
            'amount': amount, 'price': price, 'value': notional_value, 'leverage': leverage, 'pnl': -fee
        }
        self.trade_history.append(trade_log)
        self.write_trade_csv(trade_log)

    def simulate_close(self, date, position_key, price):
        pos = self.positions.pop(position_key)
        
        notional_value = pos['amount'] * price * pos['leverage']
        fee = notional_value * self.fee_rate
        
        pnl = 0
        if pos['side'] == 'LONG':
            pnl = (price - pos['entry_price']) * pos['amount'] * pos['leverage']
        else: # SHORT
            pnl = (pos['entry_price'] - price) * pos['amount'] * pos['leverage']
            
        self.cash += pnl - fee
        
        trade_log = {
            'date': date, 'ticker': pos['ticker'], 'period': position_key.split('-')[1], 'action': 'CLOSE', 'side': pos['side'],
            'amount': pos['amount'], 'price': price, 'value': notional_value, 'leverage': pos['leverage'], 'pnl': pnl - fee
        }
        self.trade_history.append(trade_log)
        self.write_trade_csv(trade_log)
        
    def write_trade_csv(self, log):
        with open(self.log_paths['trading_csv'], 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([log['date'], log['ticker'], log['period'], log['action'], log['side'], log['amount'], log['price'], log['value'], log['leverage'], log['pnl']])

    def _calculate_and_save_results(self):
        """Calculate final metrics and generate all report files and graphs."""
        if not self.portfolio_history:
            print("❌ No portfolio history recorded. Cannot generate reports.")
            return

        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')
        
        # Ensure trading log exists before reading
        if not self.log_paths['trading_csv'].exists():
            print(f"⚠️ Trading log file not found at {self.log_paths['trading_csv']}. Skipping dependent reports.")
            all_trades_df = pd.DataFrame()
        else:
            all_trades_df = pd.read_csv(self.log_paths['trading_csv'], parse_dates=['date'])

        # Generate reports
        self._write_summary_report(portfolio_df, all_trades_df)
        if not all_trades_df.empty:
            self.generate_long_short_report()  # Use the correct function

        # Generate graphs
        self.plot_monthly_returns()
        self.plot_mdd_trends()
        self.plot_returns_timeline()

    def _write_summary_report(self, portfolio_df, all_trades_df):
        """Calculate and save the main summary report."""
        with open(self.log_paths['summary_log'], 'w', encoding='utf-8') as f:
            # --- Overall Performance ---
            f.write("--- Turtle Strategy Backtest Summary ---\n")
            f.write(f"Period: {self.start_date} to {self.end_date}\n\n")
            
            initial_capital = self.initial_capital
            final_value = portfolio_df['value'].iloc[-1]
            total_return = ((final_value / initial_capital) - 1) * 100
            mdd = self._calculate_mdd(portfolio_df['value'])
            sharpe_ratio = self._calculate_sharpe_ratio(portfolio_df['value'])
            total_trades = len(all_trades_df)

            f.write(f"Initial Capital: ${initial_capital:,.2f}\n")
            f.write(f"Final Portfolio Value: ${final_value:,.2f}\n\n")
            f.write(f"Total Return: {total_return:.2f}%\n")
            f.write(f"Max Drawdown: {mdd:.2f}%\n")
            f.write(f"Sharpe Ratio: {sharpe_ratio:.2f}\n")
            f.write(f"Total Trades: {total_trades}\n")

            # --- Performance by Coin ---
            f.write("\n\n--- Performance by Coin ---\n")
            for coin in self.active_coins:
                if coin in self.portfolio_history_by_coin and self.portfolio_history_by_coin[coin]:
                    coin_df = pd.DataFrame(self.portfolio_history_by_coin[coin]).set_index('date')
                    coin_initial = coin_df['value'].iloc[0]
                    coin_final = coin_df['value'].iloc[-1]
                    # Avoid division by zero if initial value is 0
                    if coin_initial > 0:
                        coin_total_return = ((coin_final / coin_initial) - 1) * 100
                    else:
                        coin_total_return = 0.0
                    
                    coin_mdd = self._calculate_mdd(coin_df['value'])
                    f.write(f"\n[{coin}]\n")
                    f.write(f"  Total Return: {coin_total_return:.2f}%\n")
                    f.write(f"  Max Drawdown: {coin_mdd:.2f}%\n")

            # --- Monthly Returns ---
            f.write("\n\n--- Monthly Returns ---\n")
            f.write("\n** Total Portfolio **\n")
            monthly_returns = self._compute_monthly_returns(portfolio_df)
            if monthly_returns.empty or monthly_returns.isnull().all():
                f.write("  Not enough data to calculate monthly returns.\n")
            else:
                for month, ret in monthly_returns.items():
                    f.write(f"  {month.strftime('%Y-%m')}: {ret:.2f}%\n")
            
            for coin in self.active_coins:
                if coin in self.portfolio_history_by_coin and self.portfolio_history_by_coin[coin]:
                    f.write(f"\n** {coin} **\n")
                    coin_df = pd.DataFrame(self.portfolio_history_by_coin[coin]).set_index('date')
                    monthly_returns_coin = self._compute_monthly_returns(coin_df)
                    if monthly_returns_coin.empty or monthly_returns_coin.isnull().all():
                        f.write("  No trades or not enough data for monthly returns.\n")
                    else:
                        for month, ret in monthly_returns_coin.items():
                            f.write(f"  {month.strftime('%Y-%m')}: {ret:.2f}%\n")

    def _write_long_short_returns(self, all_trades_df):
        """Calculate and save long/short returns to a CSV file."""
        if all_trades_df.empty:
            return

        all_trades_df['month'] = all_trades_df['date'].dt.to_period('M')
        
        # Overall Long/Short PnL
        overall_pnl = all_trades_df.groupby(['ticker', 'side'])['pnl'].sum().unstack(fill_value=0)
        if 'long' not in overall_pnl: overall_pnl['long'] = 0
        if 'short' not in overall_pnl: overall_pnl['short'] = 0
        
        # Monthly Long/Short PnL
        monthly_pnl = all_trades_df.groupby(['month', 'ticker', 'side'])['pnl'].sum().unstack(fill_value=0)
        if 'long' not in monthly_pnl: monthly_pnl['long'] = 0
        if 'short' not in monthly_pnl: monthly_pnl['short'] = 0
        
        # Calculate returns based on initial capital per period (approximation)
        # A more accurate way would be to track capital per coin, but this gives a good directional measure.
        initial_capital_per_coin = self.initial_capital / len(self.active_coins)
        overall_pnl['long_return'] = (overall_pnl['long'] / initial_capital_per_coin) * 100
        overall_pnl['short_return'] = (overall_pnl['short'] / initial_capital_per_coin) * 100
        
        monthly_pnl_reset = monthly_pnl.reset_index()
        monthly_pnl_reset['long_return'] = (monthly_pnl_reset['long'] / initial_capital_per_coin) * 100
        monthly_pnl_reset['short_return'] = (monthly_pnl_reset['short'] / initial_capital_per_coin) * 100

        with open(self.log_paths['long_short_csv'], 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['period', 'coin', 'long_pnl', 'short_pnl', 'long_return_%', 'short_return_%'])
            
            # Write overall stats
            writer.writerow(['Overall', '---', '---', '---', '---', '---'])
            for idx, row in overall_pnl.iterrows():
                writer.writerow(['Overall', idx, f"{row['long']:.2f}", f"{row['short']:.2f}", f"{row['long_return']:.2f}", f"{row['short_return']:.2f}"])

            # Write monthly stats
            writer.writerow(['\nMonthly', '---', '---', '---', '---', '---'])
            for _, row in monthly_pnl_reset.iterrows():
                writer.writerow([row['month'].strftime('%Y-%m'), row['ticker'], f"{row['long']:.2f}", f"{row['short']:.2f}", f"{row['long_return']:.2f}", f"{row['short_return']:.2f}"])

    def _calculate_mdd(self, series):
        if series.empty: return 0.0
        rolling_max = series.cummax()
        drawdown = (series - rolling_max) / rolling_max * 100
        return drawdown.min()

    def _calculate_sharpe_ratio(self, series):
        """Calculate the Sharpe ratio from a series of values."""
        if series.empty: return 0.0
        
        daily_returns = series.pct_change().dropna()
        
        if daily_returns.empty or daily_returns.std() == 0:
            return 0.0
            
        # Annualized Sharpe Ratio
        return (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)

    def _compute_monthly_returns(self, series_df):
        if series_df.empty: return pd.Series()
        return series_df['value'].resample('M').ffill().pct_change().mul(100)

    def plot_monthly_returns(self):
        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')
        monthly_returns = self._compute_monthly_returns(portfolio_df)
        
        if monthly_returns.empty or monthly_returns.isnull().all():
            print("⚠️ Not enough data to generate monthly returns graph.")
            return

        fig, ax = plt.subplots(figsize=(14, 7))
        
        # Format x-axis labels to 'YYYY-MM'
        month_labels = monthly_returns.index.strftime('%Y-%m')
        colors = (monthly_returns.fillna(0) > 0).map({True: 'g', False: 'r'})

        ax.bar(month_labels, monthly_returns.fillna(0).values, color=colors)

        ax.set_title(LABELS['total_portfolio_monthly'])
        ax.set_ylabel(LABELS['returns'])
        
        # Rotate labels for better readability
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout() # Adjust plot to ensure everything fits without overlapping

        plt.savefig(self.results_dir / "monthly_returns.png")
        plt.close()

    def plot_mdd_trends(self):
        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')
        rolling_max = portfolio_df['value'].cummax()
        drawdown = (portfolio_df['value'] - rolling_max) / rolling_max * 100

        fig, ax = plt.subplots(figsize=(14, 7))
        ax.plot(drawdown.index, drawdown, color='r', label='Portfolio MDD')
        ax.fill_between(drawdown.index, drawdown, 0, color='r', alpha=0.3)
        ax.set_title(LABELS['total_portfolio_mdd'])
        ax.set_ylabel('Drawdown (%)')
        plt.savefig(self.results_dir / "mdd_trend.png")
        plt.close()
        
    def plot_returns_timeline(self):
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # Portfolio
        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')
        portfolio_returns = (portfolio_df['value'] / self.initial_capital - 1) * 100
        ax.plot(portfolio_returns.index, portfolio_returns, label='Total Portfolio', linewidth=3, color='black')
        
        # Per Coin
        for ticker in self.active_coins:
            coin_df = pd.DataFrame(self.portfolio_history_by_coin.get(ticker, [])).set_index('date')
            if coin_df.empty: continue
            base = self.strategy_investment / len(self.active_coins) if self.active_coins else 1
            if not base: continue
            coin_returns = (coin_df['value'] / base - 1) * 100
            ax.plot(coin_returns.index, coin_returns, label=ticker, alpha=0.7)
            
        ax.set_title(LABELS['returns_timeline_by_asset'])
        ax.set_ylabel(LABELS['returns'])
        ax.legend()
        ax.grid(True)
        plt.savefig(self.results_dir / "returns_timeline.png")
        plt.close()

    def generate_long_short_report(self):
        """Generate a detailed report of PNL for long and short positions."""
        print("✍️ Generating Long/Short performance report...")
        try:
            full_pnl = {}    # (ticker, side) -> pnl
            monthly_pnl = {} # (ticker, month, side) -> pnl

            for trade in self.trade_history:
                ticker = trade['ticker']
                side = trade['side'].lower()  # Convert to lowercase for consistency
                pnl = trade.get('pnl', 0)
                date = pd.to_datetime(trade['date'])
                month = date.strftime('%Y-%m')

                # Aggregate full period PNL
                full_pnl.setdefault((ticker, side), 0.0)
                full_pnl[(ticker, side)] += pnl

                # Aggregate monthly PNL
                monthly_pnl.setdefault((ticker, month, side), 0.0)
                monthly_pnl[(ticker, month, side)] += pnl

            base = self.strategy_investment / len(self.active_coins) if self.active_coins else 1

            with open(self.log_paths['long_short_csv'], 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # Write "Overall" section header
                writer.writerow(["Overall", "---", "---", "---", "---", "---"])
                
                # Write overall results for each coin
                for ticker in sorted(self.active_coins):
                    long_pnl = full_pnl.get((ticker, 'long'), 0.0)
                    short_pnl = full_pnl.get((ticker, 'short'), 0.0)
                    long_return = (long_pnl / base) * 100 if base != 0 else 0
                    short_return = (short_pnl / base) * 100 if base != 0 else 0
                    writer.writerow(["Overall", ticker, f"{long_pnl:.2f}", f"{short_pnl:.2f}", f"{long_return:.2f}", f"{short_return:.2f}"])
                
                # Write "Monthly" section header
                writer.writerow(['"', "---", "---", "---", "---", "---"])
                writer.writerow(['Monthly"', "---", "---", "---", "---", "---"])
                
                # Write monthly results
                all_months = sorted(set(month for (ticker, month, side) in monthly_pnl.keys()))
                for month in all_months:
                    for ticker in sorted(self.active_coins):
                        long_pnl = monthly_pnl.get((ticker, month, 'long'), 0.0)
                        short_pnl = monthly_pnl.get((ticker, month, 'short'), 0.0)
                        long_return = (long_pnl / base) * 100 if base != 0 else 0
                        short_return = (short_pnl / base) * 100 if base != 0 else 0
                        writer.writerow([month, ticker, f"{long_pnl:.2f}", f"{short_pnl:.2f}", f"{long_return:.2f}", f"{short_return:.2f}"])
            
            print(f"✅ Long/Short report saved to {self.log_paths['long_short_csv']}")
        except Exception as e:
            print(f"❌ Failed to generate Long/Short report: {e}")


def main():
    # Backtest Execution
    backtester = TurtleStrategyBacktester()
    backtester.run_backtest()

if __name__ == "__main__":
    main()
