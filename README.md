# Stock-News-and-Schedule

네이버 증권 stock.naver.com의 경제 지표 API와 날씨 API를 이용해, 매일 아침 텔레그램으로 날씨와 경제 지표를 함께 전송하는 봇입니다.

## 기능

- 📊 네이버 증권 stock.naver.com 경제 지표 API에서 데이터 크롤링
- 🌤 서울 기준 날씨 정보와 3일 예보 자동 수집
- 🎯 시장 영향력 "매우 높음" 지표만 필터링
- 📅 1주일치 경제 지표 자동 수집
- 💬 매일 아침 6시(KST, 설정 가능)에 텔레그램으로 자동 전송
- 🔄 백그라운드에서 지속적으로 실행

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 텔레그램 봇 설정

텔레그램 봇을 생성하고 토큰을 얻어야 합니다.

1. **BotFather와 채팅** (Telegram에서 `@BotFather`를 찾음)
2. `/start` 또는 `/newbot` 명령어로 새로운 봇 생성
3. 봇 이름과 사용자명 설정
4. 받은 **토큰**을 복사
5. 봇과 1:1 채팅 시작
6. 자신의 **Chat ID** 확인하는 방법:
   - 봇에게 메시지 전송
   - `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`에 접속
   - JSON 응답에서 `message.chat.id` 값 확인

### 3. 환경 변수 설정

`.env` 파일을 생성하고 다음을 입력하세요:

```env
# 필수 설정
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# 선택 설정
SCHEDULE_HOUR=7          # 전송 시간 (기본값: 7시)
SCHEDULE_MINUTE=0        # 전송 분 (기본값: 0분)
WEATHER_CITY=서울
WEATHER_LATITUDE=37.5665
WEATHER_LONGITUDE=126.9780
WEATHER_TIMEZONE=Asia/Seoul
LOG_LEVEL=INFO          # 로깅 레벨
DATA_DAYS=7             # 조회 기간 (기본값: 7일)
```

## 사용 방법

### 일반 실행

```bash
python main.py
```

프로그램이 백그라운드에서 실행되며, 매일 설정된 시간(기본값 07:00)에 날씨와 경제 캘린더를 함께 전송합니다.

### 크롤러 테스트

```bash
python test_crawler.py
```

네이버 증권 stock.naver.com에서 데이터를 실제로 크롤링하여 결과를 확인할 수 있습니다.

### 텔레그램 전송 테스트

```bash
python test_telegram.py
```

날씨와 크롤링된 경제 데이터를 텔레그램으로 실제로 전송하여 테스트합니다.

### GitHub Actions로 매일 자동 실행

이 저장소는 GitHub Actions 스케줄로 매일 아침 6시에 자동 실행할 수 있습니다.

1. GitHub 저장소의 `Settings` > `Secrets and variables` > `Actions`로 이동합니다.
2. `New repository secret`를 눌러 다음 시크릿을 각각 추가합니다.
   - `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
   - `TELEGRAM_CHAT_ID`: 메시지를 받을 채팅 ID
3. `Actions` 탭에서 `Daily Telegram Digest`는 매일 자동 실행되고, `Manual Setup Check`는 필요할 때 직접 실행해서 점검할 수 있습니다.

점검용 워크플로우는 다음을 확인합니다.

- 시크릿이 실제로 등록되어 있는지
- 날씨 API와 경제 지표 API가 정상 동작하는지

점검 후 텔레그램까지 실제로 보내고 싶으면 `Daily Telegram Digest` 워크플로우의 `Run workflow`를 눌러 수동 실행하면 됩니다.

주의: GitHub Actions의 `cron`은 UTC 기준입니다. 현재 설정은 한국시간(KST) 오전 6시를 기준으로 `21:00 UTC`에 실행되도록 되어 있습니다.

## 프로젝트 구조

```
Stock-News-and-Schedule/
├── main.py              # 메인 실행 파일
├── requirements.txt     # 의존성 목록
├── .env.example         # 환경 변수 예제
├── .env                 # 환경 변수 (Git에 포함되지 않음)
├── test_crawler.py      # 크롤러 테스트
├── test_telegram.py     # 텔레그램 전송 테스트
├── src/
│   ├── __init__.py
│   ├── config.py        # 설정 관리
│   ├── logger.py        # 로깅 설정
│   ├── crawler.py       # 네이버 증권 크롤러
│   ├── scheduler.py     # APScheduler 기반 스케줄링
│   └── telegram_sender.py  # 텔레그램 전송
└── README.md            # 이 파일
```

## 주요 모듈 설명

### crawler.py
- `EconomicCalendarCrawler`: 네이버 증권 경제 지표 API를 크롤링
  - `get_economic_calendar_data()`: 모든 경제 지표 데이터 수집
  - `filter_high_impact_events()`: 시장 영향력 "매우 높음" 필터링
  - `format_events_for_message()`: 메시지 형식으로 변환

### weather.py
- `WeatherService`: Open-Meteo를 사용해 날씨와 3일 예보를 조회
  - `fetch_weather()`: 현재 날씨와 일별 예보 수집
  - `format_weather_for_message()`: 텔레그램 메시지 형식으로 변환

### scheduler.py
- `EconomicCalendarScheduler`: APScheduler를 사용한 일정 관리
  - 매일 설정된 시간에 자동으로 경제 캘린더 전송
  - 로그 기록 및 오류 처리

### telegram_sender.py
- `TelegramSender`: python-telegram-bot 기반 메시지 전송
  - 비동기 및 동기식 전송 지원
  - 오류 처리 및 재시도 기능

## 로그 관리

프로그램 실행 중 로그는 다음 위치에 저장됩니다:
- **콘솔**: 실시간 출력
- **파일**: `economic_calendar.log` (자동 로테이션)

로그 레벨 설정:
- `DEBUG`: 상세한 디버깅 정보
- `INFO`: 일반 정보
- `WARNING`: 경고
- `ERROR`: 오류

## 문제 해결

### 1. 텔레그램 메시지가 전송되지 않는 경우
- `.env` 파일에서 `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID` 확인
- 봇이 채팅에서 차단되지 않았는지 확인
- 인터넷 연결 상태 확인

### 2. 크롤링 오류가 발생하는 경우
- 네이버 증권 웹사이트 상태 확인
- User-Agent 업데이트 확인
- `.env`에서 `USER_AGENT` 값 확인

### 3. 스케줄이 실행되지 않는 경우
- 프로그램이 백그라운드에서 실행 중인지 확인
- 시스템 시간 설정 확인
- 로그 파일에서 오류 메시지 확인

## 배포 (선택)

### systemd 서비스로 등록 (Linux)

`/etc/systemd/system/economic-calendar.service` 생성:

```ini
[Unit]
Description=Economic Calendar Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/Stock-News-and-Schedule
ExecStart=/usr/bin/python3 /path/to/Stock-News-and-Schedule/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

활성화:
```bash
sudo systemctl enable economic-calendar
sudo systemctl start economic-calendar
```

### Docker (선택)

`Dockerfile` 예제:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["python", "main.py"]
```

빌드 및 실행:
```bash
docker build -t economic-calendar .
docker run -d --env-file .env economic-calendar
```

## 라이선스

MIT License

## 기여

버그 리포트나 기능 제안은 Issues를 통해 제출해주세요.

## 주의사항

- 네이버 증권의 로봇 차단 정책을 확인하고 적절한 크롤링 간격을 유지하세요
- 개인적인 용도로만 사용해주세요
- 텔레그램 봇 토큰은 절대 공개하지 마세요
- `.env.example`에는 실제 토큰 대신 예시값만 사용하세요

## 업데이트 로그

### v1.0.0 (2024)
- 초기 버전 출시
- 네이버 증권 경제 캘린더 크롤링 기능
- 텔레그램 자동 전송 기능
- APScheduler 기반 스케줄링
