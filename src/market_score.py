"""
글로벌 심리(CNN Fear & Greed) + 미 증시 + 환율 + 수급 기반
오늘의 시장 종합 스코어(0~100점) 및 해설 생성 모듈
"""
import logging
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}


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


def fetch_nasdaq():
    """전일 미 증시(나스닥) 종가 및 등락률 조회"""
    url = 'https://api.stock.naver.com/index/.IXIC/basic'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        ratio = float(r.get('fluctuationsRatio', 0))
        close = r.get('closePrice', '')
        return ratio, close
    except Exception as e:
        logger.warning(f"나스닥 지수 조회 실패: {e}")
    return 0.0, ''


def fetch_usdkrw():
    """원/달러 환율 및 등락률 조회"""
    url = 'https://api.stock.naver.com/marketindex/exchange/FX_USDKRW'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        ex = r.get('exchangeInfo', {})
        close = ex.get('closePrice', '')
        ratio = float(ex.get('fluctuationsRatio', 0))
        return ratio, close
    except Exception as e:
        logger.warning(f"환율 조회 실패: {e}")
    return 0.0, ''


def fetch_kospi_investor():
    """코스피 외국인/기관 순매수 동향 조회"""
    url = 'https://m.stock.naver.com/api/index/KOSPI/trend'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8).json()
        foreign_val = r.get('foreignValue', '')
        foreign_num = int(foreign_val.replace(',', '').replace('+', '')) if foreign_val else 0
        return foreign_val, foreign_num
    except Exception as e:
        logger.warning(f"수급 동향 조회 실패: {e}")
    return '', 0


def calculate_score(cnn_score, nas_ratio, usdkrw_ratio, foreign_num):
    """
    하이브리드 가중치 기반 종합 시황 점수 산출 (0~100)
    - CNN Fear & Greed (40%)
    - 나스닥 등락률 (30%)
    - 원/달러 환율 변동률 (15%)
    - 코스피 외국인 수급 (15%)
    """
    score = cnn_score * 0.40
    nas_norm = min(max(50 + nas_ratio * 15, 0), 100)
    score += nas_norm * 0.30
    fx_norm = min(max(50 - usdkrw_ratio * 15, 0), 100)
    score += fx_norm * 0.15
    fr_norm = min(max(50 + (foreign_num / 100), 0), 100)
    score += fr_norm * 0.15
    return min(max(round(score), 0), 100)


def generate_commentary(score, cnn_score, nas_ratio, usdkrw_ratio, foreign_num):
    """점수와 지표를 바탕으로 한 친절하고 명쾌한 시황 분석 & 투자 가이드 생성"""
    drivers_positive = []
    drivers_cautious = []

    # 미 증시 평가
    if nas_ratio >= 1.0:
        drivers_positive.append("미 기술주(나스닥)의 강한 반등")
    elif nas_ratio > 0:
        drivers_positive.append("미 증시의 안정적인 상승 흐름")
    elif nas_ratio <= -1.0:
        drivers_cautious.append("미 증시 급락에 따른 하방 압력")
    elif nas_ratio < 0:
        drivers_cautious.append("미 증시의 조정 양상")

    # 환율 평가
    if usdkrw_ratio <= -0.2:
        drivers_positive.append("원/달러 환율 하락(원화 강세)")
    elif usdkrw_ratio >= 0.2:
        drivers_cautious.append("환율 상승(원화 약세)에 따른 수급 부담")

    # 수급 평가
    if foreign_num >= 1000:
        drivers_positive.append("외국인의 적극적인 순매수세")
    elif foreign_num <= -1000:
        drivers_cautious.append("외국인 매도 우위 지속")

    # 심리 요약
    context = ""
    if drivers_positive and not drivers_cautious:
        context = f"{', '.join(drivers_positive)}으로 전반적인 투자 심리가 개선된 모습입니다."
    elif drivers_cautious and not drivers_positive:
        context = f"{', '.join(drivers_cautious)}으로 시장 내 경계 심리가 우세합니다."
    elif drivers_positive and drivers_cautious:
        context = f"{', '.join(drivers_positive)} 호재와 {', '.join(drivers_cautious)} 경계감이 공존하고 있습니다."
    else:
        context = "대외 매크로 변수들이 균형을 이루며 방향성을 탐색하고 있습니다."

    # 행동 전략 가이드
    if score >= 75:
        guide = "위험자산 선호가 높은 과열 국면입니다. 단기 급등주 추격 매수보다는 분할 익절 및 리스크 관리가 유리합니다."
    elif score >= 58:
        guide = "우호적인 대외 환경 속에서 상승 탄력이 기대됩니다. 실적 개선주와 시장 주도 섹터 중심의 공략이 유효합니다."
    elif score >= 45:
        guide = "방향성을 모색하는 혼조/관망 구간입니다. 무리한 베팅보다는 실적 및 개별 공시 모멘텀을 확인하며 차분히 대응하세요."
    elif score >= 25:
        guide = "시장 경계 심리가 짙은 약세 구간입니다. 비중 확대를 서두르기보다 현금을 확보하며 지지선 확인이 필요합니다."
    else:
        guide = "극도의 공포 심리로 시장이 과매도권에 진입했습니다. 우량 종목의 중장기 분할 매수 기회로 활용할 수 있습니다."

    return f"{context} {guide}"


def get_market_score_message():
    """오늘의 시황 종합 점수 + 게이지 + 3대 요소 + 친절한 해설 메시지 반환"""
    cnn_score, cnn_rating = fetch_cnn_fear_greed()
    nas_ratio, nas_close = fetch_nasdaq()
    usdkrw_ratio, usdkrw_close = fetch_usdkrw()
    foreign_val, foreign_num = fetch_kospi_investor()

    score = calculate_score(cnn_score, nas_ratio, usdkrw_ratio, foreign_num)

    # 구간별 아이콘 및 상태 레이블
    if score >= 75:
        status_label = "🔥 과열 (탐욕 우세)"
        icon = "🟢"
    elif score >= 58:
        status_label = "📈 상승 우세 (매수 우위)"
        icon = "🟢"
    elif score >= 45:
        status_label = "⚖️ 중립 (혼조/관망세)"
        icon = "🟡"
    elif score >= 25:
        status_label = "😨 공포 (경계 구간)"
        icon = "🟠"
    else:
        status_label = "🥶 극도의 공포 (과매도/바닥권)"
        icon = "🔴"

    # 게이지 바 (10칸)
    filled = min(max(round(score / 10), 0), 10)
    gauge_bar = '■' * filled + '░' * (10 - filled)

    commentary = generate_commentary(score, cnn_score, nas_ratio, usdkrw_ratio, foreign_num)

    # 텔레그램 메시지 조립
    msg = f"🧭 <b>오늘의 시황 종합 점수: {score}점</b> {icon}\n"
    msg += f"   [{gauge_bar}] <b>{status_label}</b>\n\n"

    msg += "📊 <b>핵심 3요소 현황</b>\n"
    if nas_close:
        nas_sign = '+' if nas_ratio > 0 else ''
        nas_arrow = '🔺' if nas_ratio > 0 else ('🔻' if nas_ratio < 0 else '➖')
        msg += f"• 🇺🇸 <b>미 증시(나스닥)</b>: {nas_close} ({nas_sign}{nas_ratio:.2f}%) {nas_arrow}\n"
    if usdkrw_close:
        fx_sign = '+' if usdkrw_ratio > 0 else ''
        fx_desc = '원화 강세' if usdkrw_ratio < 0 else '원화 약세'
        msg += f"• 💱 <b>환율(USD/KRW)</b>: {usdkrw_close}원 ({fx_sign}{usdkrw_ratio:.2f}%, {fx_desc})\n"
    fr_display = f"코스피 외인 {foreign_val}억" if foreign_val else "외인 수급 집계중"
    msg += f"• 🧭 <b>심리/수급</b>: CNN 공포탐욕 {cnn_score:.0f}점 | {fr_display}\n\n"

    msg += f"💡 <b>오늘의 시황 분석 & 가이드</b>\n{commentary}"

    return msg
