"""
2~5일 스윙 추천 사후 성과 자동 추적 및 통계 모듈 (Swing Track Record)
1. 2~5일 스윙 추천 종목(20일선 눌림목 반등 타겟) 저장
2. 2~5영업일간 일봉을 하루씩 따라가며 3분할 청산 시뮬레이션
   - 1차 +3% 도달 시 1/3 익절 → 잔량 손절선을 본절(0%)로 상향
   - 2차 +5% 도달 시 1/3 익절 → 잔량 손절선을 +3%로 상향
   - 3차 +9% 도달 시 잔량 전량 익절 / 최초 손절 -3% / 5영업일 경과 시 종가 청산
3. 최근 1개월(30일) 데이터 유지 (1달 경과 시 자동 정리)
4. 웹 대시보드 전용 '최근 1개월 스윙 성과' 탭 렌더링 지원
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

STATE_DIR = Path(__file__).resolve().parent.parent / "data"
SWING_RECORD_FILE = STATE_DIR / "swing_track_record.json"

# 스윙 청산 규칙 버전 (2 = 3분할 +3/+5/+9, 손절 -3%, 1차 후 본절 스탑)
SWING_RULE_VERSION = 2
T1_PCT, T2_PCT, T3_PCT, SL_PCT = 3.0, 5.0, 9.0, -3.0
MAX_HOLD_DAYS = 5


def _ensure_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def is_valid_trading_date(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.weekday() < 5
    except Exception:
        return False


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('history', [])
    except Exception:
        return []


def load_swing_history():
    _ensure_dir()
    history = _read(SWING_RECORD_FILE) if SWING_RECORD_FILE.exists() else []
    data = {"history": sorted(history, key=lambda x: x['date'])}
    return cleanup_old_swing_records(data)


def save_swing_history(data):
    _ensure_dir()
    data = cleanup_old_swing_records(data)
    try:
        with open(SWING_RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"스윙 트랙 레코드 저장 실패: {e}")


def cleanup_old_swing_records(data):
    now = datetime.now(KST)
    cutoff = (now - timedelta(days=35)).strftime('%Y-%m-%d')
    history = data.get('history', [])
    data['history'] = [
        h for h in history
        if h.get('date', '') >= cutoff and is_valid_trading_date(h.get('date', ''))
    ]
    return data


def record_swing_picks(picks):
    """당일 2~5일 스윙 추천 종목 기록"""
    if not picks:
        return
    now = datetime.now(KST)
    data = load_swing_history()
    existing_dates = {h.get('date') for h in data.get('history', [])}
    hm = now.hour * 100 + now.minute
    if now.weekday() >= 5 or hm < 1500:
        cur = now - timedelta(days=1)
        while cur.weekday() >= 5:
            cur -= timedelta(days=1)
        prev_bday = cur.strftime('%Y-%m-%d')
        if prev_bday not in existing_dates:
            date_str = prev_bday
        else:
            return
    else:
        date_str = now.strftime('%Y-%m-%d')
    existing = [h for h in data.get('history', []) if h.get('date') == date_str]

    pick_items = []
    for p in picks:
        entry_p = p.get('price', p.get('close_price', 0))
        if entry_p <= 0:
            continue
        t1 = int(round(entry_p * (1 + T1_PCT / 100)))
        t2 = int(round(entry_p * (1 + T2_PCT / 100)))
        t3 = int(round(entry_p * (1 + T3_PCT / 100)))
        sl = int(round(entry_p * (1 + SL_PCT / 100)))
        item = {
            'code': p['code'],
            'name': p['name'],
            'market': p.get('market', 'KRX'),
            'sector': p.get('sector', '우량스윙주'),
            'catalyst': p.get('catalyst', ''),
            'catalyst_url': p.get('catalyst_url', f"https://m.stock.naver.com/domestic/stock/{p['code']}/news"),
            'catalyst_source': p.get('catalyst_source', ''),
            'entry_price': entry_p,
            'price': entry_p,
            'change_pct': p.get('change_pct', 0),
            'amount_eok': p.get('amount_eok', 0),
            'marcap': p.get('marcap', 0),
            'marcap_str': p.get('marcap_str', ''),
            'target_1': t1,
            'target_1_pct': '+3.0%',
            'target_2': t2,
            'target_2_pct': '+5.0%',
            'target_3': t3,
            'target_3_pct': '+9.0%',
            'stop_loss': sl,
            'stop_loss_pct': '-3.0%',
            'rule_v': SWING_RULE_VERSION,
            'stage': 0,
            'score': p.get('score', 92),
            'reason': p.get('reason', '20일선 눌림목 반등 및 수급 메이저 집중 우상향 스윙주'),
            'holding_period': '2~5영업일 3분할 매도',
            'tags': p.get('tags', ['스윙추천', '20일선눌림목']),
            'chart_url': p.get('chart_url', f"https://m.stock.naver.com/domestic/stock/{p['code']}/total"),
            'highest_price': entry_p,
            'lowest_price': entry_p,
            'max_return_pct': 0.0,
            'status': '진행중',
            'completed': False,
            'holding_days': 0
        }
        pick_items.append(item)

    if existing:
        if not existing[0].get('evaluated', False):
            existing[0]['picks'] = pick_items
    else:
        data['history'].append({
            'date': date_str,
            'picks': pick_items,
            'evaluated': False
        })

    save_swing_history(data)


def simulate_3split_exit(entry_p, bars):
    """
    일봉 리스트(bars: [(open, high, low, close), ...])를 하루씩 따라가며 3분할 청산 시뮬레이션.
    - 같은 날 손절선과 목표가가 모두 닿으면 보수적으로 '손절 먼저'로 처리
    - 1차(+3%) 1/3 익절 → 잔량 손절선 본절(0%) / 2차(+5%) 1/3 익절 → 잔량 손절선 +3% / 3차(+9%) 잔량 익절
    반환: dict(stage, realized_pct, remaining, exit_reason, days)
    """
    t1 = entry_p * (1 + T1_PCT / 100)
    t2 = entry_p * (1 + T2_PCT / 100)
    t3 = entry_p * (1 + T3_PCT / 100)
    stop = entry_p * (1 + SL_PCT / 100)
    remaining = 1.0
    realized = 0.0
    stage = 0
    exit_reason = None
    days = 0

    for (o, h, l, c) in bars:
        days += 1
        # 1) 손절/본절/수익잠금 스탑 체크 (갭하락 시 시가 체결)
        if l <= stop:
            px = o if o < stop else stop
            realized += remaining * (px / entry_p - 1) * 100
            remaining = 0.0
            exit_reason = 'stop'
            break
        # 2) 목표가 순차 체크
        if stage < 1 and h >= t1:
            realized += (1 / 3) * T1_PCT
            remaining -= 1 / 3
            stage = 1
            stop = entry_p          # 본절 스탑
        if stage < 2 and h >= t2:
            realized += (1 / 3) * T2_PCT
            remaining -= 1 / 3
            stage = 2
            stop = t1               # +3% 수익 잠금
        if stage < 3 and h >= t3:
            realized += remaining * T3_PCT
            remaining = 0.0
            stage = 3
            exit_reason = 'target3'
            break

    if remaining > 1e-9 and days >= MAX_HOLD_DAYS:
        last_close = bars[-1][3]
        realized += remaining * (last_close / entry_p - 1) * 100
        remaining = 0.0
        exit_reason = 'expire'

    return {
        'stage': stage,
        'realized_pct': round(realized, 2),
        'remaining': round(max(remaining, 0.0), 4),
        'exit_reason': exit_reason,
        'days': days,
    }


def _status_from_sim(sim):
    stage = sim['stage']
    reason = sim['exit_reason']
    days = sim['days']
    if reason == 'target3':
        return '3차 목표 달성 (전량 익절)'
    if reason == 'stop':
        if stage == 0:
            return '손절 이탈'
        if stage == 1:
            return '1차 익절 후 본절 청산'
        return '2차 익절 후 +3% 잠금 청산'
    if reason == 'expire':
        return f'{stage}차 익절 후 기간만료 청산' if stage > 0 else '기간 만료'
    return f'{stage}차 달성 · 진행중 ({days}일차)' if stage > 0 else f'진행중 ({days}일차)'


def evaluate_swing_performance():
    """추천일 이후 최대 5영업일간 일봉을 따라가며 3분할 청산 성과 자동 판정"""
    data = load_swing_history()
    history = data.get('history', [])
    if not history:
        return

    now = datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')
    updated = False

    for h in history:
        h_date = h.get('date', '')
        if h_date >= today_str:
            continue

        picks = h.get('picks', [])
        all_done = True

        for p in picks:
            # 구버전 규칙(+5/+9)으로 판정된 기록은 새 규칙으로 재판정
            if p.get('rule_v') != SWING_RULE_VERSION:
                p['completed'] = False
                p['rule_v'] = SWING_RULE_VERSION
                for k in ('final_return_pct', 'is_success'):
                    p.pop(k, None)
                h['evaluated'] = False

            if p.get('completed', False):
                continue

            code = p.get('code')
            entry_p = p.get('entry_price', 0)
            if entry_p <= 0:
                p['completed'] = True
                continue

            try:
                start = (datetime.strptime(h_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
                df = fdr.DataReader(code, start)
                if df.empty:
                    all_done = False
                    continue

                # 추천일 종가를 진입가로 확정
                if h_date in df.index:
                    entry_p = int(df.loc[h_date, 'Close'])
                p['entry_price'] = entry_p
                p['price'] = entry_p
                p['target_1'] = int(round(entry_p * (1 + T1_PCT / 100)))
                p['target_2'] = int(round(entry_p * (1 + T2_PCT / 100)))
                p['target_3'] = int(round(entry_p * (1 + T3_PCT / 100)))
                p['stop_loss'] = int(round(entry_p * (1 + SL_PCT / 100)))
                p['target_1_pct'], p['target_2_pct'], p['target_3_pct'], p['stop_loss_pct'] = '+3.0%', '+5.0%', '+9.0%', '-3.0%'

                sub = df[df.index.strftime('%Y-%m-%d') > h_date].head(MAX_HOLD_DAYS)
                if sub.empty:
                    all_done = False
                    continue

                bars = list(zip(sub['Open'].astype(float), sub['High'].astype(float),
                                sub['Low'].astype(float), sub['Close'].astype(float)))
                sim = simulate_3split_exit(entry_p, bars)

                p['holding_days'] = sim['days']
                p['highest_price'] = int(sub['High'].max())
                p['lowest_price'] = int(sub['Low'].min())
                p['max_return_pct'] = round((p['highest_price'] - entry_p) / entry_p * 100, 2)
                p['stage'] = sim['stage']
                p['realized_pct'] = sim['realized_pct']
                p['status'] = _status_from_sim(sim)

                if sim['exit_reason']:
                    p['completed'] = True
                    p['final_return_pct'] = sim['realized_pct']
                    p['is_success'] = sim['realized_pct'] > 0
                else:
                    all_done = False

                updated = True
            except Exception as e:
                logger.warning(f"스윙 성과 추적 실패 ({p.get('name')}): {e}")
                all_done = False

        h['evaluated'] = all_done

    if updated:
        save_swing_history(data)


def render_monthly_swing_history_html():
    """웹 대시보드 전용 '최근 1개월 스윙 성과' 탭 HTML 렌더링"""
    data = load_swing_history()
    history = [h for h in data.get('history', []) if is_valid_trading_date(h.get('date', ''))]

    now = datetime.now(KST)
    history.sort(key=lambda x: x['date'], reverse=True)

    total_picks = 0
    win_picks = 0
    loss_picks = 0
    win_returns = []
    loss_returns = []
    total_cum = 0.0

    hold_days = []
    t1_hits = 0
    for h in history:
        for p in h.get('picks', []):
            if not p.get('completed'):
                continue
            ret = float(p.get('final_return_pct', 0.0) or 0.0)
            total_picks += 1
            total_cum += ret
            hold_days.append(p.get('holding_days', 0) or 0)
            if (p.get('stage', 0) or 0) >= 1:
                t1_hits += 1
            if ret > 0:
                win_picks += 1
                win_returns.append(ret)
            else:
                loss_picks += 1
                loss_returns.append(abs(ret))

    win_rate = (win_picks / total_picks * 100) if total_picks > 0 else 0.0
    t1_rate = (t1_hits / total_picks * 100) if total_picks > 0 else 0.0
    avg_win = (sum(win_returns) / len(win_returns)) if win_returns else 0.0
    avg_loss = (sum(loss_returns) / len(loss_returns)) if loss_returns else 0.0
    rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    avg_ret = (total_cum / total_picks) if total_picks > 0 else 0.0
    avg_hold = (sum(hold_days) / len(hold_days)) if hold_days else 0.0

    start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')

    summary_html = f"""
    <div class="track-summary-grid">
        <div class="track-stat-card stat-swing-winrate">
            <div class="stat-label">🎯 최근 30일 스윙 승률 (실현손익 &gt; 0)</div>
            <div class="stat-value">{win_rate:.1f}%</div>
            <div class="stat-sub">{win_picks}승 {loss_picks}패 ({total_picks}회 청산) · 1차(+3%) 도달률 {t1_rate:.0f}%</div>
        </div>
        <div class="track-stat-card stat-swing-rr">
            <div class="stat-label">⚖️ 스윙 평균 손익비 (P/L Ratio)</div>
            <div class="stat-value">{rr_ratio:.2f} : 1</div>
            <div class="stat-sub">익절 평균 +{avg_win:.2f}% / 손절 평균 -{avg_loss:.2f}%</div>
        </div>
        <div class="track-stat-card stat-swing-cum">
            <div class="stat-label">💰 30일 스윙 누적 실현 수익률 (3분할 기준)</div>
            <div class="stat-value">{total_cum:+.2f}%</div>
            <div class="stat-sub">종목당 평균 실현 {avg_ret:+.2f}%</div>
        </div>
        <div class="track-stat-card stat-swing-period">
            <div class="stat-label">⏱️ 평균 보유(청산까지) 기간</div>
            <div class="stat-value">{avg_hold:.1f} 영업일</div>
            <div class="stat-sub">{start_date} ~ {end_date} (2~5일 추세추적)</div>
        </div>
    </div>
    """

    cards_html = ""
    for h in history:
        h_date = h.get('date', '')
        evaluated = h.get('evaluated', False)
        status_tag = '<span class="hist-badge badge-done">✓ 추적 완료</span>' if evaluated else '<span class="hist-badge badge-wait">⏳ 2~5일 추세 진행중</span>'

        items_html = ""
        for p in h.get('picks', []):
            code = p.get('code', '')
            name = p.get('name', '')
            sec = p.get('sector', '우량스윙')
            cat = p.get('catalyst', '')
            entry_p = p.get('entry_price', 0)
            high_p = p.get('highest_price', entry_p)
            max_ret = p.get('max_return_pct', 0.0)
            status = p.get('status', '진행중')
            h_days = p.get('holding_days', 0)
            marcap_str = p.get('marcap_str', '')
            marcap_tag = f" <span class='hist-marcap'>시총 {marcap_str}</span>" if marcap_str else ""

            stage = p.get('stage', 0) or 0
            fin_ret = p.get('final_return_pct', p.get('realized_pct', 0.0)) or 0.0
            completed = p.get('completed', False)
            if completed and '3차' in status:
                badge = f'<span class="res-badge win-gold">🚀 3차 전량 익절 (실현 {fin_ret:+.2f}%)</span>'
            elif completed and stage >= 1:
                badge = f'<span class="res-badge win">🎯 {status} (실현 {fin_ret:+.2f}%)</span>'
            elif completed and '손절' in status:
                badge = f'<span class="res-badge loss">🔻 손절 이탈 ({fin_ret:+.2f}%)</span>'
            elif completed:
                badge = f'<span class="res-badge {"win" if fin_ret > 0 else "loss"}">⌛ 기간만료 종가청산 ({fin_ret:+.2f}%)</span>'
            else:
                stage_str = f", {stage}차 익절 완료·잔량 보유" if stage > 0 else ""
                badge = f'<span class="res-badge wait">⏳ 진행중 ({h_days}일차, 최고 {max_ret:+.2f}%{stage_str})</span>'

            low_p = p.get('lowest_price', entry_p)
            min_ret = round(((low_p - entry_p) / entry_p) * 100, 2) if entry_p > 0 else 0.0
            if '손절' in status:
                res_str = f"{h_date} 종가 {entry_p:,}원 → 최저 <b>{low_p:,}원</b> (<span class='down'>{min_ret:+.2f}%</span> · 1차목표 +3% 미달, 반등최고 {max_ret:+.2f}%) {badge}"
            else:
                res_str = f"{h_date} 종가 {entry_p:,}원 → 최고 <b>{high_p:,}원</b> (<span class='{'up' if max_ret>0 else 'down'}'>{max_ret:+.2f}%</span>) {badge}"

            cat_url = p.get('catalyst_url', f"https://m.stock.naver.com/domestic/stock/{code}/news")
            cat_src = p.get('catalyst_source', '')
            src_str = f" <span class='hist-cat-src'>({cat_src})</span>" if cat_src else ""
            cat_html = f"<div class='hist-cat'>📰 <b>상승 모멘텀</b>: <a href='{cat_url}' target='_blank' rel='noopener noreferrer' class='hist-cat-link'>{cat}{src_str} ↗</a></div>" if cat else ""

            items_html += f"""
            <div class="hist-item">
                <div class="hist-item-header">
                    <div class="hist-name-box">
                        <a href="https://m.stock.naver.com/domestic/stock/{code}/total" target="_blank" rel="noopener noreferrer">
                            <b>{name}</b> <span class="hist-code">{code}</span>
                        </a>
                        <span class="hist-sector">[{sec}]</span>{marcap_tag}
                    </div>
                    <div class="hist-result">{res_str}</div>
                </div>
                {cat_html}
            </div>
            """

        cards_html += f"""
        <div class="history-day-card">
            <div class="history-day-header">
                <div class="day-title">📅 <b>{h_date} 2~5일 스윙 추천</b></div>
                <div>{status_tag}</div>
            </div>
            <div class="history-day-body">
                {items_html}
            </div>
        </div>
        """

    return f"""
    <div class="track-record-wrap">
        {summary_html}
        <div class="history-card-list">
            {cards_html}
        </div>
    </div>
    """
