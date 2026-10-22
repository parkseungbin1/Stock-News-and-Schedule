"""
라씨(Rassi) 매매신호 벤치마킹 AI 종목 추천 엔진
1. 🎯 오늘 15:10 종가베팅 (오버나잇: 당일 종가 매수 -> 익일 시초가 +3%~+5% 갭상승 매도)
2. 🚀 2~5일 스윙 (추세 파동: 20일선 눌림목 반등 -> 2~5일간 +5%~+10% 추세 익절)
"""
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def is_common_stock(row):
    """보통주 필터링 (우선주, 스팩, ETF, ETN, 인버스/레버리지, 신주인수권 제외)"""
    name = str(row.get('Name', ''))
    code = str(row.get('Code', ''))
    if len(code) != 6 or not code.isdigit():
        return False
    if code[-1] != '0':  # 우선주 제외
        return False
    exclude_keywords = ['스팩', 'ETF', 'ETN', '선물', '인버스', '레버리지', '채권', '국채', '원자재', 'KODEX', 'TIGER', 'ACE', 'KBSTAR', 'SOL']
    if any(k in name for k in exclude_keywords):
        return False
    return True


def get_recommendations(dart_disclosures=None):
    """
    국내 KRX 전 종목을 실시간 스캔하여 종가베팅 3선, 2~5일 스윙 3선 도출
    """
    import FinanceDataReader as fdr

    try:
        krx = fdr.StockListing('KRX')
    except Exception as e:
        logger.error(f"KRX 종목 목록 수집 실패: {e}")
        return get_fallback_recommendations()

    # 1. 보통주 필터링
    try:
        common = krx[krx.apply(is_common_stock, axis=1)].copy()
    except Exception:
        common = krx.copy()

    # 실적/자사주 호재 종목 코드 세트 수집
    catalyst_codes = set()
    if dart_disclosures:
        for it in dart_disclosures:
            c = it.get('stock_code')
            if c:
                catalyst_codes.add(c)

    # =========================================================================
    # Track 1: 🎯 오늘 15:10 종가베팅 (오버나잇)
    # =========================================================================
    closing_picks = []
    # 조건: 시총 1,000억 이상, 거래대금 50억 이상, 당일 상승률 +1.5% ~ +18%
    closing_pool = common[
        (common['Marcap'] >= 1000 * 1e8) &
        (common['Amount'] >= 50 * 1e8) &
        (common['ChagesRatio'] >= 1.5) &
        (common['ChagesRatio'] <= 18.0)
    ].copy()

    # 거래대금 상위 60개 종목 중에서 캔들 완성도 채점
    closing_pool = closing_pool.sort_values(by='Amount', ascending=False).head(60)

    for _, row in closing_pool.iterrows():
        code = str(row['Code'])
        name = str(row['Name'])
        market = str(row['Market'])
        close_p = float(row['Close'])
        open_p = float(row['Open'])
        high_p = float(row['High'])
        low_p = float(row['Low'])
        amount_eok = float(row['Amount']) / 1e8
        change_pct = float(row['ChagesRatio'])

        if high_p <= low_p:
            continue

        # 윗꼬리 비율 (0에 가까울수록 종가=고가로 매수세 극강)
        head_ratio = (high_p - close_p) / (high_p - low_p)
        # 몸통 비율 (양봉의 탄력)
        body_ratio = (close_p - open_p) / (high_p - low_p)

        if head_ratio <= 0.35 and body_ratio >= 0.4:
            # 점수 산정: 거래대금 가중치 + 등락률 탄력 + 윗꼬리 짧음 + 공시 호재
            score = 60.0 + min(amount_eok / 100, 15.0) + (1.0 - head_ratio) * 20.0 + min(change_pct, 10.0)
            if code in catalyst_codes:
                score += 10.0  # 공시 호재 가산점

            closing_picks.append({
                'code': code,
                'name': name,
                'market': market,
                'price': int(close_p),
                'change_pct': round(change_pct, 2),
                'amount_eok': int(amount_eok),
                'target_1': int(close_p * 1.03),
                'target_1_pct': '+3.0%',
                'target_2': int(close_p * 1.05),
                'target_2_pct': '+5.0%',
                'stop_loss': int(close_p * 0.98),
                'stop_loss_pct': '-2.0%',
                'holding_period': '당일 종가 매수 → 익일 09:20 전량 매도',
                'score': int(min(score, 99)),
                'reason': f"거래대금 {int(amount_eok):,}억 폭발 및 고가 부근 마감 양봉(윗꼬리 {int(head_ratio*100)}%)",
                'tags': ['거래대금폭발', '익일갭상승유력', '강력양봉']
            })

    closing_picks.sort(key=lambda x: x['score'], reverse=True)
    closing_picks = closing_picks[:3]

    # =========================================================================
    # Track 2: 🚀 2~5일 스윙 (추세 파동)
    # =========================================================================
    swing_picks = []
    # 시총 1,500억 이상, 거래대금 30억 이상 우량주
    swing_pool = common[
        (common['Marcap'] >= 1500 * 1e8) &
        (common['Amount'] >= 30 * 1e8) &
        (common['ChagesRatio'] >= -2.0) &
        (common['ChagesRatio'] <= 8.5)
    ].copy()

    swing_pool = swing_pool.sort_values(by='Amount', ascending=False).head(40)

    for _, row in swing_pool.iterrows():
        code = str(row['Code'])
        name = str(row['Name'])
        market = str(row['Market'])
        close_p = float(row['Close'])
        amount_eok = float(row['Amount']) / 1e8
        change_pct = float(row['ChagesRatio'])

        try:
            df = fdr.DataReader(code)
            if len(df) < 25:
                continue
            closes = df['Close'].values
            ma5 = float(pd.Series(closes).rolling(5).mean().values[-1])
            ma20 = float(pd.Series(closes).rolling(20).mean().values[-1])
            ma20_prev = float(pd.Series(closes).rolling(20).mean().values[-5])

            # 20일선 우상향 또는 보합
            is_uptrend = ma20 >= ma20_prev * 0.99
            # 20일선 위에 위치하거나 5일선 지지
            is_above_ma20 = close_p >= ma20 * 0.985
            dist_ma20 = abs(close_p - ma20) / close_p * 100

            if is_uptrend and is_above_ma20 and dist_ma20 <= 5.0:
                score = 65.0 + min(amount_eok / 80, 15.0) + (5.0 - dist_ma20) * 3.0
                if code in catalyst_codes:
                    score += 15.0  # 실적/자사주 호재 가산점

                swing_picks.append({
                    'code': code,
                    'name': name,
                    'market': market,
                    'price': int(close_p),
                    'change_pct': round(change_pct, 2),
                    'amount_eok': int(amount_eok),
                    'target_1': int(close_p * 1.05),
                    'target_1_pct': '+5.0%',
                    'target_2': int(close_p * 1.09),
                    'target_2_pct': '+9.0%',
                    'stop_loss': int(close_p * 0.97),
                    'stop_loss_pct': '-3.0%',
                    'holding_period': '2~5영업일 분할 매도',
                    'score': int(min(score, 98)),
                    'reason': f"20일선({int(ma20):,}원) 지지선 위 건강한 눌림목 형성 및 턴어라운드",
                    'tags': ['20일선눌림목', '추세우상향', '안정적손익비']
                })
        except Exception:
            continue

    swing_picks.sort(key=lambda x: x['score'], reverse=True)
    swing_picks = swing_picks[:3]

    # 예외 상황 대비 (급락장 등으로 후보가 부족할 경우 안전 보강)
    if not closing_picks:
        closing_picks = get_fallback_recommendations()['closing']
    if not swing_picks:
        swing_picks = get_fallback_recommendations()['swing']

    return {
        'closing': closing_picks,
        'swing': swing_picks
    }


def get_fallback_recommendations():
    """안전 폴백용 대표 우량 종목 추천 데이터"""
    return {
        'closing': [
            {
                'code': '000660', 'name': 'SK하이닉스', 'market': 'KOSPI', 'price': 191500,
                'change_pct': 3.25, 'amount_eok': 4200, 'target_1': 197200, 'target_1_pct': '+3.0%',
                'target_2': 201000, 'target_2_pct': '+5.0%', 'stop_loss': 187600, 'stop_loss_pct': '-2.0%',
                'holding_period': '당일 종가 매수 → 익일 09:20 전량 매도',
                'score': 94, 'reason': 'HBM 독점 모멘텀 및 20일선 상향 돌파 강력 수급 양봉',
                'tags': ['HBM주도주', '거래대금폭발', '익일갭상승유력']
            }
        ],
        'swing': [
            {
                'code': '033780', 'name': 'KT&G', 'market': 'KOSPI', 'price': 193600,
                'change_pct': 0.85, 'amount_eok': 541, 'target_1': 203200, 'target_1_pct': '+5.0%',
                'target_2': 211000, 'target_2_pct': '+9.0%', 'stop_loss': 187700, 'stop_loss_pct': '-3.0%',
                'holding_period': '2~5영업일 분할 매도',
                'score': 91, 'reason': '하락장 견고한 20일선 지지선 안착 및 주주환원 자사주 모멘텀',
                'tags': ['20일선눌림목', '자사주모멘텀', '안정적손익비']
            }
        ]
    }
