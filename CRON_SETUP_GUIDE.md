# ⏰ BiniStock 자동 알림 스케줄러 관리 가이드 (cron-job.org)

> **"내가 크론을 어디서 돌리고 있더라?" 싶을 때 이 문서를 확인하세요.**

---

## 📌 핵심 요약
* **스케줄러 서비스**: [cron-job.org](https://cron-job.org) (무료 외부 웹 크론)
* **관리 페이지**: [https://cron-job.org/en/members/cronjobs/](https://cron-job.org/en/members/cronjobs/)
* **역할**: GitHub Actions의 무료 티어 지연(1~2시간 밀림)을 없애고, **정해진 시간에 1초의 오차 없이 GitHub Actions(`smart-alert.yml`)를 즉시 실행**시켜 텔레그램을 발송합니다.
* **장점**: 내 PC를 꺼두어도 100% 클라우드 무료 서버에서 24시간 365일 정시 발송됩니다.

---

## 🕒 등록된 6대 알림 스케줄

| 번호 | 알림 이름 | 실행 시각 (KST) | 발송 내용 |
| :---: | :--- | :---: | :--- |
| **01** | `01. 07:00 모닝 브리핑` | **07:00** | ☀️ 오늘 날씨 + 주간 글로벌 경제 캘린더 |
| **02** | `02. 07:40 프리마켓 가이드` | **07:40** | ⏰ 08:00 NXT 개장 전 1차 시초가 매도 가이드 |
| **03** | `03. 08:10 장전 공시 요약` | **08:10** | 📋 당일 장전 주요 IR / DART 실적 공시 |
| **04** | `04. 08:40 정규장 개장 가이드` | **08:40** | 🚀 09:00 정규장 개장 전 최종 시초가 가이드 |
| **05** | `05. 15:10 종가베팅 가이드` | **15:10** | 🎯 15:30 정규장 종가베팅 + **AI 주도주 TOP 3** |
| **06** | `06. 19:40 야간마켓 가이드` | **19:40** | 🌙 20:00 NXT 야간마켓 최종 종가베팅 가이드 |

*(토요일/일요일은 주식 시장 휴장이므로 서버에서 자동으로 발송을 스킵합니다.)*

---

## 🛠 관리 및 수정 방법

### 1. 알림을 잠시 멈추고 싶을 때 (휴가, 휴장일 등)
1. [cron-job.org](https://cron-job.org) 로그인
2. 목록에서 해당 알림의 **초록색 토글 스위치(Enabled)**를 클릭하여 끄면(Disabled) 즉시 일시 정지됩니다.

### 2. 알림 시간을 바꾸고 싶을 때
1. 해당 알림 오른쪽 **`ACTIONS` $\rightarrow$ `Edit`** 클릭
2. **`COMMON`** 탭에서 `Every day at [시] : [분]` 변경 후 **`SAVE`**

### 3. 알림이 잘 오는지 즉시 테스트해보고 싶을 때
1. 해당 알림 오른쪽 **`ACTIONS` $\rightarrow$ `Edit`** 클릭
2. 화면 하단 **`TEST RUN`** 버튼 클릭 $\rightarrow$ 5~10초 내 텔레그램 도착 확인

---

## 📋 cURL 복구 백업 (필요 시 복사해서 바로 사용)

혹시 크론잡이 삭제되었거나 새로 만들 때는 cron-job.org에서 **`CREATE CRONJOB` $\rightarrow$ `<> IMPORT FROM CURL`**을 누르고 아래 명령어를 넣으시면 됩니다:

<details>
<summary><b>▼ 6개 알림별 cURL 백업 펼치기</b></summary>

**01. 07:00 모닝 브리핑**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"digest_0700"}}'
```

**02. 07:40 프리마켓 가이드**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"morning_735"}}'
```

**03. 08:10 장전 공시 요약**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"disclosure_0810"}}'
```

**04. 08:40 정규장 개장 가이드**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"morning_835"}}'
```

**05. 15:10 종가베팅 가이드**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"closing_1510"}}'
```

**06. 19:40 야간마켓 가이드**
```bash
curl -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token <YOUR_GITHUB_TOKEN_FROM_ENV>" https://api.github.com/repos/parkseungbin1/Stock-News-and-Schedule/actions/workflows/smart-alert.yml/dispatches -d '{"ref":"main", "inputs":{"action":"night_1940"}}'
```

</details>
