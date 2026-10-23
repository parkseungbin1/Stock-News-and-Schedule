# 📑 BiniStock 주식 알림 시스템 전면 개편 및 고도화 작업 완료 보고서

> **작성 일시**: 2026-10-23  
> **프로젝트**: `parkseungbin1/Stock-News-and-Schedule`  
> **환경**: 100% 클라우드 서버리스 (GitHub Actions + cron-job.org), PC 전원 무관 동작  

---

## 1. 🔍 문제 진단 및 분석 (Before)

### 기존 문제점
1. **극심한 알림 지연 (뒷북 알림)**:
   - 07:40, 08:40에 도착해야 할 장전 매도 가이드가 장이 이미 시작한 **09:27, 09:53, 10:58**에 도착.
   - 이미 개장한 후 전송되어 실전 매매에 전혀 활용 불가능.
2. **알림 뭉침 및 폭탄 발송**:
   - 시간대별로 따로따로 와야 할 알림들이 몇 시간 밀렸다가 한꺼번에 우르르 도착.
3. **불필요한 중복 & 스팸 메시지**:
   - 07:00 날씨 브리핑에 시장 점수가 중복으로 포함됨.
   - 공시가 없는 날에도 "오늘 예정된 IR 공시가 없습니다" 스팸 발송.
4. **로컬 PC 의존성 문제**:
   - 사용자가 외부에서 스마트폰으로만 매매하는 환경인데, 로컬 PC 스케줄러는 PC가 꺼지면 작동하지 않음.

### 지연의 기술적 원인 분석
* **GitHub Actions `schedule:` 무료 큐 지연**:
  - 한국 시각 아침 07:00~09:00은 전 세계 UTC 00시 전후로, 전 세계 깃허브 크론 작업이 몰려 무료 러너 대기열(Queue Delay)이 1시간 30분~2시간 30분 발생.
* **만료 가드(Expiration Guard) 부재**:
  - 지연 실행되었을 때 시간이 지난 것을 감지하고 스스로 취소하는 로직이 없어, 10시가 넘어도 07:40 메시지를 그대로 텔레그램으로 쏘아 올림.
* **동시 빌드 큐 병목**:
  - `deploy-web.yml` 웹 대시보드 빌드가 07:40, 08:40 동일한 시각에 예약되어 있어 리포지토리 동시 실행 한도를 잠식함.

---

## 2. 🛠️ 단행된 핵심 개편 및 솔루션 (After)

```
[cron-job.org 외부 클라우드 크론]
       │
       │ (정각에 지연 0초 즉시 POST 호출)
       ▼
[GitHub Actions : smart-alert.yml]
       │
       │ (스마트 디스패처 실행)
       ▼
[scripts/smart_dispatcher.py]
  ├── ① 주말(토/일) 검사 ──> 주말이면 1초 만에 자동 스킵
  ├── ② 시간 만료 가드 ──> 지연 발생 시 뒷북 알림 원천 차단
  └── ③ KST 시각 / 액션 파라미터 판별
       ├── 07:00 ──> daily_digest.py (날씨 + 경제 캘린더)
       ├── 07:40 ──> market_alert.py --mode morning_740 (08:00 프리마켓 가이드)
       ├── 08:10 ──> disclosure_alert.py --morning (DART IR/주요공시)
       ├── 08:40 ──> market_alert.py --mode morning_840 (09:00 정규장 개장 가이드)
       ├── 15:10 ──> market_alert.py --mode closing (종가베팅 + AI 주도주 TOP 3)
       └── 19:40 ──> market_alert.py --mode night (야간마켓 종가베팅 가이드)
```

### ① 지연 0초 '클라우드 즉시 트리거' 도입 (`cron-job.org` + `workflow_dispatch`)
- 무료 외부 크론([cron-job.org](https://cron-job.org))이 정해진 시각에 GitHub Actions API(`workflow_dispatch`)를 호출.
- `workflow_dispatch`는 GitHub 내부 `schedule:`과 달리 **우선순위가 가장 높아 대기 시간 0~5초 만에 러너가 즉시 할당되어 실행**됨.
- PC를 켜둘 필요 없이 100% 클라우드에서 24시간 365일 정시 발송.

### ② 통합 관제탑 `scripts/smart_dispatcher.py` 및 워크플로우 구축
- 단일 워크플로우([.github/workflows/smart-alert.yml](file:///c:/Users/BINI/Desktop/news-stock/.github/workflows/smart-alert.yml))에서 6대 알림을 모두 처리.
- 시간대별 자동 라우팅뿐만 아니라, `inputs: {"action": "..."}`을 지원하여 **언제든 각 알림을 수동 개별 테스트 가능**하도록 설계.
- **주말(토/일) 자동 스킵 가드**: 토요일, 일요일은 증시 휴장이므로 서버에서 즉시 발송 스킵.

### ③ 엄격한 만료 가드 (Expiration Guard) 적용
- [market_alert.py](file:///c:/Users/BINI/Desktop/news-stock/market_alert.py) 내부에 세션별 한계 시간 가드 장착:
  - 07:40 알림: 08:05 이후 실행 시 자동 취소
  - 08:40 알림: 09:05 이후 실행 시 자동 취소
  - 15:10 알림: 15:35 이후 실행 시 자동 취소
  - 19:40 알림: 20:05 이후 실행 시 자동 취소
- 어떠한 클라우드 지연이 발생해도 **"뒷북 알림"이 사용자에게 전송되는 일 원천 봉쇄**.

### ④ 메시지 품질 및 종목 추천 엔진 고도화
- **07:00 브리핑 중복 제거**: [daily_digest.py](file:///c:/Users/BINI/Desktop/news-stock/daily_digest.py)에서 중복 시장 점수를 빼고 '날씨 + 경제 캘린더' 본연의 가독성 극대화.
- **공시 알림 최적화**: [disclosure_alert.py](file:///c:/Users/BINI/Desktop/news-stock/disclosure_alert.py)에서 공시가 없을 때의 불필요한 스팸 메시지 차단.
- **AI 종가베팅 주도주 TOP 3 탑재**: 15:10 및 19:40 알림 시 `recommender.py`의 퀀트 필터(거래대금 폭발 + 윗꼬리 억제 + DART 공시 연동)를 통과한 **당일 최강 주도주 TOP 3**를 실시간 분석해 함께 전송.

### ⑤ 중복 발송 요소 완전 제거
- `market-score.yml`, `daily-telegram.yml`, `disclosure-alert.yml` 내부의 지연 유발 내부 `schedule: cron` 트리거 제거.
- 로컬 Windows 작업 스케줄러에 등록되어 있던 구버전 작업 4건 영구 삭제.

---

## 3. 🕒 완성된 6대 정시 알림 체계

| 번호 | 알림 시간 | 알림 명칭 | 발송 내용 및 목적 |
| :---: | :---: | :--- | :--- |
| **01** | **07:00** | 모닝 브리핑 | ☀️ 서울 날씨/주간 예보 + 당일 글로벌 경제 캘린더 |
| **02** | **07:40** | NXT 프리마켓 가이드 | ⏰ 08:00 Nextrade 개장 전 1차 시초가 매도 타이밍 점검 |
| **03** | **08:10** | 장전 주요 공시 | 📋 당일 장 시작 전 DART 실적 발표(IR) 및 주요 공시 요약 |
| **04** | **08:40** | 정규장 개장 가이드 | 🚀 09:00 정규장 개장 직전 동시호가 & 최종 시초가 매도 가이드 |
| **05** | **15:10** | 정규장 종가베팅 | 🎯 15:30 마감 전 **AI 종가베팅 주도주 TOP 3** + 시장 레짐 판정 |
| **06** | **19:40** | NXT 야간마켓 가이드 | 🌙 20:00 Nextrade 야간 거래 종료 20분 전 최종 오버나잇 판정 |

*(토/일요일은 증시 휴장일로 자동 스킵)*

---

## 4. 🗂️ 주요 변경/생성 파일 일람

| 파일 경로 | 작업 내용 |
| :--- | :--- |
| [src/recommender.py](file:///c:/Users/BINI/Desktop/news-stock/src/recommender.py) | **[STEP 1]** 실시간 1위 뉴스(재료) 및 업종/테마 자동 추출, 모바일 차트 링크 탑재 |
| [src/track_record.py](file:///c:/Users/BINI/Desktop/news-stock/src/track_record.py) | **[STEP 4]** 전일 종가베팅 종목 익일 시초가 갭상승 자동 추적 및 누적 승률 산출 |
| [src/market_score.py](file:///c:/Users/BINI/Desktop/news-stock/src/market_score.py) | 모바일 네이버 증권 원클릭 차트/호가 링크 & 아침 트랙 레코드 성과 피드백 연동 |
| [.github/workflows/smart-alert.yml](file:///c:/Users/BINI/Desktop/news-stock/.github/workflows/smart-alert.yml) | cron-job.org 연동용 단일 워크플로우 (상태 캐시 복원 및 디스패처 실행) |
| [scripts/smart_dispatcher.py](file:///c:/Users/BINI/Desktop/news-stock/scripts/smart_dispatcher.py) | KST 시간대 자동 분기, 수동 액션 처리, 주말 스킵 가드 |
| [market_alert.py](file:///c:/Users/BINI/Desktop/news-stock/market_alert.py) | 세션별 만료 가드 장착, `--mode` 세분화 및 AI 주도주 연동 |
| [daily_digest.py](file:///c:/Users/BINI/Desktop/news-stock/daily_digest.py) | 중복 시장 점수 제거, 날씨+경제 캘린더 전용 분리 |
| [disclosure_alert.py](file:///c:/Users/BINI/Desktop/news-stock/disclosure_alert.py) | 공시 미발생 시 스팸 억제 로직 추가 |
| [CRON_SETUP_GUIDE.md](file:///c:/Users/BINI/Desktop/news-stock/CRON_SETUP_GUIDE.md) | 외부 스케줄러(cron-job.org) 세부 관리 가이드 및 복구 cURL 모음 |
| [크론잡_스케줄러_관리(cron-job.org).url](file:///c:/Users/BINI/Desktop/news-stock/%ED%81%AC%EB%A1%A0%EC%9E%A1_%EC%8A%A4%EC%BC%80%EC%A4%84%EB%9F%AC_%EA%B4%80%EB%A6%AC%28cron-job.org%29.url) | 더블 클릭 시 cron-job.org 대시보드로 즉시 이동하는 바로가기 |
| [README.md](file:///c:/Users/BINI/Desktop/news-stock/README.md) | 최상단에 스케줄러 가이드 배너 및 문서 링크 추가 |
| [.env](file:///c:/Users/BINI/Desktop/news-stock/.env) | 로컬 GitHub 토큰 및 스케줄러 관리 링크 안전 보관 (.gitignore) |

---

## 5. 🚀 고도화 완료 및 향후 추가 제안

- ✅ **[완료] STEP 1. 실시간 재료 & 테마 자동 추출**:
  - 네이버 증권 모바일 뉴스 API에서 당일 1등 뉴스 헤드라인(`📰 핵심재료`) 추출 및 업종(`🏷️ [반도체]`, `[2차전지]` 등) 자동 태깅 완료.
- ✅ **[완료] STEP 4. 전일 종가베팅 성과(트랙 레코드) 자동 검증**:
  - `state/betting_track_record.json` 기반 익일 시초가 갭상승 수익률 및 성공률 자동 계산, 아침 알림에 피드백 탑재 완료.
- ✅ **[완료] 모바일 네이버 증권 원클릭 차트/호가 링크**:
  - 텔레그램 메시지 내 종목명 또는 링크 터치 시 실시간 모바일 일봉/호가창으로 즉시 이동 연동 완료.
- 💡 **[향후 제안] 외인·기관 수급 쌍끌이 가중치 필터**:
  - 네이버 종목별 실시간 수급 API 연동 가산점 부여.

---
*보고서 최신 갱신 완료: 프로젝트 루트의 `PROJECT_WORK_REPORT.md`에서 언제든 확인 가능합니다.*
