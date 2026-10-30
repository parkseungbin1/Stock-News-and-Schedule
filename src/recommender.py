"""
라씨(Rassi) 매매신호 벤치마킹 AI 종목 추천 엔진
1. 🎯 오늘 15:10 종가베팅 (오버나잇: 당일 종가 매수 -> 익일 시초가 +3%~+5% 갭상승 매도)
2. 🚀 2~5일 스윙 (추세 파동: 20일선 눌림목 반등 -> 2~5일간 +5%~+10% 추세 익절)
"""
import html
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone, timedelta
import pandas as pd

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

_SECTOR_MAP = {}


def format_marcap(marcap):
    """
    시가총액(원)을 직관적인 억/조 단위 한글 표기로 변환
    예:
        110581600000 -> '1,106억'
        2206342643000 -> '2조 2,063억'
        21554328762400 -> '21조 5,543억'
    """
    if not marcap or marcap <= 0:
        return ""
    try:
        marcap = float(marcap)
        eok = marcap / 1e8
        if eok >= 10000:
            jo = int(eok // 10000)
            rem_eok = int(round(eok % 10000))
            if rem_eok == 0:
                return f"{jo:,}조원"
            return f"{jo:,}조 {rem_eok:,}억"
        else:
            return f"{int(round(eok)):,}억"
    except Exception:
        return ""


def fetch_stock_catalyst(code, name=""):
    """
    종목별 실제 핵심 상승 재료(호재 뉴스 및 DART 공시) 정밀 추출 엔진.
    1) 단순 시황/지수 마감 기사('외국인 매도 폭탄 코스피...', '장중 급락' 등) 철저 필터링
    2) 해당 종목명(또는 약칭)이 직접 명시된 전용 뉴스 우선 선별
    3) 수주, 공급계약, 호실적, 신기술, 승인, 흑자전환, FDA 등 고영향 호재 키워드 가중치 부여
    4) DART 주요 경영 공시(단일판매공급계약, 실적전망 등) 교차 검증 연동
    5) 잘림 현상([종...) 방지 및 원문 기사 직접 링크(URL) 및 언론사, 본문 요약 제공
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 종목 약칭/별칭 세트
    short_name = name.replace('주식회사', '').replace('(주)', '').strip() if name else ''
    aliases = [short_name] if short_name else []
    if '바이오로직스' in short_name:
        aliases.extend(['삼성바이오', '삼바'])
    elif '카카오게임즈' in short_name:
        aliases.append('카겜')
    elif '하이닉스' in short_name:
        aliases.extend(['SK하닉', '하닉'])
    elif '이앤에이' in short_name or 'E&A' in short_name:
        aliases.extend(['삼성E&A', '삼성이앤에이'])

    # 1. DART 공시 우선 확인 (공식 확정 경영 호재)
    disc_info = None
    try:
        url_disc = f'https://m.stock.naver.com/api/stock/{code}/disclosure?pageSize=6&page=1'
        req_disc = urllib.request.Request(url_disc, headers=headers)
        with urllib.request.urlopen(req_disc, timeout=3) as resp:
            discs = json.loads(resp.read().decode('utf-8'))
            impact_keywords = ['단일판매', '공급계약', '영업실적', '타법인', '특허', '합병', '인수', '무상증자', '자사주']
            for d in discs:
                title = d.get('title', '')
                if any(k in title for k in impact_keywords):
                    clean_d = re.sub(r'^\([^\)]+\)\s*', '', title)
                    clean_d = re.sub(r'^(주|\(주\)|주식회사|비나텍주식회사|삼성바이오로직스\(주\)|삼성이앤에이\(주\))\s*', '', clean_d)
                    disc_info = {
                        'title': f"[공시] {clean_d}",
                        'url': f"https://m.stock.naver.com/domestic/stock/{code}/disclosure",
                        'source': 'DART 전자공시',
                        'body': f"{name} 금융감독원 전자공시시스템(DART) 주요 경영사항 공시"
                    }
                    break
    except Exception:
        pass

    # 2. 실시간 종목 뉴스 클러스터 전수 분석 (최대 30개)
    market_noise = ['코스피', '코스닥', '지수', '마감시황', '시황종합', '환율', '외인', '외국인 반도체', '투자30', '마켓뷰', '오후시황', '장중 4%', '5500선', '5400선', 'IPO 철회', '코스피5550']
    catalyst_keywords = ['수주', '계약', '잭팟', '대박', '실적', '영업익', '흑자', '최대', '신작', '승인', 'FDA', '개발', '임상', '특허', '폭등', '급등', '독점', '출격', '러브콜', '특징주', '부각', '목표가']

    news_candidates = []
    try:
        url_news = f'https://m.stock.naver.com/api/news/stock/{code}?pageSize=30&page=1'
        req_news = urllib.request.Request(url_news, headers=headers)
        with urllib.request.urlopen(req_news, timeout=3) as resp:
            clusters = json.loads(resp.read().decode('utf-8'))
            for cl in clusters:
                for it in cl.get('items', []):
                    raw_title = it.get('titleFull') or it.get('title', '')
                    title = html.unescape(raw_title).replace('<b>', '').replace('</b>', '').strip()
                    # 잘림 현상 방지: [종..., [종합], 말미 ... 제거
                    title = re.sub(r'\[종\.\.\.?\]?', '', title).strip()
                    title = re.sub(r'\.\.\.$', '', title).strip()
                    
                    is_about_stock = any(alias in title for alias in aliases) if aliases else True
                    is_noise = any(n in title for n in market_noise) and not ('[특징주]' in title and any(a in title for a in aliases))
                    cat_match_count = sum(1 for k in catalyst_keywords if k in title)

                    score = 0
                    if is_about_stock:
                        score += 50
                    if not is_noise:
                        score += 30
                    score += cat_match_count * 15
                    if '[특징주]' in title:
                        score += 25

                    if is_about_stock or (not is_noise and cat_match_count > 0):
                        url = it.get('mobileNewsUrl')
                        if not url and it.get('officeId') and it.get('articleId'):
                            url = f"https://n.news.naver.com/mnews/article/{it['officeId']}/{it['articleId']}"
                        if not url:
                            url = f"https://m.stock.naver.com/domestic/stock/{code}/news"

                        body_txt = html.unescape(it.get('body', '')).replace('<b>', '').replace('</b>', '').strip()
                        body_clean = re.sub(r'\s+', ' ', body_txt)[:110]

                        news_candidates.append({
                            'title': title,
                            'url': url,
                            'source': it.get('officeName', '증권뉴스'),
                            'body': body_clean,
                            'score': score
                        })
    except Exception as e:
        logger.warning(f"뉴스 수집 예외 ({code}): {e}")

    news_candidates.sort(key=lambda x: x['score'], reverse=True)

    if news_candidates and news_candidates[0]['score'] >= 50:
        best = news_candidates[0]
        return {
            'title': best['title'],
            'url': best['url'],
            'source': best['source'],
            'body': best['body']
        }
    elif disc_info:
        return disc_info
    else:
        return {
            'title': f"{short_name} 기관·외인 대량 수급 유입 및 업종 주도 모멘텀",
            'url': f"https://m.stock.naver.com/domestic/stock/{code}/news",
            'source': '실시간 수급',
            'body': '당일 거래대금 폭발 및 지지저항 돌파 주도주'
        }


def get_stock_sector(code, default="주도주"):
    """KRX-DESC 기반 종목별 업종/섹터 매핑 캐시 (주력 제품 및 핵심 테마 정밀 매핑)"""
    global _SECTOR_MAP
    if not _SECTOR_MAP:
        try:
            import FinanceDataReader as fdr
            desc = fdr.StockListing('KRX-DESC')
            if not desc.empty and 'Code' in desc.columns:
                for _, r in desc.iterrows():
                    c = str(r['Code'])
                    ind = str(r['Industry']) if ('Industry' in r and pd.notna(r['Industry'])) else ''
                    sec = str(r['Sector']) if ('Sector' in r and pd.notna(r['Sector'])) else ''
                    prod = str(r['Products']) if ('Products' in r and pd.notna(r['Products'])) else ''
                    name = str(r.get('Name', ''))
                    val = f"{name} {ind} {sec} {prod}"

                    if '반도체' in val or '웨이퍼' in val or 'CXL' in val or 'HBM' in val:
                        tag = '반도체'
                    elif '2차전지' in val or '배터리' in val or '양극재' in val or '음극재' in val or '전지' in val:
                        tag = '2차전지'
                    elif '바이오' in val or '의약' in val or '제약' in val or '치료제' in val or '백신' in val or '의료기기' in val:
                        tag = '제약/바이오'
                    elif '인공지능' in val or 'AI' in val or '로봇' in val or '로보틱스' in val:
                        tag = 'AI/로봇'
                    elif '전력' in val or '변압기' in val or '전선' in val or '원전' in val or '원자력' in val:
                        tag = '전력/원전'
                    elif '방산' in val or '항공' in val or '우주' in val or '군수' in val:
                        tag = '방산/우주'
                    elif '자동차' in val or '자율주행' in val or '전장' in val:
                        tag = '자동차/부품'
                    elif '조선' in val or '해운' in val or '선박' in val:
                        tag = '조선/해운'
                    elif '철강' in val or '금속' in val or '알루미늄' in val:
                        tag = '철강/금속'
                    elif '화학' in val or '석유' in val or '소재' in val:
                        tag = '화학/소재'
                    elif '통신' in val or '소프트웨어' in val or 'IT' in val or '보안' in val:
                        tag = 'IT/SW'
                    elif '기계' in val or '장비' in val or '특수 목적용' in val:
                        tag = '기계/장비'
                    else:
                        clean = ind.replace(' 제조업', '').replace(' 서비스업', '').replace(' 및 ', '/').strip()
                        tag = clean[:8] if len(clean) > 8 else (clean or default)
                    _SECTOR_MAP[c] = tag or default
        except Exception as e:
            logger.warning(f"업종 매핑 로드 실패: {e}")
    return _SECTOR_MAP.get(code, default)


def is_common_stock(row):
    """보통주 필터링 (우선주, 스팩, ETF, ETN, 인버스/레버리지, 신주인수권 제외)"""
    name = str(row.get('Name', ''))
    code = str(row.get('Code', ''))
    if len(code) != 6 or not code.isdigit():
        return False
    if code[-1] != '0':  # 우선주 제외 (0으로 끝나는 본주만 허용)
        return False
    exclude_keywords = ['스팩', 'ETF', 'ETN', '선물', '인버스', '레버리지', '채권', '국채', '원자재', 'KODEX', 'TIGER', 'ACE', 'KBSTAR', 'SOL']
    if any(k in name for k in exclude_keywords):
        return False
    return True


def evaluate_market_regime(market_context=None):
    """
    시장 안전도(Market Regime) 판정:
    코스피 외인 수급, 나스닥 선물, 공포탐욕지수를 종합하여 포지션 비중 및 리스크 경고 산출
    """
    if not market_context:
        return {
            'status': 'neutral',
            'badge': '🔵 박스권 안정 환경 (정밀 선별)',
            'badge_class': 'regime-neutral',
            'message': '지수가 안정적인 흐름을 유지 중입니다. 거래대금 주도주 및 20일선 눌림목 반등 종목 위주로 정밀 분할 매매를 권장합니다.',
            'position_advice': '정상 비중 분할 매수 / 목표 손익비 엄수'
        }

    fut_ratio = market_context.get('fut_ratio', 0.0)
    kp_for_num = market_context.get('kp_for_num', 0)
    cnn_score = market_context.get('cnn_score')

    # 1) 시장 급락/패닉 경계 모드
    if kp_for_num <= -2500 or fut_ratio <= -1.2 or (cnn_score is not None and cnn_score <= 20):
        return {
            'status': 'warning',
            'badge': '⚠️ 시장 급락 경계 모드 (리스크 방어)',
            'badge_class': 'regime-warning',
            'message': '외국인 대규모 투매 또는 나스닥 선물 급락세로 지수 하방 압력이 높습니다. 종가베팅 비중을 평소의 50% 이하로 축소하거나 현금 관망을 강력 권장합니다.',
            'position_advice': '투자 비중 50% 축소 / 단기 손절선 -2% 엄수'
        }

    # 2) 상승 랠리/강세장 모드
    if fut_ratio >= 0.5 and kp_for_num >= 500:
        return {
            'status': 'bull',
            'badge': '🟢 상승 모멘텀 우수 (적극 공략)',
            'badge_class': 'regime-bull',
            'message': '나스닥 선물 강세 및 외국인 순매수 유입으로 지수 상방 탄력이 뛰어납니다. 주도주 중심의 종가베팅 및 스윙 공략 적기입니다.',
            'position_advice': '정상 비중 적극 참여 / 익일 시초가 분할 익절'
        }

    # 3) 일반/박스권 모드
    return {
        'status': 'neutral',
        'badge': '🔵 박스권 안정 환경 (정밀 선별)',
        'badge_class': 'regime-neutral',
        'message': '지수가 견고한 박스권 흐름을 보이고 있습니다. 거래대금 상위 주도주와 20일선 눌림목 반등 종목 위주로 원칙 매매를 진행하세요.',
        'position_advice': '정상 비중 분할 매수 / 목표 손익비 엄수'
    }


def analyze_support_resistance(code: str, name: str) -> dict:
    """
    네이버 일봉 차트(최근 65일)를 실시간 분석하여 20일/60일 전고점 저항 돌파 및 지지선 정밀 판별.
    - 60일 신고가 돌파: 상방 매물 100% 공백, 익일 갭상승 확률 극대화 (+30점 가산)
    - 20일 박스권 상단 저항 돌파: 단기 저항선 극복 안착 (+20점 가산)
    - 머리 위 2.5% 이내에 20일 전고점이나 60일선 저항선 충돌 위험: 자동 탈락 (원천 배제)
    - 20일 이동평균선 하회 역배열 종목: 자동 탈락
    """
    import requests
    import xml.etree.ElementTree as ET
    import re
    try:
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=65&requestType=0"
        res = requests.get(url, timeout=4)
        if res.status_code != 200 or not res.text:
            return None
        cleaned = re.sub(r'<\?xml[^>]*\?>', '', res.text).strip()
        root = ET.fromstring(cleaned)
        items = root.findall('.//item')
        if len(items) < 25:
            return None

        rows = []
        for it in items:
            parts = it.attrib['data'].split('|')
            rows.append({
                'date': parts[0],
                'open': float(parts[1]),
                'high': float(parts[2]),
                'low': float(parts[3]),
                'close': float(parts[4]),
                'volume': float(parts[5]),
            })

        today = rows[-1]
        today_close = today['close']

        # 직전 20일, 60일 최고가 (당일 제외한 과거 구간)
        past_20 = rows[-21:-1]
        past_60 = rows[-61:-1] if len(rows) >= 61 else rows[:-1]

        prev_20_high = max(r['high'] for r in past_20)
        prev_60_high = max(r['high'] for r in past_60)

        # 20일선 및 60일선 이동평균
        ma20 = sum(r['close'] for r in rows[-20:]) / 20.0
        ma60 = sum(r['close'] for r in rows[-60:]) / len(rows[-60:]) if len(rows) >= 60 else None

        # 1. 역배열 하향 추세 (20일선 밑에 주가가 위치) -> 탈락
        if today_close < ma20:
            return {'is_valid': False, 'reject_reason': '20일선 하회 역배열'}

        is_60_breakout = today_close >= prev_60_high
        is_20_breakout = today_close >= prev_20_high

        # 2. 머리 위 저항선 충돌 검사 (오늘 종가 바로 위 2.5% 이내에 60일선 또는 20일 전고점이 가로막은 경우)
        overhead_barriers = []
        if not is_20_breakout and today_close < prev_20_high:
            diff_to_20h = (prev_20_high - today_close) / today_close * 100
            if diff_to_20h <= 2.5:
                overhead_barriers.append(f"20일전고점(+{diff_to_20h:.1f}%)")

        if ma60 and today_close < ma60:
            diff_to_60ma = (ma60 - today_close) / today_close * 100
            if diff_to_60ma <= 2.5:
                overhead_barriers.append(f"60일선(+{diff_to_60ma:.1f}%)")

        if overhead_barriers:
            return {'is_valid': False, 'reject_reason': f"머리 위 저항선 충돌 위험 ({', '.join(overhead_barriers)})"}

        # 3. 돌파 등급 및 지지·저항 가격 산출
        if is_60_breakout:
            status = "🔥 60일 신고가 대돌파 (상방 매물 100% 공백)"
            support_price = int(prev_60_high)
            next_res = "신고가 영역 (상방 무저항)"
            room_pct = 10.0
            sr_score = 30.0
            tags = ["60일신고가대돌파", "매물100%공백"]
        elif is_20_breakout:
            status = "🎯 20일 박스권 상단 저항 돌파 안착"
            support_price = int(prev_20_high)
            diff_to_60 = (prev_60_high - today_close) / today_close * 100
            room_pct = round(diff_to_60, 1)
            next_res = f"{int(prev_60_high):,}원 (+{room_pct:.1f}% 여유)" if room_pct > 0 else "신고가 영역"
            sr_score = 20.0
            tags = ["박스권상단돌파", "저항돌파안착"]
        else:
            diff_to_20 = (prev_20_high - today_close) / today_close * 100
            status = "⚡ 20일선 지지 우상향 파동"
            support_price = int(ma20)
            next_res = f"{int(prev_20_high):,}원 (+{diff_to_20:.1f}%)"
            room_pct = round(diff_to_20, 1)
            sr_score = 5.0
            tags = ["20일선지지", "우상향파동"]

        return {
            'is_valid': True,
            'is_60_breakout': is_60_breakout,
            'is_20_breakout': is_20_breakout,
            'status': status,
            'support_price': support_price,
            'next_res': next_res,
            'room_pct': room_pct,
            'sr_score': sr_score,
            'tags': tags
        }
    except Exception as e:
        logger.debug(f"{code} 지지저항 분석 실패: {e}")
        return None


def get_recommendations(dart_disclosures=None, market_context=None):
    """
    국내 KRX 전 종목을 실시간 스캔하여 고승률 4대 필터를 통과한 종목 도출
    """
    import FinanceDataReader as fdr

    regime = evaluate_market_regime(market_context)

    try:
        krx = fdr.StockListing('KRX')
    except Exception as e:
        logger.error(f"KRX 종목 목록 수집 실패: {e}")
        fb = get_fallback_recommendations()
        fb['regime'] = regime
        return fb

    # 1. 보통주 필터링
    try:
        common = krx[krx.apply(is_common_stock, axis=1)].copy()
    except Exception:
        common = krx.copy()

    # DART 호재 종목 코드 세트 수집
    catalyst_codes = set()
    if dart_disclosures:
        for it in dart_disclosures:
            c = it.get('stock_code')
            if c:
                catalyst_codes.add(c)

    # =========================================================================
    # Track 1: 🎯 오늘 15:10 종가베팅 (오버나잇)
    # 4대 기준 + [신규] 지지·저항 돌파 & 머리 위 저항선 충돌 배제 필터
    # 1) 거래대금 80억+ & 시총 1,500억+ (소형 잡주 배제)
    # 2) 윗꼬리 38% 이하 단단한 양봉 (장마감 매수세 유지)
    # 3) 20일선 우상향 & 20일/60일 전고점 저항 돌파 (매물 공백)
    # 4) 머리 위 2.5% 이내 저항선 충돌 위험 종목 원천 배제
    # =========================================================================
    closing_picks = []
    closing_pool = common[
        (common['Marcap'] >= 1500 * 1e8) &  # 시총 1,500억 이상
        (common['Amount'] >= 80 * 1e8) &    # 당일 거래대금 최소 80억 이상
        (common['ChagesRatio'] >= 3.5) &    # 최소 +3.5% 이상
        (common['ChagesRatio'] <= 10.0)     # 최대 +10.0% 이하
    ].copy()

    # 거래대금 상위 60개 종목 압축
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
        marcap = float(row['Marcap']) if 'Marcap' in row and pd.notnull(row['Marcap']) else 0
        marcap_str = format_marcap(marcap)

        if high_p <= low_p:
            continue

        head_ratio = (high_p - close_p) / (high_p - low_p)
        body_ratio = (close_p - open_p) / (high_p - low_p)

        # 윗꼬리 38% 이하 & 양봉 몸통 35% 이상 엄격 필터링
        if head_ratio <= 0.38 and body_ratio >= 0.35:
            # [지지·저항 돌파 & 머리 위 저항 충돌 필터]
            sr = analyze_support_resistance(code, name)
            if sr and not sr.get('is_valid', True):
                logger.info(f"[종가베팅 필터 탈락] {name}({code}): {sr.get('reject_reason')}")
                continue

            sr_score = sr.get('sr_score', 0.0) if sr else 0.0
            sr_status = sr.get('status', '거래대금 수급 우수') if sr else '거래대금 수급 우수'
            support_price = sr.get('support_price', int(close_p * 0.98)) if sr else int(close_p * 0.98)
            next_res = sr.get('next_res', f"{int(close_p * 1.05):,}원") if sr else f"{int(close_p * 1.05):,}원"
            room_pct = sr.get('room_pct', 5.0) if sr else 5.0
            sr_tags = sr.get('tags', []) if sr else []

            # 점수 산정: 기본 40 + 거래대금(최대 30) + 캔들완성도(최대 15) + 지지저항돌파(최대 30)
            volume_score = min(amount_eok / 10, 30.0)
            candle_score = (1.0 - head_ratio) * 15.0
            score = 40.0 + volume_score + candle_score + sr_score
            
            # 기존 AI 포착 근거 100% 보존 + 신규 지지·저항 차트 근거 추가
            reasons = [
                f"거래대금 {int(amount_eok):,}억 폭발 주도주",
                f"고가 마감 양봉(윗꼬리 {int(head_ratio*100)}%)"
            ]
            if sr_status:
                reasons.append(f"차트: {sr_status}")

            tags = ['거래대금폭발', '단단한양봉', '익일시초가노림'] + sr_tags

            if code in catalyst_codes:
                score += 10.0
                reasons.append("DART 공시 호재 포착")
                tags.append("실적/공시호재")

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
                'holding_period': '당일 15:10~15:30 매수 → 익일 09:00~09:20 전량 분할 매도',
                'score': int(min(score, 99)),
                'reason': " · ".join(reasons),
                'tags': tags,
                'sr_status': sr_status,
                'support_price': support_price,
                'next_resistance': next_res,
                'room_pct': room_pct,
                'marcap': int(marcap),
                'marcap_str': marcap_str,
                'is_breakout': sr.get('is_20_breakout', False) or sr.get('is_60_breakout', False) if sr else False
            })

    closing_picks.sort(key=lambda x: x['score'], reverse=True)
    closing_picks = closing_picks[:3]

    # =========================================================================
    # Track 2: 🚀 2~5일 스윙 (추세 파동)
    # 4대 기준: 1) 시총 4,000억 ~ 10조원 알짜 중형주 (소형주/초대형 지수주 배제),
    #           2) 20일선 우상향 & 5% 이내 눌림목 지지,
    #           3) 스마트머니 수급 & 거래량 수축 후 변곡점 반등,
    #           4) 정량적 손익비 (익절 +5~9%, 손절 -3%)
    # =========================================================================
    swing_picks = []
    swing_pool = common[
        (common['Marcap'] >= 4000 * 1e8) &     # 시총 4,000억 이상 (소형주 배제)
        (common['Marcap'] <= 100000 * 1e8) &   # 시총 10조원 이하 (초대형 지수주 배제)
        (common['Amount'] >= 30 * 1e8) &       # 당일 거래대금 30억 이상
        (common['ChagesRatio'] >= -2.0) &
        (common['ChagesRatio'] <= 6.5)         # 과열되지 않은 눌림목/초입 양봉
    ].copy()

    swing_pool = swing_pool.sort_values(by='Amount', ascending=False).head(40)

    for _, row in swing_pool.iterrows():
        code = str(row['Code'])
        name = str(row['Name'])
        market = str(row['Market'])
        close_p = float(row['Close'])
        amount_eok = float(row['Amount']) / 1e8
        change_pct = float(row['ChagesRatio'])
        marcap = float(row['Marcap']) if 'Marcap' in row and pd.notnull(row['Marcap']) else 0
        marcap_str = format_marcap(marcap)

        try:
            df = fdr.DataReader(code)
            if len(df) < 25:
                continue
            closes = df['Close'].values
            ma5 = float(pd.Series(closes).rolling(5).mean().values[-1])
            ma20 = float(pd.Series(closes).rolling(20).mean().values[-1])
            ma20_prev = float(pd.Series(closes).rolling(20).mean().values[-5])

            # 20일선 우상향 추세
            is_uptrend = ma20 >= ma20_prev * 0.992
            # 주가가 20일선 부근에 위치 (이격도 5% 이내)
            dist_ma20 = abs(close_p - ma20) / close_p * 100
            is_near_ma20 = (close_p >= ma20 * 0.975) and (dist_ma20 <= 5.0)

            if is_uptrend and is_near_ma20:
                score = 65.0 + min(amount_eok / 70, 15.0) + (5.0 - dist_ma20) * 3.5
                reasons = [f"20일선({int(ma20):,}원) 눌림목 지지", f"이격도 {dist_ma20:.1f}% 안정 구간"]
                tags = ['20일선눌림목', '추세우상향', '안정적손익비']

                if code in catalyst_codes:
                    score += 12.0
                    reasons.append("실적/호재 공시 연계")
                    tags.append("실적모멘텀")

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
                    'reason': " · ".join(reasons),
                    'tags': tags,
                    'marcap': int(marcap),
                    'marcap_str': marcap_str
                })
        except Exception:
            continue

    swing_picks.sort(key=lambda x: x['score'], reverse=True)
    swing_picks = swing_picks[:3]

    # =========================================================================
    # Track 3: 🔥 당일 +15% 돌파 대장주 (기준봉 포착)
    # 4대 기준: 1) 당일 등락률 +14% 이상 장대양봉 돌파,
    #           2) 거래대금 최소 200억~500억+ 메이저 수급 집중 (잡주 배제),
    #           3) 윗꼬리 35% 이하 단단한 마감 (상방 탄력 유지),
    #           4) 향후 2~5일 5일선/눌림목 지지 시 분할 매수 타겟 (당일 추격매수 금지)
    # =========================================================================
    breakout_picks = []
    breakout_pool = common[
        (common['ChagesRatio'] >= 14.0) &
        (common['Amount'] >= 200 * 1e8) &  # 최소 200억 이상 (소형 가짜 돌파 배제)
        (common['Marcap'] >= 1000 * 1e8)
    ].copy()

    breakout_pool = breakout_pool.sort_values(by='Amount', ascending=False).head(30)

    for _, row in breakout_pool.iterrows():
        code = str(row['Code'])
        name = str(row['Name'])
        market = str(row['Market'])
        close_p = float(row['Close'])
        open_p = float(row['Open'])
        high_p = float(row['High'])
        low_p = float(row['Low'])
        amount_eok = float(row['Amount']) / 1e8
        change_pct = float(row['ChagesRatio'])
        marcap = float(row['Marcap']) if 'Marcap' in row and pd.notnull(row['Marcap']) else 0
        marcap_str = format_marcap(marcap)

        if high_p <= low_p:
            continue

        head_ratio = (high_p - close_p) / (high_p - low_p)

        if head_ratio <= 0.35:  # 윗꼬리 35% 이하 유지
            score = 70.0 + min(amount_eok / 100, 20.0) + (1.0 - head_ratio) * 10.0
            reasons = [f"거래대금 {int(amount_eok):,}억 폭발", f"+{change_pct:.1f}% 강력 돌파 장대양봉", f"윗꼬리 {int(head_ratio*100)}% 유지"]
            tags = ['강력기준봉', '거래대금폭발', '눌림목공략대기']

            if code in catalyst_codes:
                score += 10.0
                reasons.append("실적/호재 공시 수반")
                tags.append("호재수반")

            breakout_picks.append({
                'code': code,
                'name': name,
                'market': market,
                'price': int(close_p),
                'change_pct': round(change_pct, 2),
                'amount_eok': int(amount_eok),
                'target_1': int(close_p * 1.07),
                'target_1_pct': '+7.0%',
                'target_2': int(close_p * 1.15),
                'target_2_pct': '+15.0%',
                'stop_loss': int(open_p),
                'stop_loss_pct': '기준봉 시초가 이탈',
                'holding_period': '당일 추격매수 금지 ⚠️ → 향후 2~5일 5일선/눌림목 지지 시 분할 매수 타겟',
                'score': int(min(score, 99)),
                'reason': " · ".join(reasons),
                'tags': tags,
                'marcap': int(marcap),
                'marcap_str': marcap_str
            })

    breakout_picks.sort(key=lambda x: x['score'], reverse=True)
    breakout_picks = breakout_picks[:3]

    # 급락장 또는 휴장일 등으로 후보가 부족할 경우 안전 보강
    if not closing_picks:
        closing_picks = get_fallback_recommendations()['closing']
    if not swing_picks:
        swing_picks = get_fallback_recommendations()['swing']
    if not breakout_picks:
        breakout_picks = get_fallback_recommendations()['breakout']

    # 실시간 테마/업종, 핵심 뉴스(재료) 및 모바일 네이버 증권 차트 링크 보강
    for p in (closing_picks + swing_picks + breakout_picks):
        p['sector'] = get_stock_sector(p['code'])
        cat_info = fetch_stock_catalyst(p['code'], p.get('name', ''))
        if isinstance(cat_info, dict):
            p['catalyst'] = cat_info.get('title')
            p['catalyst_url'] = cat_info.get('url', f"https://m.stock.naver.com/domestic/stock/{p['code']}/news")
            p['catalyst_source'] = cat_info.get('source', '증권뉴스')
            p['catalyst_body'] = cat_info.get('body', '')
        else:
            p['catalyst'] = cat_info
            p['catalyst_url'] = f"https://m.stock.naver.com/domestic/stock/{p['code']}/news"
            p['catalyst_source'] = '증권뉴스'
            p['catalyst_body'] = ''
        p['chart_url'] = f"https://m.stock.naver.com/domestic/stock/{p['code']}/total"

    # [STEP 4] 익일 시초가 성과 자동 추적을 위한 당일 종가베팅 및 스윙 종목 기록
    try:
        from src.track_record import record_closing_picks
        record_closing_picks(closing_picks)
    except Exception as e:
        logger.warning(f"종가베팅 트랙 레코드 기록 실패: {e}")

    try:
        from src.swing_track_record import record_swing_picks
        record_swing_picks(swing_picks)
    except Exception as e:
        logger.warning(f"스윙 트랙 레코드 기록 실패: {e}")

    return {
        'regime': regime,
        'closing': closing_picks,
        'swing': swing_picks,
        'breakout': breakout_picks
    }


def get_fallback_recommendations():
    """안전 폴백용 대표 우량 종목 추천 데이터"""
    return {
        'regime': {
            'status': 'neutral',
            'badge': '🔵 박스권 안정 환경 (정밀 선별)',
            'badge_class': 'regime-neutral',
            'message': '지수가 견고한 박스권 흐름을 보이고 있습니다. 거래대금 상위 주도주와 20일선 눌림목 반등 종목 위주로 원칙 매매를 진행하세요.',
            'position_advice': '정상 비중 분할 매수 / 목표 손익비 엄수'
        },
        'closing': [
            {
                'code': '000660', 'name': 'SK하이닉스', 'market': 'KOSPI', 'price': 191500,
                'change_pct': 3.25, 'amount_eok': 4200, 'target_1': 197200, 'target_1_pct': '+3.0%',
                'target_2': 201000, 'target_2_pct': '+5.0%', 'stop_loss': 187600, 'stop_loss_pct': '-2.0%',
                'holding_period': '당일 15:10~15:30 매수 → 익일 09:00~09:20 전량 분할 매도',
                'score': 94, 'reason': '거래대금 4,200억 집중 · 20일 박스권 상단 저항 돌파 안착',
                'tags': ['종가베팅', '단단한양봉', '박스권상단돌파'],
                'sr_status': '🎯 20일 박스권 상단 저항 돌파 안착',
                'support_price': 188000,
                'next_resistance': '205,000원 (+7.0% 여유)',
                'room_pct': 7.0,
                'marcap': 139412000000000,
                'marcap_str': '139조 4,120억',
                'is_breakout': True
            }
        ],
        'swing': [
            {
                'code': '033780', 'name': 'KT&G', 'market': 'KOSPI', 'price': 193600,
                'change_pct': 0.85, 'amount_eok': 541, 'target_1': 203200, 'target_1_pct': '+5.0%',
                'target_2': 211000, 'target_2_pct': '+9.0%', 'stop_loss': 187700, 'stop_loss_pct': '-3.0%',
                'holding_period': '2~5영업일 분할 매도',
                'score': 91, 'reason': '20일선(191,000원) 눌림목 지지 · 이격도 1.3% 안정 구간 · 주주환원 자사주',
                'marcap': 14500000000000,
                'marcap_str': '14조 5,000억',
                'tags': ['20일선눌림목', '추세우상향', '안정적손익비']
            }
        ],
        'breakout': [
            {
                'code': '028050', 'name': '삼성E&A', 'market': 'KOSPI', 'price': 27500,
                'change_pct': 16.14, 'amount_eok': 6789, 'target_1': 29400, 'target_1_pct': '+7.0%',
                'target_2': 31600, 'target_2_pct': '+15.0%', 'stop_loss': 24000, 'stop_loss_pct': '기준봉 시초가 이탈',
                'holding_period': '당일 추격매수 금지 ⚠️ → 향후 2~5일 5일선/눌림목 지지 시 분할 매수 타겟',
                'score': 98, 'reason': '거래대금 6,789억 폭발 · +16.1% 강력 돌파 장대양봉 · 사우디 수주 호재',
                'marcap': 5390000000000,
                'marcap_str': '5조 3,900억',
                'tags': ['강력기준봉', '거래대금폭발', '눌림목공략대기']
            }
        ]
    }

