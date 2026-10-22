"""
종가베팅 & 시초가 매도 타이밍 전문 시황 분석 모듈 (KRX + Nextrade 대체거래소 반영)
1. [아침 07:40] 🌅 08:00 NXT 프리마켓 개장 전 시초가 매도 가이드
2. [아침 08:40] 🌅 09:00 정규장 개장 전 최종 매도 & 동시호가 가이드
3. [오후 15:10] 🎯 15:30 정규장 마감 1차 종가베팅 가이드
4. [저녁 19:40] 🎯 20:00 NXT 8시 마감 최종 종가베팅 가이드
"""
import logging
from datetime import datetime, timezone, timedelta
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

KST = timezone(timedelta(hours=9))


def fetch_nasdaq_futures():
    """실시간 미국 E-mini 나스닥 100 선물 (NQ=F) 조회"""
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/NQ%3DF?interval=1d'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        meta = r['chart']['result'][0]['meta']
        price = meta.get('regularMarketPrice')
        prev = meta.get('chartPreviousClose')
        ratio = ((price - prev) / prev) * 100 if prev else 0.0
        return price, ratio
    except Exception as e:
        logger.warning(f"나스닥 선물 조회 실패: {e}")
    return None, 0.0


def fetch_naver_index(code):
    """네이버 증권 글로벌/국내 인덱스 조회 (예: .IXIC, .SOX, .GDAXI)"""
    url = f'https://api.stock.naver.com/index/{code}/basic'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        close = r.get('closePrice', '')
        ratio = float(r.get('fluctuationsRatio', 0))
        return close, ratio
    except Exception as e:
        logger.warning(f"인덱스 {code} 조회 실패: {e}")
    return '', 0.0


def fetch_usdkrw():
    """원/달러 환율 및 등락률 조회"""
    url = 'https://api.stock.naver.com/marketindex/exchange/FX_USDKRW'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        ex = r.get('exchangeInfo', {})
        close = ex.get('closePrice', '')
        ratio = float(ex.get('fluctuationsRatio', 0))
        diff = float(ex.get('changeValue', 0))
        return close, ratio, diff
    except Exception as e:
        logger.warning(f"환율 조회 실패: {e}")
    return '', 0.0, 0.0


def fetch_cnn_fear_greed():
    """CNN Fear & Greed Index 조회 (0~100)"""
    url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            fg = r.json().get('fear_and_greed', {})
            return float(fg.get('score', 50)), fg.get('rating', 'neutral')
    except Exception as e:
        logger.warning(f"CNN Fear & Greed 조회 실패: {e}")
    return 50.0, 'neutral'


def fetch_kr_market(code):
    """코스피/코스닥 지수 및 외인/기관 순매매 금액(억원) 조회"""
    close, ratio = '', 0.0
    foreign_str, inst_str = '0', '0'
    foreign_num, inst_num = 0, 0
    try:
        b = requests.get(f'https://m.stock.naver.com/api/index/{code}/basic', headers=HEADERS, timeout=8).json()
        close = b.get('closePrice', '')
        ratio = float(b.get('fluctuationsRatio', 0))
    except Exception as e:
        logger.warning(f"{code} 기본 정보 조회 실패: {e}")

    try:
        t = requests.get(f'https://m.stock.naver.com/api/index/{code}/trend', headers=HEADERS, timeout=8).json()
        foreign_str = t.get('foreignValue', '0')
        inst_str = t.get('institutionalValue', '0')
        foreign_num = int(foreign_str.replace(',', '').replace('+', '')) if foreign_str else 0
        inst_num = int(inst_str.replace(',', '').replace('+', '')) if inst_str else 0
    except Exception as e:
        logger.warning(f"{code} 수급 정보 조회 실패: {e}")

    return close, ratio, foreign_str, inst_str, foreign_num, inst_num


def make_gauge_bar(score, total_blocks=10):
    """0~100점 점수를 게이지 바로 변환"""
    filled = min(max(round(score / (100 / total_blocks)), 0), total_blocks)
    return '■' * filled + '░' * (total_blocks - filled)


# ==========================================================
# 1 & 2. [아침 07:40 / 08:40] 시초가 매도 타이밍 & 대응 가이드
# ==========================================================
def get_morning_sell_guide(time_label="07:40", is_nxt=True):
    nas_close, nas_ratio = fetch_naver_index('.IXIC')
    sox_close, sox_ratio = fetch_naver_index('.SOX')
    fut_price, fut_ratio = fetch_nasdaq_futures()
    fx_close, fx_ratio, _ = fetch_usdkrw()
    cnn_score, _ = fetch_cnn_fear_greed()

    # 시초가 갭 예측 점수 (0~100점)
    score = 50.0
    score += (nas_ratio * 12) * 0.30
    score += (sox_ratio * 12) * 0.25
    score += (fut_ratio * 15) * 0.30
    score -= (fx_ratio * 15) * 0.15
    score = min(max(round(score), 0), 100)

    gauge = make_gauge_bar(score)

    target_text = "08:00 NXT 프리마켓" if is_nxt else "09:00 정규장"

    if score >= 75:
        status_label = "🔥 강한 갭상승 출발 예상 (적극 분할 익절)"
        icon = "🟢"
        guide = (
            f"👉 <b>[{target_text} 시초가 슈팅 적극 분할 익절]</b>\n"
            f"미 증시 및 반도체 지수 강세로 {target_text} 개장 직후 강한 갭상승이 유력합니다.\n"
            f"• <b>매도 타이밍</b>: 개장 직후 5~10분간 시초 갭을 띄울 때 욕심부리지 말고 보유 물량의 <b>50~70%를 1차 익절</b>하세요.\n"
            f"• <b>홀딩 기준</b>: 잔여 물량은 '시초가'를 손절선(본절스탑)으로 잡고 상방 추세를 추종하세요."
        )
    elif score >= 55:
        status_label = "📈 완만한 상승/보합 출발 (슈팅 시 분할 익절)"
        icon = "🟢"
        guide = (
            f"👉 <b>[수급 확인 후 분할 익절]</b>\n"
            f"대외 환경이 완만하게 상승세를 뒷받침하고 있습니다.\n"
            f"• <b>매도 타이밍</b>: 개장 직후 체결강도와 수급 유입을 확인한 뒤 <b>+2~+4% 구간에서 분할 익절</b>을 시작하세요.\n"
            f"• <b>주의점</b>: 거래량이 줄며 시초가를 깨는 흐름이 나오면 미련 없이 남은 물량을 본절/약익절로 정리하세요."
        )
    elif score >= 40:
        status_label = "⚖️ 혼조/보합 출발 (개장 초 수급 확인 필수)"
        icon = "🟡"
        guide = (
            f"👉 <b>[장 초반 뇌동매매 자제 & 본절 방어]</b>\n"
            f"대외 지표가 엇갈리며 시초가 방향성이 팽팽합니다.\n"
            f"• <b>매도 타이밍</b>: 개장 정각에 섣불리 던지지 마시고, 첫 5분간 메이저 수급 방향을 지켜보세요.\n"
            f"• <b>원칙</b>: 전일 종가를 지지하면 1~2% 짧은 반등에 익절하고, 전일 종가를 하향 이탈하면 즉시 비중을 줄이세요."
        )
    else:
        status_label = "😨 갭하락 출발 우려 (투매 동참 금지, 반등 매도)"
        icon = "🔴"
        guide = (
            f"👉 <b>[시초가 패닉셀 금지 & 첫 반등 시 매도]</b>\n"
            f"미 증시 조정 여파로 시초가 갭하락 출발 가능성이 높습니다.\n"
            f"• <b>매도 타이밍</b>: 개장 직후 공포에 동참해 최저점에 던지지 마세요. 통상 개장 후 10~20분경 나오는 <b>'첫 기술적 반등 파동'</b>에서 비중을 축소하거나 분할 정리하는 것이 유리합니다."
        )

    title_desc = "08:00 NXT 프리마켓 개장 전" if is_nxt else "09:00 정규장 개장 전 최종"
    msg = f"🌅 <b>[{title_desc} 시초가 매도 가이드] {time_label}</b>\n"
    msg += f"점수: <b>{score}점</b> [{gauge}] {icon}\n"
    msg += f"<b>상태</b>: {status_label}\n\n"

    msg += "📊 <b>밤사이 글로벌 마켓 팩트</b>\n"
    if nas_close:
        sign = '+' if nas_ratio > 0 else ''
        arr = '🔺' if nas_ratio > 0 else ('🔻' if nas_ratio < 0 else '➖')
        msg += f"• 🇺🇸 <b>나스닥 마감</b>: {nas_close} ({sign}{nas_ratio:.2f}%) {arr}\n"
    if sox_close:
        sign = '+' if sox_ratio > 0 else ''
        arr = '🔺' if sox_ratio > 0 else ('🔻' if sox_ratio < 0 else '➖')
        msg += f"• 💻 <b>반도체(SOX)</b>: {sox_close} ({sign}{sox_ratio:.2f}%) {arr}\n"
    if fut_price:
        sign = '+' if fut_ratio > 0 else ''
        arr = '🔺' if fut_ratio > 0 else ('🔻' if fut_ratio < 0 else '➖')
        msg += f"• 🇺🇸 <b>E-mini 나스닥100 선물</b>: {fut_price:,.1f} ({sign}{fut_ratio:.2f}%) {arr}\n"
    if fx_close:
        sign = '+' if fx_ratio > 0 else ''
        fx_desc = '원화 강세' if fx_ratio < 0 else '원화 약세'
        msg += f"• 💱 <b>환율(USD/KRW)</b>: {fx_close}원 ({sign}{fx_ratio:.2f}%, {fx_desc})\n\n"

    msg += f"💡 <b>오늘의 시초가 매도 액션 플랜</b>\n{guide}"
    return msg


# ==========================================================
# 3. [오후 15:10] 정규장 1차 종가베팅 가이드
#    (15:30 KRX 정규장 마감 20분 전 판단)
# ==========================================================
def get_closing_betting_guide():
    fut_price, fut_ratio = fetch_nasdaq_futures()
    kp_close, kp_ratio, kp_for, kp_inst, kp_for_num, kp_inst_num = fetch_kr_market('KOSPI')
    kd_close, kd_ratio, kd_for, kd_inst, kd_for_num, kd_inst_num = fetch_kr_market('KOSDAQ')
    fx_close, fx_ratio, _ = fetch_usdkrw()

    score = 50.0
    score += (fut_ratio * 15) * 0.35

    total_major = kp_for_num + kp_inst_num + kd_for_num + kd_inst_num
    score += min(max(total_major / 150, -30), 30) * 0.35

    avg_kr_ratio = (kp_ratio + kd_ratio) / 2
    score += (avg_kr_ratio * 12) * 0.15
    score -= (fx_ratio * 15) * 0.15

    score = min(max(round(score), 0), 100)
    gauge = make_gauge_bar(score)

    if score >= 75:
        betting_label = "🟢 [정규장 적극 베팅 | 비중 60~80%]"
        guide = (
            "👉 <b>[주도 섹터 대장주 1차 종가베팅 추천]</b>\n"
            "외인/기관 메이저 수급이 장 막판까지 지수를 견고히 받치고 미 야간선물도 안정적입니다.\n"
            "• <b>공략 대상</b>: 당일 거래대금 최상위 & 신고가/눌림목 주도 섹터 1등주\n"
            "• <b>비중</b>: 투자금의 60~80% 수준으로 정규장 종가베팅이 유효합니다."
        )
    elif score >= 55:
        betting_label = "🟡 [선별 베팅 | 비중 30~50%]"
        guide = (
            "👉 <b>[확실한 재료주만 선별 베팅]</b>\n"
            "지수는 혼조세이나 특정 섹터로 수급이 집중되는 장세입니다.\n"
            "• <b>전략</b>: 실적 서프라이즈, 자사주 취득 등 개별 모멘텀이 확실한 종목만 30~50% 비중으로 분할 진입하세요.\n"
            "• <b>TIP</b>: 나머지 비중은 19:40 NXT 야간 마감 전 흐름을 보고 추가 진입 여부를 결정하세요."
        )
    elif score >= 40:
        betting_label = "🟠 [보수적 접근 | 비중 20% 이하]"
        guide = (
            "👉 <b>[비중 축소 & 현금 우위 유지]</b>\n"
            "수급 에너지가 분산되어 오버나잇 리스크가 있습니다.\n"
            "• <b>전략</b>: 무리하게 베팅하지 마시고 확실한 지지 라인이 확인된 종목만 20% 이하 소액 진입하세요."
        )
    else:
        betting_label = "🔴 [정규장 베팅 금지 | 전량 현금 100%]"
        guide = (
            "👉 <b>[15:30 정규장 종가베팅 금지]</b>\n"
            "외인/기관 양매도 또는 미 야간선물 급락세로 하방 압력이 큽니다.\n"
            "• <b>전략</b>: 정규장에서는 무리한 진입을 피하고, 장 마감 후 나오는 공시와 19:40 NXT 야간 가이드를 확인하세요."
        )

    msg = f"🎯 <b>[정규장 1차 종가베팅 가이드] 15:10</b>\n"
    msg += f"점수: <b>{score}점</b> [{gauge}]\n"
    msg += f"<b>신호</b>: {betting_label}\n\n"

    msg += "📊 <b>정규장 마감 핵심 지표 & 수급</b>\n"
    if fut_price:
        sign = '+' if fut_ratio > 0 else ''
        arr = '🔺' if fut_ratio > 0 else ('🔻' if fut_ratio < 0 else '➖')
        msg += f"• 🇺🇸 <b>E-mini 나스닥100 선물</b>: {fut_price:,.1f} ({sign}{fut_ratio:.2f}%) {arr}\n"
    if kp_close:
        kp_sign = '+' if kp_ratio > 0 else ''
        msg += f"• 🇰🇷 <b>코스피</b>: {kp_close} ({kp_sign}{kp_ratio:.2f}%) | 외인 {kp_for}억, 기관 {kp_inst}억\n"
    if kd_close:
        kd_sign = '+' if kd_ratio > 0 else ''
        msg += f"• 🇰🇷 <b>코스닥</b>: {kd_close} ({kd_sign}{kd_ratio:.2f}%) | 외인 {kd_for}억, 기관 {kd_inst}억\n"
    if fx_close:
        sign = '+' if fx_ratio > 0 else ''
        fx_desc = '원화 강세' if fx_ratio < 0 else '원화 약세'
        msg += f"• 💱 <b>환율(USD/KRW)</b>: {fx_close}원 ({sign}{fx_ratio:.2f}%, {fx_desc})\n\n"

    msg += f"💡 <b>정규장 종가베팅 전략</b>\n{guide}"
    return msg


# ==========================================================
# 4. [오후 19:40] NXT 20:00 마감 최종 종가베팅 가이드
#    (Nextrade 대체거래소/시간외 20:00 종료 20분 전 최종 오버나잇 판정)
# ==========================================================
def get_evening_betting_guide():
    fut_price, fut_ratio = fetch_nasdaq_futures()
    dax_close, dax_ratio = fetch_naver_index('.GDAXI')
    fx_close, fx_ratio, _ = fetch_usdkrw()
    cnn_score, cnn_rating = fetch_cnn_fear_greed()

    score = 50.0
    score += (fut_ratio * 18) * 0.45
    score += (dax_ratio * 12) * 0.20
    score += (cnn_score - 50) * 0.15
    score -= (fx_ratio * 15) * 0.20
    score = min(max(round(score), 0), 100)

    gauge = make_gauge_bar(score)

    if score >= 75:
        betting_label = "🟢 [NXT 야간 최종 베팅 적극 추천 | 비중 60~80%]"
        guide = (
            "👉 <b>[20:00 NXT 마감 전 최종 오버나잇 진입]</b>\n"
            "미국 프리마켓 선물이 강한 상승세를 유지하고 유럽 증시도 훈풍을 보이고 있습니다.\n"
            "• <b>공략 대상</b>: 오늘 정규장 마감 후 발표된 <b>호재 공시주(어닝 서프라이즈/자사주 취득)</b> 및 정규장 주도 대장주\n"
            "• <b>비중</b>: 총 투자금의 60~80% 수준으로 20:00 장 마감 전 적극적인 종가베팅 매수가 유효합니다.\n"
            "• <b>목표</b>: 내일 아침 08:00 NXT 프리마켓 & 09:00 정규장 시초 갭상승 익절!"
        )
    elif score >= 55:
        betting_label = "🟡 [선별 베팅 | 비중 30~50%]"
        guide = (
            "👉 <b>[호재 공시주 중심 소액 선별 베팅]</b>\n"
            "미 선물이 보합권에서 방향성을 탐색하고 있습니다.\n"
            "• <b>공략 대상</b>: 지수 연동 대형주보다는 장 마감 후 확실한 실적 서프라이즈나 자사주 공시가 뜬 개별주 위주로 공략하세요.\n"
            "• <b>비중</b>: 비중 30~50% 이내로 조절하여 안정적으로 분할 진입하세요."
        )
    elif score >= 40:
        betting_label = "🟠 [보수적 접근 | 비중 20% 이하]"
        guide = (
            "👉 <b>[야간 변동성 주의 & 소액 접근]</b>\n"
            "미 선물 변동성이 감지되거나 환율 하방 압력이 존재합니다.\n"
            "• <b>원칙</b>: 무리하게 오버나잇 비중을 늘리지 마시고, 확신이 드는 종목만 20% 미만으로 가볍게 담고 현금을 우선하세요."
        )
    else:
        betting_label = "🔴 [야간 종가베팅 절대 금지 | 전량 현금 100%]"
        guide = (
            "👉 <b>[20:00 마감 전 오버나잇 절대 금지]</b>\n"
            "미국 야간 선물이 하락세를 보이거나 글로벌 리스크가 발생했습니다.\n"
            "• <b>전략</b>: 오늘 밤 종가베팅 진입 시 내일 아침 시초가 갭하락 맞을 위험이 대단히 높습니다.\n"
            "• <b>원칙</b>: 20:00 NXT 거래 종료 전 전량 현금화하여 리스크 없이 편안하게 마감하세요."
        )

    msg = f"🎯 <b>[NXT 8시 마감 최종 종가베팅 가이드] 19:40</b>\n"
    msg += f"최종 점수: <b>{score}점</b> [{gauge}]\n"
    msg += f"<b>신호</b>: {betting_label}\n\n"

    msg += "📊 <b>야간 글로벌 마켓 현황</b>\n"
    if fut_price:
        sign = '+' if fut_ratio > 0 else ''
        arr = '🔺' if fut_ratio > 0 else ('🔻' if fut_ratio < 0 else '➖')
        msg += f"• 🇺🇸 <b>E-mini 나스닥100 선물</b>: {fut_price:,.1f} ({sign}{fut_ratio:.2f}%) {arr}\n"
    if dax_close:
        sign = '+' if dax_ratio > 0 else ''
        arr = '🔺' if dax_ratio > 0 else ('🔻' if dax_ratio < 0 else '➖')
        msg += f"• 🇪🇺 <b>유럽(독일 DAX)</b>: {dax_close} ({sign}{dax_ratio:.2f}%) {arr}\n"
    if fx_close:
        sign = '+' if fx_ratio > 0 else ''
        fx_desc = '원화 강세' if fx_ratio < 0 else '원화 약세'
        msg += f"• 💱 <b>야간 환율(USD/KRW)</b>: {fx_close}원 ({sign}{fx_ratio:.2f}%, {fx_desc})\n"
    msg += f"• 🧭 <b>글로벌 심리(CNN)</b>: {cnn_score:.0f}점 ({cnn_rating})\n\n"

    msg += f"💡 <b>20:00 마감 전 최종 종가베팅 전략</b>\n{guide}"
    return msg


# ==========================================================
# 통합 디스패처: 시간에 따라 자동 분기
# ==========================================================
def get_market_score_message(mode=None):
    """
    지정된 mode 또는 현재 KST 시간에 맞춰 4대 가이드 반환
    1. 07:40 타임 (06:00~08:15 KST) -> [08:00 NXT 프리마켓 시초가 매도 가이드]
    2. 08:40 타임 (08:15~10:59 KST) -> [09:00 정규장 개장 최종 매도 가이드]
    3. 15:10 타임 (11:00~16:59 KST) -> [정규장 1차 종가베팅 가이드]
    4. 19:40 타임 (17:00~05:59 KST) -> [NXT 8시 마감 최종 종가베팅 가이드]
    """
    if not mode or mode == 'auto':
        now_kst = datetime.now(KST)
        hour = now_kst.hour
        minute = now_kst.minute

        if (hour == 6) or (hour == 7) or (hour == 8 and minute < 15):
            mode = 'morning_740'
        elif 8 <= hour < 11:
            mode = 'morning_840'
        elif 11 <= hour < 17:
            mode = 'closing'
        else:
            mode = 'night'

    if mode in ('morning_740', 'morning'):
        return get_morning_sell_guide(time_label="07:40", is_nxt=True)
    elif mode == 'morning_840':
        return get_morning_sell_guide(time_label="08:40", is_nxt=False)
    elif mode == 'closing':
        return get_closing_betting_guide()
    else:
        return get_evening_betting_guide()
