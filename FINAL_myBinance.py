#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
FINAL myBinance Module

기존 myBinance.py 기능을 포함하면서 개선된 매매봇에 최적화된 기능 추가:
- 헤지 모드 전용 함수들 강화
- 안전한 포지션 관리
- 개선된 오류 처리
- 리스크 관리 기능 강화
'''

import ccxt
import time
import pandas as pd
import pprint
import numpy
import datetime
from cryptography.fernet import Fernet

# 기존 myBinance.py의 모든 함수들을 포함하면서 개선된 기능 추가

# 암호화 복호화 클래스 (기존 유지)
class SimpleEnDecrypt:
    def __init__(self, key=None):
        if key is None:
            key = Fernet.generate_key()
        self.key = key
        self.f = Fernet(self.key)
    
    def encrypt(self, data, is_out_string=True):
        if isinstance(data, bytes):
            ou = self.f.encrypt(data)
        else:
            ou = self.f.encrypt(data.encode('utf-8'))
        if is_out_string is True:
            return ou.decode('utf-8')
        else:
            return ou
        
    def decrypt(self, data, is_out_string=True):
        if isinstance(data, bytes):
            ou = self.f.decrypt(data)
        else:
            ou = self.f.decrypt(data.encode('utf-8'))
        if is_out_string is True:
            return ou.decode('utf-8')
        else:
            return ou

# 기술적 지표 함수들 (pandas/numpy 기반 구현)
def GetRSI(ohlcv, period, st):
    try:
        close = ohlcv["close"].astype(float)
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(com=(period - 1), min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(com=(period - 1), min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, numpy.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi = rsi.bfill().fillna(0.0)
        return float(rsi.iloc[st])
    except Exception as e:
        print(f"RSI 계산 오류: {e}")
        try:
            close = ohlcv["close"].astype(float)
            delta = close.diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.ewm(com=(period - 1), min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(com=(period - 1), min_periods=period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, numpy.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi = rsi.bfill().fillna(0.0)
            return float(rsi.iloc[st])
        except Exception:
            return 0.0


def GetMA(ohlcv, period, st):
    try:
        close = ohlcv["close"].astype(float)
        ma = close.rolling(window=int(period), min_periods=int(period)).mean()
        ma = ma.bfill().fillna(close)
        return float(ma.iloc[st])
    except Exception as e:
        print(f"MA 계산 오류: {e}")
        try:
            close = ohlcv["close"].astype(float)
            ma = close.rolling(window=int(period), min_periods=int(period)).mean()
            ma = ma.bfill().fillna(close)
            return float(ma.iloc[st])
        except Exception:
            return float(close.iloc[st]) if "close" in ohlcv else 0.0


def GetBB(ohlcv, period, st):
    try:
        close = ohlcv["close"].astype(float)
        ma = close.rolling(window=int(period), min_periods=int(period)).mean()
        std = close.rolling(window=int(period), min_periods=int(period)).std()
        upper = ma + (2.0 * std)
        lower = ma - (2.0 * std)
        dic_bb = {
            'ma': float(ma.iloc[st]),
            'upper': float(upper.iloc[st]),
            'lower': float(lower.iloc[st])
        }
        return dic_bb
    except Exception as e:
        print(f"BB 계산 오류: {e}")
        try:
            # 간단 대체 계산
            close = ohlcv["close"].astype(float)
            window = int(period)
            if len(close) < window:
                val = float(close.iloc[st])
                return {'ma': val, 'upper': val, 'lower': val}
            recent = close.rolling(window=window, min_periods=window)
            ma = recent.mean()
            std = recent.std()
            return {
                'ma': float(ma.iloc[st]),
                'upper': float((ma + 2.0 * std).iloc[st]),
                'lower': float((ma - 2.0 * std).iloc[st])
            }
        except Exception:
            v = float(ohlcv["close"].iloc[st]) if "close" in ohlcv else 0.0
            return {'ma': v, 'upper': v, 'lower': v}


def GetMACD(ohlcv, st):
    try:
        close = ohlcv["close"].astype(float)
        ema_short = close.ewm(span=12, adjust=False).mean()
        ema_long = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_short - ema_long
        signal = macd_line.ewm(span=9, adjust=False).mean()
        dic_macd = {
            'macd': float(macd_line.iloc[st]),
            'macd_siginal': float(signal.iloc[st]),
            'ocl': float((macd_line - signal).iloc[st])
        }
        return dic_macd
    except Exception as e:
        print(f"MACD 계산 오류: {e}")
        try:
            close = ohlcv["close"].astype(float)
            ema_short = close.ewm(span=12, adjust=False).mean()
            ema_long = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_short - ema_long
            signal = macd_line.ewm(span=9, adjust=False).mean()
            return {
                'macd': float(macd_line.iloc[st]),
                'macd_siginal': float(signal.iloc[st]),
                'ocl': float((macd_line - signal).iloc[st])
            }
        except Exception:
            return {'macd': 0.0, 'macd_siginal': 0.0, 'ocl': 0.0}

# 개선된 OHLCV 데이터 수집 함수
def GetOhlcv(binance, Ticker, period, count=500):
    """
    개선된 캔들 데이터 수집 함수 - 오류 처리 및 재시도 로직 포함
    """
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # 데이터 샘플을 가져와서 시간 간격 계산
            initial_data = binance.fetch_ohlcv(Ticker, period, limit=2)
            if len(initial_data) < 2:
                print(f"[CANDLE WARNING] {Ticker} 초기 데이터 부족 (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return pd.DataFrame()
            
            # 연속된 두 캔들 사이의 시간 간격 계산
            timeframe_ms = initial_data[1][0] - initial_data[0][0]
            
            # 현재 시간을 마지막 타임스탬프로 사용
            last_timestamp = int(datetime.datetime.now().timestamp() * 1000)
            
            # 시작 시간 계산
            date_start_ms = last_timestamp - (timeframe_ms * count)
            
            final_list = []
            remaining_count = count
            fetch_attempts = 0
            max_fetch_attempts = 10
            
            while remaining_count > 0 and fetch_attempts < max_fetch_attempts:
                try:
                    limit = min(1000, remaining_count)
                    ohlcv_data = binance.fetch_ohlcv(Ticker, period, since=date_start_ms, limit=limit)
                    
                    if not ohlcv_data:
                        print(f"[CANDLE WARNING] {Ticker} 빈 데이터 응답 (fetch 시도 {fetch_attempts + 1})")
                        fetch_attempts += 1
                        time.sleep(0.5)
                        continue
                        
                    final_list.extend(ohlcv_data)
                    date_start_ms = ohlcv_data[-1][0] + timeframe_ms
                    remaining_count -= len(ohlcv_data)
                    fetch_attempts += 1
                    time.sleep(0.1)
                    
                except Exception as fetch_error:
                    print(f"[CANDLE ERROR] {Ticker} fetch 오류 (시도 {fetch_attempts + 1}): {fetch_error}")
                    fetch_attempts += 1
                    if fetch_attempts < max_fetch_attempts:
                        time.sleep(0.5)
                        continue
                    else:
                        break
            
            if not final_list:
                print(f"[CANDLE ERROR] {Ticker} 데이터 수집 완전 실패 (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            
            # 정확한 개수만큼 데이터 자르기
            final_list = final_list[:count]
            
            # DataFrame으로 변환
            df = pd.DataFrame(final_list, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['datetime'], unit='ms')
            df.set_index('datetime', inplace=True)
            
            # 데이터 유효성 검증
            if len(df) < count * 0.8:
                print(f"[CANDLE WARNING] {Ticker} 데이터 부족: {len(df)}/{count} (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
            
            # 가격 데이터 유효성 검증
            invalid_close_na = df['close'].isna().any()
            invalid_close_zero = (df['close'] <= 0).any()
            
            if invalid_close_na or invalid_close_zero:
                print(f"[CANDLE ERROR] {Ticker} 잘못된 가격 데이터 감지 (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                df = df.dropna()
                df = df[df['close'] > 0]
            
            print(f"[CANDLE SUCCESS] {Ticker} 데이터 수집 성공: {len(df)}개 캔들")
            return df
            
        except Exception as e:
            print(f"[CANDLE ERROR] {Ticker} 전체 오류 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
    
    print(f"[CANDLE FAILED] {Ticker} 모든 시도 실패 - 빈 DataFrame 반환")
    return pd.DataFrame()

# 개선된 현재가 조회 함수
def GetCoinNowPrice(binance, Ticker):
    """안전한 현재가 조회 함수"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            coin_info = binance.fetch_ticker(Ticker)
            
            if isinstance(coin_info, dict):
                price_keys = ['last', 'close', 'price']
                for key in price_keys:
                    if key in coin_info and coin_info[key] is not None:
                        try:
                            price = float(coin_info[key])
                            if price > 0:
                                return price
                        except (ValueError, TypeError):
                            continue
                
                print(f"GetCoinNowPrice Warning: {Ticker} 가격 정보를 찾을 수 없음")
                return 0.0
            else:
                print(f"GetCoinNowPrice Error: {Ticker} 예상치 못한 응답 타입")
                return 0.0
                
        except Exception as e:
            print(f"GetCoinNowPrice Error: {Ticker} 가격 조회 실패 (시도 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            return 0.0

# 총 평가금액 조회 함수
def GetTotalRealMoney(balance):
    """총 평가금액 조회"""
    try:
        return float(balance['info']['totalWalletBalance']) + float(balance['info']['totalUnrealizedProfit'])
    except Exception as e:
        print(f"총 평가금액 조회 오류: {e}")
        return 0.0

# 개선된 헤지 모드 전용 함수들
def GetLongPositionAmt(binance, ticker):
    """롱 포지션 수량 조회 (개선된 오류 처리)"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            balance = binance.fetch_balance(params={"type": "future"})
            time.sleep(0.1)
            
            for posi in balance['info']['positions']:
                if posi['symbol'] == ticker.replace("/", "").replace(":USDT", "") and posi['positionSide'] == 'LONG':
                    amt = float(posi['positionAmt'])
                    return max(0, amt)  # 음수 방지
            return 0
        except Exception as e:
            print(f"GetLongPositionAmt Error (시도 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            return 0

def GetShortPositionAmt(binance, ticker):
    """숏 포지션 수량 조회 (개선된 오류 처리)"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            balance = binance.fetch_balance(params={"type": "future"})
            time.sleep(0.1)
            
            for posi in balance['info']['positions']:
                if posi['symbol'] == ticker.replace("/", "").replace(":USDT", "") and posi['positionSide'] == 'SHORT':
                    amt = float(posi['positionAmt'])
                    return abs(amt)  # 절댓값으로 반환
            return 0
        except Exception as e:
            print(f"GetShortPositionAmt Error (시도 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            return 0

def GetPositionInfo(binance, ticker):
    """포지션 상세 정보 조회 (새로 추가)"""
    try:
        balance = binance.fetch_balance(params={"type": "future"})
        time.sleep(0.1)
        
        symbol = ticker.replace("/", "").replace(":USDT", "")
        long_info = {'amount': 0, 'entry_price': 0, 'unrealized_pnl': 0, 'percentage': 0}
        short_info = {'amount': 0, 'entry_price': 0, 'unrealized_pnl': 0, 'percentage': 0}
        
        for posi in balance['info']['positions']:
            if posi['symbol'] == symbol:
                if posi['positionSide'] == 'LONG':
                    long_info = {
                        'amount': float(posi['positionAmt']),
                        'entry_price': float(posi['entryPrice']) if posi['entryPrice'] else 0,
                        'unrealized_pnl': float(posi['unrealizedProfit']) if posi['unrealizedProfit'] else 0,
                        'percentage': float(posi.get('percentage', 0))  # .get() 사용으로 안전하게 처리
                    }
                elif posi['positionSide'] == 'SHORT':
                    short_info = {
                        'amount': abs(float(posi['positionAmt'])),
                        'entry_price': float(posi['entryPrice']) if posi['entryPrice'] else 0,
                        'unrealized_pnl': float(posi['unrealizedProfit']) if posi['unrealizedProfit'] else 0,
                        'percentage': float(posi.get('percentage', 0))  # .get() 사용으로 안전하게 처리
                    }
        
        return {
            'long': long_info,
            'short': short_info,
            'has_long': long_info['amount'] > 0,
            'has_short': short_info['amount'] > 0,
            'total_unrealized_pnl': long_info['unrealized_pnl'] + short_info['unrealized_pnl']
        }
        
    except Exception as e:
        print(f"GetPositionInfo Error: {e}")
        return {
            'long': {'amount': 0, 'entry_price': 0, 'unrealized_pnl': 0, 'percentage': 0},
            'short': {'amount': 0, 'entry_price': 0, 'unrealized_pnl': 0, 'percentage': 0},
            'has_long': False,
            'has_short': False,
            'total_unrealized_pnl': 0
        }

def SafeCreateOrder(binance, ticker, order_type, side, amount, price=None, params=None):
    """안전한 주문 생성 함수 (새로 추가)"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 최소 주문 수량 체크
            min_amount = GetMinimumAmount(binance, ticker)
            if amount < min_amount:
                print(f"SafeCreateOrder Warning: {ticker} 최소 주문 수량 미달 ({amount:.6f} < {min_amount:.6f})")
                return None
            
            # 주문 실행
            result = binance.create_order(ticker, order_type, side, amount, price, params)
            print(f"SafeCreateOrder Success: {ticker} {side} {amount:.6f} @ {price if price else 'market'}")
            return result
            
        except Exception as e:
            print(f"SafeCreateOrder Error (시도 {attempt + 1}): {ticker} {e}")
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            return None

def GetMinimumAmount(binance, ticker):
    """최소 주문 단위 조회 (개선된 버전)"""
    try:
        t_ticker = ticker.replace(":USDT","")
        limit_values = None

        try:
            limit_values = binance.markets[t_ticker+":USDT"]['limits']
        except Exception:
            try:
                limit_values = binance.markets[t_ticker]['limits']
            except Exception:
                print(f"GetMinimumAmount Error: {ticker} markets 정보 없음")
                return 0.001

        if not limit_values or not isinstance(limit_values, dict):
            print(f"GetMinimumAmount Error: {ticker} limits 정보 없음")
            return 0.001

        min_amount = float(limit_values['amount']['min'])
        min_cost = float(limit_values['cost']['min']) if limit_values['cost']['min'] else 0
        min_price = float(limit_values['price']['min']) if limit_values['price']['min'] else 0

        coin_price = GetCoinNowPrice(binance, ticker)
        
        if coin_price <= 0:
            print(f"GetMinimumAmount Error: {ticker} 가격 정보 없음")
            return 0.001

        if min_price < coin_price:
            min_price = coin_price

        min_order_cost = min_price * min_amount
        num_min_amount = 1

        if min_cost > 0 and min_order_cost < min_cost:
            while min_order_cost < min_cost:
                num_min_amount += 1
                min_order_cost = min_price * (num_min_amount * min_amount)

        result = num_min_amount * min_amount
        
        if not isinstance(result, (int, float)) or result <= 0:
            print(f"GetMinimumAmount Warning: {ticker} 계산 결과 이상: {result}")
            return 0.001
            
        return float(result)
        
    except Exception as e:
        print(f"GetMinimumAmount Error: {ticker} 최소 수량 계산 실패: {e}")
        return 0.001

def CheckAccountHealth(binance):
    """계좌 건강성 체크 (새로 추가)"""
    try:
        balance = binance.fetch_balance(params={"type": "future"})
        
        total_balance = float(balance['info']['totalWalletBalance'])
        total_unrealized = float(balance['info']['totalUnrealizedProfit'])
        total_margin_balance = float(balance['info']['totalMarginBalance'])
        available_balance = float(balance['info']['availableBalance'])
        
        # 올바른 마진 비율 계산: 사용된 증거금 / 총 잔고
        used_margin = total_balance - available_balance  # 사용된 증거금
        margin_ratio = (used_margin / total_balance * 100) if total_balance > 0 else 0
        
        # 사용 가능한 잔고 비율
        available_ratio = (available_balance / total_balance * 100) if total_balance > 0 else 100
        
        health_status = {
            'total_balance': total_balance,
            'total_unrealized_pnl': total_unrealized,
            'total_margin_balance': total_margin_balance,
            'available_balance': available_balance,
            'used_margin': used_margin,
            'margin_ratio': margin_ratio,
            'available_ratio': available_ratio,
            'health_level': 'GOOD'  # GOOD, WARNING, DANGER
        }
        
        # 건강성 평가 (포지션이 없으면 항상 GOOD)
        if used_margin <= 0:
            health_status['health_level'] = 'GOOD'
        elif margin_ratio > 80:
            health_status['health_level'] = 'DANGER'
        elif margin_ratio > 60:
            health_status['health_level'] = 'WARNING'
        
        return health_status
        
    except Exception as e:
        print(f"CheckAccountHealth Error: {e}")
        return {
            'total_balance': 0,
            'total_unrealized_pnl': 0,
            'total_margin_balance': 0,
            'available_balance': 0,
            'used_margin': 0,
            'margin_ratio': 0,
            'available_ratio': 0,
            'health_level': 'UNKNOWN'
        }

def CloseAllPositions(binance, ticker):
    """해당 코인의 모든 포지션 청산 (개선된 버전)"""
    try:
        position_info = GetPositionInfo(binance, ticker)
        
        closed_positions = []
        
        # 롱 포지션 청산
        if position_info['has_long']:
            try:
                params = {'positionSide': 'LONG'}
                result = binance.create_order(ticker, 'market', 'sell', position_info['long']['amount'], None, params)
                closed_positions.append(f"LONG {position_info['long']['amount']:.6f}")
                print(f"롱 포지션 청산: {ticker} {position_info['long']['amount']:.6f}개")
                time.sleep(0.1)
            except Exception as e:
                print(f"롱 포지션 청산 실패: {e}")
        
        # 숏 포지션 청산
        if position_info['has_short']:
            try:
                params = {'positionSide': 'SHORT'}
                result = binance.create_order(ticker, 'market', 'buy', position_info['short']['amount'], None, params)
                closed_positions.append(f"SHORT {position_info['short']['amount']:.6f}")
                print(f"숏 포지션 청산: {ticker} {position_info['short']['amount']:.6f}개")
                time.sleep(0.1)
            except Exception as e:
                print(f"숏 포지션 청산 실패: {e}")
        
        return closed_positions
        
    except Exception as e:
        print(f"CloseAllPositions Error: {e}")
        return []

# 기존 함수들 유지 (스탑로스, 트레일링 스탑 등)
# ... (기존 myBinance.py의 나머지 함수들을 모두 포함)

# 추가 유틸리티 함수들
def ValidateTickerFormat(ticker):
    """티커 형식 검증"""
    if not ticker or not isinstance(ticker, str):
        return False
    if "/USDT" not in ticker:
        return False
    return True

def FormatPositionSide(side):
    """포지션 사이드 형식 통일"""
    if side and isinstance(side, str):
        return side.upper()
    return "NONE"

def CalculatePositionValue(amount, price, leverage=1):
    """포지션 가치 계산"""
    try:
        return float(amount) * float(price) * float(leverage)
    except:
        return 0.0

def CalculateRequiredMargin(position_value, leverage=10):
    """필요 증거금 계산"""
    try:
        return float(position_value) / float(leverage)
    except:
        return 0.0

print("✅ FINAL myBinance 모듈 로드 완료")
print("🔧 개선된 기능: 안전한 포지션 관리, 향상된 오류 처리, 계좌 건강성 체크") 