#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
FINAL Discord Alert Module

개선된 디스코드 알림 모듈:
- 환경변수 지원 (.env 파일)
- 향상된 오류 처리
- 메시지 포맷팅 개선
- 재시도 로직 추가
'''

import requests
import os
from datetime import datetime
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(dotenv_path: str = ".env"):
        env_path = dotenv_path
        if not os.path.isabs(env_path):
            env_path = os.path.join(os.getcwd(), env_path)
        if not os.path.exists(env_path):
            return
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass

# 환경변수 로드
load_dotenv()

# Discord 웹훅 URL 설정 (환경변수 우선, 없으면 기본값 사용)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL') or "https://discord.com/api/webhooks/993868624957800490/a6pvQp8c2mgrQKyZZicwYnsnSQ9pL2Ehm-j2DEyTfldj2XAqEhrbEo991suLj6R5TIr_"

def SendMessage(msg, max_retries=3):
    """
    디스코드로 메시지 전송
    
    Args:
        msg (str): 전송할 메시지
        max_retries (int): 최대 재시도 횟수
    
    Returns:
        bool: 전송 성공 여부
    """
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        print("⚠️ Discord 웹훅 URL이 설정되지 않았습니다.")
        return False
    
    # 메시지 포맷팅
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"🤖 **FINAL Enhanced Trading Bot** | {timestamp}\n{msg}"
    
    # 메시지 길이 제한 (Discord 제한: 2000자)
    if len(formatted_message) > 1900:  # 여유분 100자
        formatted_message = formatted_message[:1900] + "... (메시지 길이 초과로 잘림)"
    
    for attempt in range(max_retries):
        try:
            payload = {
                "content": formatted_message,
                "username": "FINAL Trading Bot",
                "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
            
            response = requests.post(
                DISCORD_WEBHOOK_URL, 
                json=payload,
                timeout=10
            )
            
            if response.status_code == 204:
                print(f"✅ Discord 알림 전송 성공: {msg[:50]}...")
                return True
            elif response.status_code == 429:
                # Rate limit 처리
                retry_after = response.json().get('retry_after', 1)
                print(f"⚠️ Discord Rate limit - {retry_after}초 대기 후 재시도")
                import time
                time.sleep(retry_after)
                continue
            else:
                print(f"❌ Discord 알림 전송 실패 (시도 {attempt + 1}/{max_retries}): HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"⏰ Discord 알림 타임아웃 (시도 {attempt + 1}/{max_retries})")
        except requests.exceptions.ConnectionError:
            print(f"🌐 Discord 연결 오류 (시도 {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"❌ Discord 알림 오류 (시도 {attempt + 1}/{max_retries}): {e}")
        
        # 재시도 전 대기
        if attempt < max_retries - 1:
            import time
            time.sleep(1 * (attempt + 1))  # 점진적 대기시간 증가
    
    print(f"❌ Discord 알림 전송 최종 실패: {msg[:50]}...")
    return False

def SendTradingAlert(ticker, action, amount, price, pnl=None):
    """
    거래 전용 알림 (구조화된 메시지)
    
    Args:
        ticker (str): 코인 티커
        action (str): 거래 액션 (BUY, SELL, CLOSE 등)
        amount (float): 거래 수량
        price (float): 거래 가격
        pnl (float, optional): 손익
    """
    emoji_map = {
        'BUY': '🟢',
        'SELL': '🔴', 
        'CLOSE_LONG': '🟡',
        'CLOSE_SHORT': '🟡',
        'OPEN_LONG': '🟢',
        'OPEN_SHORT': '🔴'
    }
    
    emoji = emoji_map.get(action, '⚪')
    
    message = f"{emoji} **{action}** {ticker}\n"
    message += f"📊 수량: {amount:.6f}\n"
    message += f"💰 가격: ${price:.2f}"
    
    if pnl is not None:
        pnl_emoji = "📈" if pnl > 0 else "📉"
        message += f"\n{pnl_emoji} 손익: ${pnl:.2f}"
    
    return SendMessage(message)

def SendSystemAlert(level, message):
    """
    시스템 알림 (레벨별 구분)
    
    Args:
        level (str): 알림 레벨 (INFO, WARNING, ERROR, CRITICAL)
        message (str): 알림 메시지
    """
    level_emoji = {
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    emoji = level_emoji.get(level.upper(), 'ℹ️')
    formatted_msg = f"{emoji} **{level.upper()}**\n{message}"
    
    return SendMessage(formatted_msg)

def TestConnection():
    """
    Discord 연결 테스트
    """
    test_message = "🧪 FINAL Enhanced Trading Bot 연결 테스트"
    success = SendMessage(test_message)
    
    if success:
        print("✅ Discord 연결 테스트 성공!")
    else:
        print("❌ Discord 연결 테스트 실패!")
    
    return success

# 하위 호환성을 위한 별칭
send_message = SendMessage  # 소문자 버전
sendMessage = SendMessage   # 카멜케이스 버전

if __name__ == "__main__":
    # 테스트 실행
    print("🧪 FINAL Discord Alert 모듈 테스트")
    TestConnection()
    
    # 거래 알림 테스트
    SendTradingAlert("BTC/USDT", "OPEN_LONG", 0.001, 50000, 100)
    
    # 시스템 알림 테스트
    SendSystemAlert("INFO", "매매봇이 성공적으로 시작되었습니다.")
    
    print("✅ 테스트 완료!") 