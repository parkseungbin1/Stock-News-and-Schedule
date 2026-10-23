"""
종가베팅 사후 성과 자동 추적 및 승률 통계 모듈 (Track Record)
1. 당일 15:10 추천 종목(종가) 저장
2. 익일 시초가(Open) 확인하여 갭상승 수익률 및 성공(익절/손절) 여부 자동 판정
3. 최근 누적 승률(Track Record) 산출
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
RECORD_FILE = STATE_DIR / "betting_track_record.json"


def _ensure_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_history():
    _ensure_dir()
    if RECORD_FILE.exists():
        try:
            with open(RECORD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"트랙 레코드 로드 실패: {e}")
    return {"history": []}


def save_history(data):
    _ensure_dir()
    try:
        with open(RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"트랙 레코드 저장 실패: {e}")


def record_closing_picks(picks):
    """오늘 15:10 종가베팅 추천 종목 기록"""
    if not picks:
        return
    now = datetime.now(KST)
    date_str = now.strftime('%Y-%m-%d')

    data = load_history()
    # 이미 오늘 기록이 있으면 갱신
    existing = [h for h in data.get('history', []) if h.get('date') == date_str]
    if existing:
        existing[0]['picks'] = [
            {'code': p['code'], 'name': p['name'], 'close_price': p['price'], 'change_pct': p.get('change_pct', 0)}
            for p in picks
        ]
    else:
        data['history'].append({
            'date': date_str,
            'picks': [
                {'code': p['code'], 'name': p['name'], 'close_price': p['price'], 'change_pct': p.get('change_pct', 0)}
                for p in picks
            ],
            'evaluated': False
        })

    # 최근 30거래일만 유지
    data['history'] = data['history'][-30:]
    save_history(data)
    logger.info(f"[{date_str}] 종가베팅 {len(picks)}종목 트랙 레코드 기록 완료")


def evaluate_latest_performance():
    """
    가장 최근 종가베팅 추천의 익일 시초가 갭상승 성과 평가
    평가 조건: 평가 안 된 최근 회차의 다음 날 장 시작 후
    반환값: 텔레그램 메시지용 포맷 문자열 (평가할 대상이 없으면 None)
    """
    data = load_history()
    history = data.get('history', [])
    if not history:
        return None

    # 미평가된 항목 중 가장 최근 것 찾기
    target = None
    for h in reversed(history):
        if not h.get('evaluated', False):
            target = h
            break

    now = datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')

    # 당일 장 마감 전에 당일 것을 평가할 수는 없음 (익일 시초가가 필요)
    if not target or target.get('date') == today_str:
        # 이미 모두 평가되었거나 오늘 방금 등록된 것
        return None

    picks = target.get('picks', [])
    if not picks:
        target['evaluated'] = True
        save_history(data)
        return None

    results = []
    success_count = 0

    for p in picks:
        code = p['code']
        name = p['name']
        close_p = p['close_price']

        try:
            # 최근 가격 조회
            df = fdr.DataReader(code)
            if df.empty or len(df) < 2:
                continue

            # 마지막 봉의 시초가
            last_date = df.index[-1].strftime('%Y-%m-%d')
            # 만약 마지막 봉 날짜가 추천일보다 미래여야 익일 시초가임
            if last_date <= target['date']:
                # 아직 다음 거래일 장이 열리지 않음
                return None

            open_p = float(df['Open'].iloc[-1])
            gap_pct = ((open_p - close_p) / close_p) * 100

            is_success = gap_pct >= 1.5  # +1.5% 이상 갭상승 시 익절 성공 판정
            if is_success:
                success_count += 1

            p['open_price'] = int(open_p)
            p['gap_pct'] = round(gap_pct, 2)
            p['is_success'] = is_success

            badge = "🎯 갭상승 성공" if is_success else ("✨ 보합권" if gap_pct >= 0 else "🔻 갭하락")
            results.append(f"• <b>{name}</b>: 종가 {close_p:,}원 → 시초가 {int(open_p):,}원 (<b>{gap_pct:+.2f}%</b> {badge})")
        except Exception as e:
            logger.warning(f"성과 평가 실패 ({name}): {e}")

    if not results:
        return None

    target['evaluated'] = True
    target['success_count'] = success_count
    target['total_count'] = len(results)
    save_history(data)

    # 누적 승률 계산 (최근 평가된 20개 종목 기준)
    all_evaluated_picks = []
    for h in history:
        if h.get('evaluated'):
            for p in h.get('picks', []):
                if 'is_success' in p:
                    all_evaluated_picks.append(p)

    total_eval = len(all_evaluated_picks)
    win_eval = sum(1 for p in all_evaluated_picks if p.get('is_success'))
    win_rate = (win_eval / total_eval * 100) if total_eval > 0 else 0.0

    msg = f"📊 <b>[전일({target['date']}) 종가베팅 시초가 결과 피드백]</b>\n"
    msg += "\n".join(results) + "\n"
    if total_eval >= 3:
        msg += f"👉 <i>최근 누적 승률: <b>{win_rate:.1f}%</b> ({win_eval}승 {total_eval - win_eval}패)</i>\n"

    return msg
