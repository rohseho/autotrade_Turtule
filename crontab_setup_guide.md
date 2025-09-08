# 🕐 Turtle Trading Bot 크론탭 설정 가이드

## 📋 개요
실제 매매봇을 12시간마다 자동 실행하기 위한 크론탭 설정 가이드입니다.

## ⚙️ 크론탭 설정

### 1. 크론탭 편집
```bash
crontab -e
```

### 2. 크론탭 규칙 추가
```bash
# Turtle Trading Strategy C Bot - 매일 오전 9시, 오후 9시 실행
0 9,21 * * * cd /path/to/Seho_BackTesting && /usr/bin/python3 Turtule_trading_Stratgy_C.py >> logs/cron.log 2>&1
```

### 3. 설정 설명
- `0 9,21 * * *`: 매일 09:00, 21:00에 실행 (12시간 간격)
- `cd /path/to/Seho_BackTesting`: 프로젝트 디렉토리로 이동
- `/usr/bin/python3`: Python3 실행 경로
- `>> logs/cron.log 2>&1`: 로그 파일에 출력 저장

### 4. 경로 설정 예시
```bash
# 실제 경로로 수정 필요
0 9,21 * * * cd /home/user/crypto-trading/Seho_BackTesting && /usr/bin/python3 Turtule_trading_Stratgy_C.py >> logs/cron.log 2>&1
```

## 📁 필요한 디렉토리 생성
```bash
mkdir -p logs
```

## 🔍 크론탭 상태 확인
```bash
# 현재 크론탭 목록 확인
crontab -l

# 크론 서비스 상태 확인
sudo systemctl status cron

# 크론 로그 확인
tail -f logs/cron.log
```

## ⚠️ 주의사항
1. **환경변수**: `.env` 파일이 프로젝트 루트에 있어야 함
2. **권한**: 실행 권한 확인 (`chmod +x Turtule_trading_Stratgy_C.py`)
3. **Python 경로**: 시스템의 Python 경로 확인 (`which python3`)
4. **타임존**: 서버 시간대 확인 (UTC vs KST)

## 🧪 테스트 실행
```bash
# 수동 테스트 실행
cd /path/to/Seho_BackTesting
python3 Turtule_trading_Stratgy_C.py
```

## 📊 로그 모니터링
```bash
# 실시간 로그 확인
tail -f logs/cron.log

# 최근 실행 결과 확인
tail -50 logs/cron.log
```
