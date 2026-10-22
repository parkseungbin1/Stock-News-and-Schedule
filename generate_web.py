"""
비니stock 웹 대시보드 (index.html) 정적 생성 스크립트
실시간 시황 데이터, E-mini 나스닥 선물, 외인/기관 수급, 최근 핵심 공시를 수집하여
초프리미엄 반응형 다크모드 대시보드(HTML/CSS)를 생성합니다.
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows 콘솔 출력 인코딩 안전화
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

from src.market_score import (
    fetch_nasdaq_futures,
    fetch_naver_index,
    fetch_usdkrw,
    fetch_cnn_fear_greed,
    fetch_kr_market,
    fetch_vix,
    fetch_us10y,
    get_market_score_message,
)
from src import recommender

KST = timezone(timedelta(hours=9))


def generate_html():
    now_kst = datetime.now(KST)
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")

    # 1. 시황 지표 수집
    fut_price, fut_ratio = fetch_nasdaq_futures()
    nas_close, nas_ratio = fetch_naver_index('.IXIC')
    sox_close, sox_ratio = fetch_naver_index('.SOX')
    dax_close, dax_ratio = fetch_naver_index('.GDAXI')
    fx_close, fx_ratio, fx_diff = fetch_usdkrw()
    cnn_score, cnn_rating = fetch_cnn_fear_greed()
    vix_close, vix_ratio = fetch_vix()
    us10y_price, us10y_diff = fetch_us10y()

    kp_close, kp_ratio, kp_for, kp_inst, kp_for_num, kp_inst_num = fetch_kr_market('KOSPI')
    kd_close, kd_ratio, kd_for, kd_inst, kd_for_num, kd_inst_num = fetch_kr_market('KOSDAQ')

    # 2. 4대 가이드 메시지 수집
    guide_0740 = get_market_score_message('morning_740')
    guide_0840 = get_market_score_message('morning_840')
    guide_1510 = get_market_score_message('closing')
    guide_1940 = get_market_score_message('night')

    # Python 3.12 미만 호환: f-string 표현식 내부 백슬래시 금지 → 미리 이스케이프
    bt, bt_esc = '`', '\\`'
    g0740_js = guide_0740.replace(bt, bt_esc)
    g0840_js = guide_0840.replace(bt, bt_esc)
    g1510_js = guide_1510.replace(bt, bt_esc)
    g1940_js = guide_1940.replace(bt, bt_esc)

    # 2-1. AI 실전 추천 종목 수집 (종가베팅 & 2~5일 스윙)
    market_ctx = {
        'fut_ratio': fut_ratio,
        'kp_for_num': kp_for_num,
        'kd_for_num': kd_for_num,
        'cnn_score': cnn_score,
        'vix_close': vix_close,
    }
    try:
        rec_data = recommender.get_recommendations(market_context=market_ctx)
        rec_regime = rec_data.get('regime', {})
        closing_picks = rec_data.get('closing', [])
        swing_picks = rec_data.get('swing', [])
        breakout_picks = rec_data.get('breakout', [])
    except Exception as e:
        print(f"추천 종목 수집 실패: {e}")
        fallback = recommender.get_fallback_recommendations()
        rec_regime = fallback.get('regime', {})
        closing_picks = fallback['closing']
        swing_picks = fallback['swing']
        breakout_picks = fallback.get('breakout', [])

    def render_rec_card(pick, card_theme):
        tags_html = "".join([f'<span class="rec-tag">{t}</span>' for t in pick.get('tags', [])])
        change_val = pick['change_pct']
        change_class = 'up' if change_val > 0 else ('down' if change_val < 0 else '')
        sign = '+' if change_val > 0 else ''
        return f"""
        <div class="rec-card {card_theme}">
            <div class="rec-card-top">
                <div class="rec-stock-title">
                    <a href="https://finance.naver.com/item/main.naver?code={pick['code']}" target="_blank" rel="noopener noreferrer">
                        {pick['name']} <span class="rec-code">{pick['code']}</span>
                    </a>
                    <span class="rec-market-badge">{pick['market']}</span>
                </div>
                <div class="rec-score-badge">⭐ AI 적중도 {pick['score']}점</div>
            </div>

            <div class="rec-price-row">
                <div>
                    <span class="rec-label">추천 매수가</span>
                    <span class="rec-price">{pick['price']:,}원</span>
                </div>
                <div class="rec-change-box {change_class}">
                    {sign}{change_val:.2f}% ({pick['amount_eok']:,}억)
                </div>
            </div>

            <div class="rec-target-box">
                <div class="target-col col-t1">
                    <div class="t-label">1차 목표가 ({pick['target_1_pct']})</div>
                    <div class="t-val">{pick['target_1']:,}원</div>
                </div>
                <div class="target-col col-t2">
                    <div class="t-label">2차 목표가 ({pick['target_2_pct']})</div>
                    <div class="t-val">{pick['target_2']:,}원</div>
                </div>
                <div class="target-col col-sl">
                    <div class="t-label">손절 기준 ({pick['stop_loss_pct']})</div>
                    <div class="t-val">{pick['stop_loss']:,}원</div>
                </div>
            </div>

            <div class="rec-desc-box">
                <div class="rec-desc-title">💡 AI 포착 근거:</div>
                <div class="rec-desc-text">{pick['reason']}</div>
                <div class="rec-period-tag">⏱️ 매매 타이밍: {pick['holding_period']}</div>
            </div>

            <div class="rec-tags-row">
                {tags_html}
            </div>
        </div>
        """

    closing_cards_html = "".join([render_rec_card(p, "theme-closing") for p in closing_picks])
    swing_cards_html = "".join([render_rec_card(p, "theme-swing") for p in swing_picks])
    breakout_cards_html = "".join([render_rec_card(p, "theme-breakout") for p in breakout_picks])

    # 3. 최근 공시 수집 및 카테고리별 분리
    earnings_cards = []
    buyback_cards = []
    ir_cards = []

    def render_disc_card(block, badge_class, badge_label, card_type):
        b = block.replace('<a href=', '<a target="_blank" rel="noopener noreferrer" href=')
        is_watch = '⭐' in b
        b_clean = b.replace('⭐', '').strip()
        lines = [l.strip() for l in b_clean.split('\n') if l.strip()]
        if not lines:
            return ""
        header_text = lines[0]
        details_html = ""
        if len(lines) > 1:
            details_joined = "<br>".join(lines[1:])
            details_html = f"<div class='card-details'>{details_joined}</div>"
        watch_tag = ""
        if is_watch:
            if "어닝서프라이즈" in b:
                watch_tag = '<span class="watch-tag tag-surprise">⭐ 어닝 서프라이즈</span>'
            elif "흑자전환" in b:
                watch_tag = '<span class="watch-tag tag-turnaround">⭐ 흑자전환</span>'
            elif "YoY +" in b:
                watch_tag = '<span class="watch-tag tag-growth">⭐ 실적 급증</span>'
            elif "자사주" in b:
                watch_tag = '<span class="watch-tag tag-buyback">⭐ 대규모 자사주</span>'
            else:
                watch_tag = '<span class="watch-tag">⭐ 핵심 포착</span>'
        watch_card_class = " is-watchlist" if is_watch else ""
        return f"""
        <div class="disclosure-card {card_type}{watch_card_class}">
            <div class="card-top-row">
                <span class="badge {badge_class}">{badge_label}</span>
                {watch_tag}
            </div>
            <div class="card-main-title">{header_text}</div>
            {details_html}
        </div>
        """

    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('DART_API_KEY')
        if api_key:
            from src import disclosure as d
            dart = d.Dart(api_key)
            # 상태를 변경하지 않는 가상 state로 최근 공시 조회
            temp_state = {'seen': [], 'ir_dates': {}}
            watch = d.load_watchlist()
            sections = d.collect_new_disclosures(dart, temp_state, watch)
            if sections:
                for title, blocks in sections:
                    if "실적" in title:
                        for block in blocks:
                            earnings_cards.append(render_disc_card(block, "badge-green", "📈 실적공시", "type-earnings"))
                    elif "자사주" in title:
                        for block in blocks:
                            buyback_cards.append(render_disc_card(block, "badge-gold", "💰 자사주", "type-buyback"))
                    elif "IR" in title:
                        for block in blocks:
                            ir_cards.append(render_disc_card(block, "badge-purple", "🎤 IR일정", "type-ir"))
    except Exception as e:
        print(f"공시 수집 중 오류: {e}")

    earnings_count = len(earnings_cards)
    buyback_count = len(buyback_cards)
    ir_count = len(ir_cards)
    total_disc_count = earnings_count + buyback_count + ir_count

    earnings_html = "".join(earnings_cards)
    buyback_html = "".join(buyback_cards)
    ir_html = "".join(ir_cards)

    # 지표 카드 도우미
    def format_ratio(val):
        if val > 0:
            return f"<span class='up'>+{val:.2f}% 🔺</span>"
        elif val < 0:
            return f"<span class='down'>{val:.2f}% 🔻</span>"
        return f"<span>{val:.2f}% ➖</span>"

    fut_display = f"{fut_price:,.1f}" if fut_price else "-"
    fut_badge = format_ratio(fut_ratio)

    sox_display = sox_close or "-"
    sox_badge = format_ratio(sox_ratio)

    nas_display = nas_close or "-"
    nas_badge = format_ratio(nas_ratio)

    fx_display = f"{fx_close}원" if fx_close else "-"
    fx_badge = format_ratio(fx_ratio)

    kp_display = kp_close or "-"
    kp_badge = format_ratio(kp_ratio)

    kd_display = kd_close or "-"
    kd_badge = format_ratio(kd_ratio)

    vix_display = vix_close or "-"
    vix_badge = format_ratio(vix_ratio) if vix_close else "<span>-</span>"

    us10y_display = f"{us10y_price:.2f}%" if us10y_price else "-"
    if us10y_diff and us10y_diff > 0:
        us10y_badge = f"<span class='up'>+{us10y_diff:.2f}%p 🔺</span>"
    elif us10y_diff and us10y_diff < 0:
        us10y_badge = f"<span class='down'>{us10y_diff:.2f}%p 🔻</span>"
    else:
        us10y_badge = "<span>0.00%p ➖</span>"

    # 8대 시장 지표별 호재/악재 판정 배지 및 실전 영향 설명문 산출
    # 1) E-mini 나스닥100 선물
    if fut_ratio >= 0.5:
        fut_impact_badge = '<span class="impact-badge impact-good">🟢 강력 호재</span>'
        fut_impact_desc = "야간 미 증시 랠리 지속. 내일 아침 국내 증시 시초가 갭상승 출발 기대"
    elif fut_ratio >= 0.0:
        fut_impact_badge = '<span class="impact-badge impact-good">🟢 호재 (상승)</span>'
        fut_impact_desc = "미 선물 완만한 상승. 내일 국내 시초가 안정적 방어 및 강보합 출발 우호적"
    elif fut_ratio >= -0.5:
        fut_impact_badge = '<span class="impact-badge impact-neutral">⚪ 중립 (약보합)</span>'
        fut_impact_desc = "미 선물 소폭 하락. 시초가 보합권 출발 예상, 장초반 외인 매매 확인 필요"
    else:
        fut_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (하락주의)</span>'
        fut_impact_desc = "야간 미 선물 급락. 내일 아침 시초가 갭하락 및 하방 매물 출회 주의"

    # 2) 필라델피아 반도체 지수
    if sox_ratio >= 1.0:
        sox_impact_badge = '<span class="impact-badge impact-good">🟢 강력 호재</span>'
        sox_impact_desc = "미 반도체 급등. 삼성전자, SK하이닉스 및 국내 소부장 테마 강한 상승 견인"
    elif sox_ratio > 0.0:
        sox_impact_badge = '<span class="impact-badge impact-good">🟢 호재 (상승)</span>'
        sox_impact_desc = "글로벌 IT 섹터 호조. 국내 반도체 대형주 중심 지수 상승 분위기 조성"
    elif sox_ratio >= -1.0:
        sox_impact_badge = '<span class="impact-badge impact-neutral">⚪ 중립 (보합)</span>'
        sox_impact_desc = "반도체 지수 소폭 조정. 섹터 전체보다 실적 우량 개별 소부장주 차별화"
    else:
        sox_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (하락압력)</span>'
        sox_impact_desc = "미 반도체 급락. 국내 반도체 대형주 하방 압력으로 지수 전반 위축 가능성"

    # 3) 코스피 & 수급
    kp_num = kp_for_num if kp_for_num is not None else 0
    if kp_num >= 1000:
        kp_impact_badge = '<span class="impact-badge impact-good">🟢 순매수 (호재)</span>'
        kp_impact_desc = "외국인이 지수를 견인 중. 코스피 대형주 및 지수 전반의 상승 탄력 강화"
    elif kp_num >= 0:
        kp_impact_badge = '<span class="impact-badge impact-neutral">⚪ 매수 우위</span>'
        kp_impact_desc = "외국인 소폭 순매수. 하방 경직성을 확보하며 안정적인 지수 흐름 뒷받침"
    elif kp_num >= -1000:
        kp_impact_badge = '<span class="impact-badge impact-caution">🟡 주의 (매도)</span>'
        kp_impact_desc = "외국인 단기 차익 실현. 지수 상단 제한, 순환매 및 방어적 대응 유리"
    else:
        kp_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (외인 이탈)</span>'
        kp_impact_desc = "외국인 대규모 매도세. 대형주 중심 지수 하방 압력 지속, 무리한 추격매수 자제"

    # 4) 코스닥 & 수급
    kd_num = kd_for_num if kd_for_num is not None else 0
    if kd_num >= 500:
        kd_impact_badge = '<span class="impact-badge impact-good">🟢 순매수 (호재)</span>'
        kd_impact_desc = "외인 매수세 유입. 바이오, 2차전지, AI 등 성장 테마주의 탄력적인 슈팅 기대"
    elif kd_num >= 0:
        kd_impact_badge = '<span class="impact-badge impact-neutral">⚪ 수급 안정</span>'
        kd_impact_desc = "외인 수급 균형. 테마주 종가베팅 시 비교적 양호한 성공 확률 기대"
    elif kd_num >= -500:
        kd_impact_badge = '<span class="impact-badge impact-caution">🟡 주의 (차익실현)</span>'
        kd_impact_desc = "외인 차익 실현 중. 개별 호재 및 실적 모멘텀이 확실한 주도주로 압축 대응"
    else:
        kd_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (매도압력)</span>'
        kd_impact_desc = "외인 강한 매도세. 코스닥 중소형주 변동성 확대, 종가베팅 비중 축소 권장"

    # 5) 원/달러 환율 (환율 하락 = 원화 강세 = 호재)
    if fx_ratio <= -0.3:
        fx_impact_badge = '<span class="impact-badge impact-good">🟢 원화강세 (호재)</span>'
        fx_impact_desc = "환율 하락으로 외인 환차익 매력 증가. 국내 증시 외국인 자금 유입 촉진"
    elif fx_ratio <= 0.2:
        fx_impact_badge = '<span class="impact-badge impact-neutral">⚪ 환율 안정</span>'
        fx_impact_desc = "환율 등락폭 제한적. 외국인 수급에 특별한 이탈 압력 없이 중립적 작용"
    elif fx_ratio <= 0.7:
        fx_impact_badge = '<span class="impact-badge impact-caution">🟡 주의 (환율상승)</span>'
        fx_impact_desc = "원화 약세 진행 중. 외국인 매수세 유입이 제한되고 관망세가 짙어질 수 있음"
    else:
        fx_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (환율급등)</span>'
        fx_impact_desc = "환율 급등으로 외인 환차손 회피 투매 위험. 외국인 자금 이탈 경계 필요"

    # 6) CNN 공포 & 탐욕 지수
    if cnn_score <= 25:
        cnn_impact_badge = '<span class="impact-badge impact-caution">🟡 극단적 공포 (반등기회)</span>'
        cnn_impact_desc = "시장 공포 극대화 구간. 단기 투매 위험 있으나 역발상 저가 매수세/기술적 반등 임박"
    elif cnn_score <= 45:
        cnn_impact_badge = '<span class="impact-badge impact-caution">🟡 공포 (조정구간)</span>'
        cnn_impact_desc = "투자 심리 위축. 시장에 불안감이 팽배한 상태로 우량주 분할 매수 고려 영역"
    elif cnn_score <= 55:
        cnn_impact_badge = '<span class="impact-badge impact-neutral">⚪ 중립 (균형상태)</span>'
        cnn_impact_desc = "공포와 탐욕 균형. 매크로 충격보다 개별 종목 재료와 실적에 정직하게 반응"
    elif cnn_score <= 75:
        cnn_impact_badge = '<span class="impact-badge impact-good">🟢 호재 (낙관적 탐욕)</span>'
        cnn_impact_desc = "투자 심리 강세. 지수 상승 탄력이 좋고 종가베팅 성공 확률이 높은 우호적 환경"
    else:
        cnn_impact_badge = '<span class="impact-badge impact-bad">🔴 주의 (극단적 탐욕/과열)</span>'
        cnn_impact_desc = "시장 과열 극치. 누구나 수익 중인 위험 구간, 차익 매물 출회 및 고점 상투 경계"

    # 7) VIX 변동성 지수
    vix_val = None
    if vix_close:
        try:
            vix_val = float(str(vix_close).replace(',', ''))
        except Exception:
            vix_val = None

    if vix_val is not None:
        if vix_val < 18:
            vix_impact_badge = '<span class="impact-badge impact-good">🟢 안정 (호재)</span>'
            vix_impact_desc = "월가 공포가 매우 낮고 안정적. 급락 위험이 적어 종가베팅 및 오버나잇 유리"
        elif vix_val < 23:
            vix_impact_badge = '<span class="impact-badge impact-neutral">⚪ 보통 (정상범위)</span>'
            vix_impact_desc = "통상적인 변동성 수준. 시스템 리스크 없이 테마주와 지수가 정상적으로 전개"
        elif vix_val < 30:
            vix_impact_badge = '<span class="impact-badge impact-caution">🟡 경계 (변동성확대)</span>'
            vix_impact_desc = "월가 불안감 급증. 지수 등락폭이 커지고 장중 변동성이 심하므로 목표수익 짧게 대응"
        else:
            vix_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (패닉셀위험)</span>'
            vix_impact_desc = "시장 패닉 상태(30 이상). 지수 급락 및 투매 발생 위험 높아 현금 비중 확대 필수"
    else:
        vix_impact_badge = '<span class="impact-badge impact-neutral">⚪ 데이터 대기</span>'
        vix_impact_desc = "월가 공포지수 수집 대기 중"

    # 8) 미국 10년물 국채금리
    if us10y_diff is not None and us10y_diff <= -0.03:
        us10y_impact_badge = '<span class="impact-badge impact-good">🟢 호재 (금리하락)</span>'
        us10y_impact_desc = "글로벌 긴축 완화 신호. 기술주, 2차전지, 바이오 등 성장주 밸류에이션 부담 완화"
    elif us10y_diff is not None and abs(us10y_diff) < 0.03:
        us10y_impact_badge = '<span class="impact-badge impact-neutral">⚪ 보합 (금리안정)</span>'
        us10y_impact_desc = "채권 금리 안정세. 주식 시장 밸류에이션에 미치는 영향이 중립적"
    elif us10y_diff is not None and us10y_diff > 0.03:
        us10y_impact_badge = '<span class="impact-badge impact-bad">🔴 악재 (금리급등)</span>'
        us10y_impact_desc = "고금리 긴축 우려 재부각. 유동성 축소로 성장주 및 기술주에 주가 하방 압력"
    else:
        us10y_impact_badge = '<span class="impact-badge impact-neutral">⚪ 보합</span>'
        us10y_impact_desc = "글로벌 벤치마크 금리가 기준선 부근에서 안정적인 흐름 유지"

    # HTML 템플릿
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>비니stock 실전 트레이딩 대시보드</title>
    <meta name="description" content="E-mini 나스닥 100 선물, 외인/기관 수급, 종가베팅 & 시초가 매도 타이밍 실시간 분석 대시보드">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: rgba(255, 255, 255, 0.08);
            --text-main: #f9fafb;
            --text-sub: #9ca3af;
            --primary: #3b82f6;
            --up: #ef4444;
            --down: #3b82f6;
            --green: #10b981;
            --gold: #f59e0b;
            --purple: #8b5cf6;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg);
            color: var(--text-main);
            font-family: 'Pretendard', -apple-system, sans-serif;
            padding: 16px;
            max-width: 1200px;
            margin: 0 auto;
            line-height: 1.5;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 0 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .logo-area h1 {{
            font-size: 1.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .time-badge {{
            font-size: 0.82rem;
            color: var(--text-sub);
            font-family: 'JetBrains Mono', monospace;
            background: rgba(255,255,255,0.05);
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid var(--border);
        }}
        .live-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            margin-right: 6px;
            box-shadow: 0 0 10px #10b981;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.7; }}
            50% {{ transform: scale(1.2); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.7; }}
        }}

        /* 지표 그리드 */
        .grid-indicators {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 14px;
            margin-bottom: 28px;
        }}
        .metric-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
        }}
        .metric-card:hover {{
            border-color: rgba(255,255,255,0.22);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        }}
        .metric-top-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            gap: 6px;
        }}
        .metric-label {{
            font-size: 0.82rem;
            color: var(--text-sub);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .impact-badge {{
            font-size: 0.72rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 999px;
            white-space: nowrap;
        }}
        .impact-good {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }}
        .impact-bad {{
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.35);
        }}
        .impact-caution {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }}
        .impact-neutral {{
            background: rgba(156, 163, 175, 0.15);
            color: #e5e7eb;
            border: 1px solid rgba(156, 163, 175, 0.3);
        }}
        .metric-main-row {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 2px;
        }}
        .metric-value {{
            font-size: 1.4rem;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            color: #ffffff;
        }}
        .up {{ color: #f87171; }}
        .down {{ color: #60a5fa; }}
        .metric-sub {{
            font-size: 0.78rem;
            color: var(--text-sub);
            margin-bottom: 10px;
        }}
        .metric-desc {{
            background: rgba(0, 0, 0, 0.32);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 9px 11px;
            font-size: 0.78rem;
            line-height: 1.45;
            color: #d1d5db;
            margin-top: auto;
        }}
        .metric-desc-title {{
            color: #9ca3af;
            font-weight: 700;
            font-size: 0.72rem;
            margin-bottom: 3px;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .metric-desc-text {{
            color: #f3f4f6;
        }}

        /* 섹션 제목 */
        .section-title {{
            font-size: 1.15rem;
            font-weight: 700;
            margin: 28px 0 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* AI 시장 안전도 레짐 배너 */
        .rec-market-alert {{
            border-radius: 14px;
            padding: 14px 18px;
            margin-bottom: 18px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            border: 1px solid var(--border);
            transition: all 0.2s;
        }}
        .regime-warning {{
            background: rgba(239, 68, 68, 0.12);
            border-color: rgba(239, 68, 68, 0.4);
        }}
        .regime-bull {{
            background: rgba(16, 185, 129, 0.12);
            border-color: rgba(16, 185, 129, 0.4);
        }}
        .regime-neutral {{
            background: rgba(59, 130, 246, 0.08);
            border-color: rgba(59, 130, 246, 0.28);
        }}
        .regime-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .regime-badge {{
            font-size: 0.95rem;
            font-weight: 800;
        }}
        .regime-advice {{
            font-size: 0.82rem;
            color: #d1d5db;
        }}
        .regime-advice b {{
            color: #ffffff;
            background: rgba(255, 255, 255, 0.12);
            padding: 3px 9px;
            border-radius: 6px;
        }}
        .regime-msg {{
            font-size: 0.85rem;
            color: #f3f4f6;
            line-height: 1.55;
        }}

        /* 종목 발굴 기준 설명 카드 */
        .criteria-card {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 18px;
        }}
        .criteria-head {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            font-weight: 700;
            font-size: 0.95rem;
            color: #ffffff;
        }}
        .criteria-sub-tag {{
            font-size: 0.72rem;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}
        .criteria-sub-tag.tag-purple {{
            background: rgba(139, 92, 246, 0.15);
            color: #c084fc;
            border-color: rgba(139, 92, 246, 0.3);
        }}
        .criteria-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
        }}
        .criteria-item {{
            display: flex;
            gap: 10px;
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 10px 12px;
        }}
        .ci-num {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.95rem;
            font-weight: 800;
            color: #f59e0b;
            flex-shrink: 0;
            line-height: 1.2;
            padding-top: 2px;
        }}
        .ci-num.num-purple {{
            color: #a78bfa;
        }}
        .ci-content {{
            display: flex;
            flex-direction: column;
            gap: 3px;
        }}
        .ci-title {{
            font-size: 0.84rem;
            font-weight: 700;
            color: #f9fafb;
        }}
        .ci-desc {{
            font-size: 0.76rem;
            color: #9ca3af;
            line-height: 1.45;
        }}

        /* AI 추천 종목 레이더 */
        .rec-nav {{
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 8px;
            margin-bottom: 14px;
        }}
        .rec-tab {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-sub);
            padding: 12px 18px;
            border-radius: 12px;
            font-size: 0.92rem;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: all 0.2s;
        }}
        .rec-tab:hover {{
            border-color: rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }}
        .rec-tab.active {{
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(37, 99, 235, 0.15));
            border-color: #f59e0b;
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(245, 158, 11, 0.25);
        }}
        .rec-tag-pill {{
            font-size: 0.74rem;
            padding: 3px 8px;
            border-radius: 999px;
            background: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }}
        .pill-purple {{
            background: rgba(139, 92, 246, 0.2);
            color: #c084fc;
            border-color: rgba(139, 92, 246, 0.35);
        }}
        .pill-red {{
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.35);
        }}
        .ci-num.num-red {{
            color: #ef4444;
        }}
        .criteria-sub-tag.tag-red {{
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.3);
        }}
        .rec-strategy-banner {{
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 0.85rem;
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        .banner-orange {{
            background: rgba(245, 158, 11, 0.08);
            border: 1px solid rgba(245, 158, 11, 0.25);
            color: #fde68a;
        }}
        .banner-purple {{
            background: rgba(139, 92, 246, 0.08);
            border: 1px solid rgba(139, 92, 246, 0.25);
            color: #e9d5ff;
        }}
        .banner-red {{
            background: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.25);
            color: #fca5a5;
        }}
        .rec-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .rec-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.25s;
            position: relative;
        }}
        .rec-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
        }}
        .rec-card.theme-closing {{
            border-top: 3px solid #f59e0b;
        }}
        .rec-card.theme-swing {{
            border-top: 3px solid #8b5cf6;
        }}
        .rec-card.theme-breakout {{
            border-top: 3px solid #ef4444;
        }}
        .rec-card-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        .rec-stock-title a {{
            font-size: 1.15rem;
            font-weight: 800;
            color: #ffffff !important;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .rec-stock-title a:hover {{
            text-decoration: underline;
        }}
        .rec-code {{
            font-size: 0.8rem;
            color: #9ca3af;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
        }}
        .rec-market-badge {{
            font-size: 0.7rem;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.08);
            color: #d1d5db;
            margin-left: 4px;
        }}
        .rec-score-badge {{
            font-size: 0.74rem;
            font-weight: 700;
            padding: 3px 9px;
            border-radius: 999px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }}
        .rec-price-row {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .rec-label {{
            font-size: 0.78rem;
            color: var(--text-sub);
            margin-right: 6px;
        }}
        .rec-price {{
            font-size: 1.35rem;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            color: #ffffff;
        }}
        .rec-change-box {{
            font-size: 0.88rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .rec-target-box {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 6px;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 12px;
            text-align: center;
        }}
        .target-col .t-label {{
            font-size: 0.68rem;
            color: #9ca3af;
            margin-bottom: 4px;
        }}
        .target-col .t-val {{
            font-size: 0.88rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .col-t1 .t-val {{ color: #f87171; }}
        .col-t2 .t-val {{ color: #ef4444; }}
        .col-sl .t-val {{ color: #60a5fa; }}
        .rec-desc-box {{
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 8px;
            padding: 10px;
            font-size: 0.8rem;
            line-height: 1.5;
            margin-bottom: 10px;
        }}
        .rec-desc-title {{
            color: #9ca3af;
            font-weight: 600;
            font-size: 0.74rem;
            margin-bottom: 3px;
        }}
        .rec-desc-text {{
            color: #f3f4f6;
            margin-bottom: 6px;
        }}
        .rec-period-tag {{
            font-size: 0.72rem;
            color: #fbbf24;
            font-weight: 600;
        }}
        .rec-tags-row {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .rec-tag {{
            font-size: 0.7rem;
            padding: 2px 7px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.06);
            color: #9ca3af;
        }}

        /* 가이드 탭 & 박스 */
        .tabs {{
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 8px;
            margin-bottom: 14px;
        }}
        .tab-btn {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-sub);
            padding: 10px 16px;
            border-radius: 10px;
            font-size: 0.88rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }}
        .tab-btn.active {{
            background: #2563eb;
            color: #fff;
            border-color: #3b82f6;
            box-shadow: 0 4px 14px rgba(37,99,235,0.4);
        }}
        .guide-content {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 22px;
            line-height: 1.8;
            font-size: 0.95rem;
            white-space: pre-line;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}

        /* 공시 카테고리 탭 네비게이션 */
        .disclosure-nav {{
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 8px;
            margin-bottom: 20px;
        }}
        .disc-tab {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-sub);
            padding: 10px 18px;
            border-radius: 12px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }}
        .disc-tab:hover {{
            border-color: rgba(255,255,255,0.2);
            color: var(--text-main);
        }}
        .disc-tab.active {{
            background: rgba(59, 130, 246, 0.18);
            border-color: #3b82f6;
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.25);
        }}
        .tab-count {{
            display: inline-block;
            font-size: 0.75rem;
            padding: 2px 7px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-sub);
            font-family: 'JetBrains Mono', monospace;
        }}
        .disc-tab.active .tab-count {{
            background: #3b82f6;
            color: #fff;
        }}
        .count-green {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .count-gold {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
        .count-purple {{ background: rgba(139, 92, 246, 0.2); color: #a78bfa; }}

        /* 카테고리 그룹 컨테이너 */
        .category-group {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 24px;
            transition: all 0.3s;
        }}
        .category-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            padding-bottom: 14px;
            margin-bottom: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .cat-title {{
            font-size: 1.1rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .cat-badge {{
            font-size: 0.78rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 999px;
        }}
        .header-green .cat-title {{ color: #34d399; }}
        .header-green .cat-badge {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .header-gold .cat-title {{ color: #fbbf24; }}
        .header-gold .cat-badge {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
        .header-purple .cat-title {{ color: #c084fc; }}
        .header-purple .cat-badge {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}

        /* 공시 카드 스타일 */
        .disclosure-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 14px;
        }}
        .disclosure-card {{
            background: rgba(17, 24, 39, 0.7);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
            position: relative;
        }}
        .disclosure-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }}
        .disclosure-card.type-earnings {{
            border-left: 4px solid #10b981;
        }}
        .disclosure-card.type-buyback {{
            border-left: 4px solid #f59e0b;
        }}
        .disclosure-card.type-ir {{
            border-left: 4px solid #8b5cf6;
        }}
        .disclosure-card.is-watchlist {{
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.06), rgba(17, 24, 39, 0.95));
            border-color: rgba(245, 158, 11, 0.35);
        }}
        .card-top-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .watch-tag {{
            font-size: 0.74rem;
            font-weight: 700;
            color: #fbbf24;
            background: rgba(245, 158, 11, 0.15);
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }}
        .watch-tag.tag-surprise {{
            color: #34d399;
            background: rgba(16, 185, 129, 0.18);
            border-color: rgba(16, 185, 129, 0.4);
        }}
        .watch-tag.tag-turnaround {{
            color: #60a5fa;
            background: rgba(59, 130, 246, 0.18);
            border-color: rgba(59, 130, 246, 0.4);
        }}
        .watch-tag.tag-growth {{
            color: #a78bfa;
            background: rgba(139, 92, 246, 0.18);
            border-color: rgba(139, 92, 246, 0.4);
        }}
        .watch-tag.tag-buyback {{
            color: #fbbf24;
            background: rgba(245, 158, 11, 0.18);
            border-color: rgba(245, 158, 11, 0.4);
        }}
        .badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
        }}
        .badge-green {{ background: rgba(16,185,129,0.2); color: #34d399; }}
        .badge-gold {{ background: rgba(245,158,11,0.2); color: #fbbf24; }}
        .badge-purple {{ background: rgba(139,92,246,0.2); color: #a78bfa; }}
        .card-main-title {{
            font-size: 0.98rem;
            font-weight: 700;
            color: #ffffff !important;
            margin-bottom: 8px;
            line-height: 1.45;
        }}
        .card-main-title a,
        .card-main-title a:link,
        .card-main-title a:visited,
        .card-main-title a:hover,
        .card-main-title a:active,
        .card-main-title b {{
            color: #ffffff !important;
            text-decoration: underline;
            text-decoration-color: rgba(255, 255, 255, 0.4);
            font-weight: 700;
        }}
        .card-main-title a:hover {{
            color: #ffffff !important;
            text-decoration-color: #ffffff;
        }}
        .card-details {{
            font-size: 0.85rem;
            color: #f3f4f6 !important;
            line-height: 1.65;
            background: rgba(0, 0, 0, 0.35);
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .card-details a,
        .card-details a:link,
        .card-details a:visited,
        .card-details a:hover {{
            color: #ffffff !important;
            text-decoration: underline;
        }}
        .card-details b {{
            color: #ffffff !important;
        }}
        .empty-card {{
            padding: 30px;
            text-align: center;
            color: var(--text-sub);
            background: rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            border: 1px dashed rgba(255, 255, 255, 0.08);
            grid-column: 1 / -1;
            font-size: 0.88rem;
        }}

        footer {{
            margin-top: 48px;
            padding: 24px 0;
            text-align: center;
            border-top: 1px solid var(--border);
            color: var(--text-sub);
            font-size: 0.82rem;
        }}
    </style>
</head>
<body>
    <header>
        <div class="logo-area">
            <h1>🧭 비니stock 트레이딩 대시보드</h1>
        </div>
        <div class="time-badge">
            <span class="live-dot"></span>{now_str}
        </div>
    </header>

    <!-- 1. 핵심 지표 그리드 -->
    <div class="grid-indicators">
        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">🇺🇸 E-mini 나스닥100 선물</span>
                {fut_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{fut_display}</div>
            </div>
            <div class="metric-sub">{fut_badge} (CME 실시간)</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{fut_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">💻 필라델피아 반도체</span>
                {sox_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{sox_display}</div>
            </div>
            <div class="metric-sub">{sox_badge}</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{sox_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">🇰🇷 코스피 & 수급</span>
                {kp_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{kp_display}</div>
            </div>
            <div class="metric-sub">{kp_badge} | 외인 {kp_for}억</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{kp_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">🇰🇷 코스닥 & 수급</span>
                {kd_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{kd_display}</div>
            </div>
            <div class="metric-sub">{kd_badge} | 외인 {kd_for}억</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{kd_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">💱 원/달러 환율</span>
                {fx_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{fx_display}</div>
            </div>
            <div class="metric-sub">{fx_badge}</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{fx_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">🧭 CNN 공포/탐욕</span>
                {cnn_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{cnn_score:.0f}점</div>
            </div>
            <div class="metric-sub">{cnn_rating.upper()} (월가 투자심리)</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{cnn_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">🌪️ VIX 변동성 지수</span>
                {vix_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{vix_display}</div>
            </div>
            <div class="metric-sub">{vix_badge} (월가 공포)</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{vix_impact_desc}</div>
            </div>
        </div>

        <div class="metric-card">
            <div class="metric-top-row">
                <span class="metric-label">📈 미국 10년물 국채금리</span>
                {us10y_impact_badge}
            </div>
            <div class="metric-main-row">
                <div class="metric-value">{us10y_display}</div>
            </div>
            <div class="metric-sub">{us10y_badge} (글로벌 긴축)</div>
            <div class="metric-desc">
                <div class="metric-desc-title">💡 시장 영향 & 실전 의미</div>
                <div class="metric-desc-text">{us10y_impact_desc}</div>
            </div>
        </div>
    </div>

    <!-- 2. AI 실전 추천 레이더 (라씨 벤치마킹) -->
    <div class="section-title">
        <span>🎯 AI 실전 추천 레이더 (라씨 벤치마킹)</span>
    </div>
    <div style="font-size: 0.85rem; color: #9ca3af; margin-top: -8px; margin-bottom: 16px;">
        💡 코스피·코스닥 2,800개 전 종목의 수급, 거래대금, 20일선 눌림목을 분석하여 <b>[당일 종가베팅]</b>과 <b>[2~5일 스윙]</b> 최우량주를 엄선합니다.
    </div>

    <!-- 시장 안전도(Market Regime) 레짐 배너 -->
    <div class="rec-market-alert {rec_regime.get('badge_class', 'regime-neutral')}">
        <div class="regime-header">
            <span class="regime-badge">{rec_regime.get('badge', '🔵 시장 환경 분석')}</span>
            <span class="regime-advice">AI 권장 포지션: <b>{rec_regime.get('position_advice', '원칙 분할 매매')}</b></span>
        </div>
        <div class="regime-msg">{rec_regime.get('message', '')}</div>
    </div>

    <!-- 추천 트랙 선택 탭 -->
    <div class="rec-nav">
        <button class="rec-tab active" onclick="switchRecTrack('closing', this)">
            ⚡ 오늘 15:10 종가베팅 <span class="rec-tag-pill">익일 갭상승 +3%~+5%</span>
        </button>
        <button class="rec-tab" onclick="switchRecTrack('swing', this)">
            🌊 2~5일 스윙 추천 <span class="rec-tag-pill pill-purple">추세 파동 +5%~+10%</span>
        </button>
        <button class="rec-tab" onclick="switchRecTrack('breakout', this)">
            🔥 당일 +15% 돌파 대장주 <span class="rec-tag-pill pill-red">기준봉 포착</span>
        </button>
    </div>

    <!-- 1) 종가베팅 컨테이너 -->
    <div id="rec-closing-container" class="rec-container">
        <div class="rec-strategy-banner banner-orange">
            <div>
                <b>🎯 종가베팅 전략 핵심 가이드</b>: 오후 15:10~15:30 매수 → 익일 아침 09:00~09:20 시초가 갭상승 시 전량 분할 익절 (+3%~+5%)
            </div>
        </div>

        <!-- 🔍 15:10 종가베팅 4대 선별 기준 설명 박스 -->
        <div class="criteria-card">
            <div class="criteria-head">
                <span>🔍 AI 15:10 종가베팅 4대 엄격 선별 기준 (당일 승률 극대화)</span>
                <span class="criteria-sub-tag">오버나잇 승률 모델</span>
            </div>
            <div class="criteria-grid">
                <div class="criteria-item">
                    <div class="ci-num">01</div>
                    <div class="ci-content">
                        <div class="ci-title">거래대금 최우선 집중 (수백억~1,000억+)</div>
                        <div class="ci-desc">시장의 메이저 자금이 쏠린 최상위 주도주만 선별 (호가창이 얇아 매도 시 손해보는 소형 거래량 종목 원천 배제)</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num">02</div>
                    <div class="ci-content">
                        <div class="ci-title">마감 양봉 완성도 (윗꼬리 38% 이하)</div>
                        <div class="ci-desc">15:10 장마감까지 차익실현 매물에 밀리지 않고 고가 부근을 단단하게 지켜낸 최상위 매수세 검증</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num">03</div>
                    <div class="ci-content">
                        <div class="ci-title">과열 없는 최적 상승률 (+3.5% ~ +10.0%)</div>
                        <div class="ci-desc">너무 적게 오르면(+3% 미만) 힘이 없고, 너무 많이 폭등하면(+10% 초과) 다음 날 아침 차익 매물(상투)을 맞기 때문에 갭상승 확률이 가장 높은 '딱 좋은 상승 구간'만 선별</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num">04</div>
                    <div class="ci-content">
                        <div class="ci-title">익일 시초가 기계적 익절 (+3%~+5%)</div>
                        <div class="ci-desc">익일 아침 09:00~09:20 시초가 갭상승 파동에서 욕심 없이 전량 분할 매도하는 오버나잇 단기 승부 원칙</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="rec-grid">
            {closing_cards_html}
        </div>
    </div>

    <!-- 2) 2~5일 스윙 컨테이너 -->
    <div id="rec-swing-container" class="rec-container" style="display: none;">
        <div class="rec-strategy-banner banner-purple">
            <div>
                <b>🌊 2~5일 스윙 전략 핵심 가이드</b>: 20일선 우상향 눌림목 지지 종목 매수 → 2~5영업일간 +5%~+10% 추세 파동 누적 익절 (손절 -3%)
            </div>
        </div>

        <!-- 🔍 2~5일 스윙 4대 선별 기준 설명 박스 -->
        <div class="criteria-card">
            <div class="criteria-head">
                <span>🔍 AI 2~5일 스윙 4대 엄격 선별 기준 (추세 파동 승률 모델)</span>
                <span class="criteria-sub-tag tag-purple">안정적 손익비 모델</span>
            </div>
            <div class="criteria-grid">
                <div class="criteria-item">
                    <div class="ci-num num-purple">01</div>
                    <div class="ci-content">
                        <div class="ci-title">20일선 우상향 & 5% 이내 눌림목 지지</div>
                        <div class="ci-desc">중기 추세가 살아있는 종목이 20일선 부근까지 건강하게 조정을 마치고 하방 경직성을 확보한 골든 변곡점 포착</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-purple">02</div>
                    <div class="ci-content">
                        <div class="ci-title">스마트머니 지지 & 거래량 수축</div>
                        <div class="ci-desc">주가가 조정을 받을 때는 매도세가 마르고, 반등할 때 거래대금이 재차 실리는 세력/기관 매집 패턴 확인</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-purple">03</div>
                    <div class="ci-content">
                        <div class="ci-title">시총 4천억 ~ 10조원 알짜 중형주</div>
                        <div class="ci-desc">초대형 지수주(10조 초과)의 무거운 둔화와 소형주(4천억 미만)의 급락 리스크를 모두 피하고, 2~5일 파동 탄력이 가장 뛰어난 알짜 중형 우량주만 선별</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-purple">04</div>
                    <div class="ci-content">
                        <div class="ci-title">정량적 손익비 (목표 +5%~+9%, 손절 -3%)</div>
                        <div class="ci-desc">손실은 -3%로 타이트하게 제한하고, 파동 상승 시 +5%~+9% 분할 익절하여 계좌 수익 곡선을 우상향시키는 전략</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="rec-grid">
            {swing_cards_html}
        </div>
    </div>

    <!-- 3) 당일 +15% 돌파 대장주 컨테이너 -->
    <div id="rec-breakout-container" class="rec-container" style="display: none;">
        <div class="rec-strategy-banner banner-red">
            <div>
                <b>🔥 돌파 대장주 실전 매매 가이드</b>: 당일 종가에 섣불리 추격매수하지 마시고, 향후 2~5영업일간 주가가 5일선/눌림목까지 숨고르기할 때 분할 매수로 공략하는 '기준봉' 관심종목입니다.
            </div>
        </div>

        <!-- 🔍 돌파 대장주 4대 선별 기준 설명 박스 -->
        <div class="criteria-card">
            <div class="criteria-head">
                <span>🔍 AI 당일 +15% 돌파 대장주 4대 엄격 선별 기준 (기준봉 포착 모델)</span>
                <span class="criteria-sub-tag tag-red">시장 주도 대장주 모델</span>
            </div>
            <div class="criteria-grid">
                <div class="criteria-item">
                    <div class="ci-num num-red">01</div>
                    <div class="ci-content">
                        <div class="ci-title">당일 상승률 +14% 이상 장대양봉 돌파</div>
                        <div class="ci-desc">전고점 및 강력한 매물대를 시원하게 뚫어버린 당일 시장 최강 모멘텀 주도주 포착</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-red">02</div>
                    <div class="ci-content">
                        <div class="ci-title">거래대금 200억~500억+ 폭발 (메이저 수급)</div>
                        <div class="ci-desc">시장 자금이 총집결하여 소형 잡주의 가짜 돌파가 아닌 '진짜 메이저 세력/기관 매집' 검증</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-red">03</div>
                    <div class="ci-content">
                        <div class="ci-title">마감 양봉 완성도 (윗꼬리 35% 이하)</div>
                        <div class="ci-desc">장마감까지 차익실현에 무너지지 않고 고가 권역을 견고하게 지켜낸 진짜 대장주만 선별</div>
                    </div>
                </div>
                <div class="criteria-item">
                    <div class="ci-num num-red">04</div>
                    <div class="ci-content">
                        <div class="ci-title">향후 2~5일 눌림목 공략 타겟 (기준봉 활용)</div>
                        <div class="ci-desc">당일 고점 추격매수 절대 금지! 며칠 뒤 5일선·눌림목 반등 시 큰 파동을 안겨줄 핵심 기준봉 후보</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="rec-grid">
            {breakout_cards_html}
        </div>
    </div>

    <!-- 3. 실전 4대 종가베팅/매도 가이드 -->
    <div class="section-title">⏱️ 실전 4대 트레이딩 라이프사이클 가이드</div>
    <div class="tabs">
        <button class="tab-btn" onclick="showGuide('g0740', this)">🌅 07:40 NXT 매도</button>
        <button class="tab-btn" onclick="showGuide('g0840', this)">🌅 08:40 정규장 매도</button>
        <button class="tab-btn" onclick="showGuide('g1510', this)">🎯 15:10 정규장 종가베팅</button>
        <button class="tab-btn active" onclick="showGuide('g1940', this)">🎯 19:40 NXT 최종 종가베팅</button>
    </div>

    <div id="guide-box" class="guide-content"></div>

    <!-- 3. 핵심 공시 레이더 (실적 · 자사주 · IR 카테고리 분리) -->
    <div class="section-title">
        <span>📢 핵심 공시 레이더 (실적 · 자사주 · IR)</span>
    </div>
    <div style="font-size: 0.8rem; color: #9ca3af; margin-top: -8px; margin-bottom: 16px;">
        💡 <b>⭐ 배지</b>는 알고리즘이 '어닝서프라이즈(+10% 초과)', '흑자전환', '대규모 자사주 취득' 등 강력한 상승 모멘텀을 자동 포착한 공시입니다.
    </div>

    <!-- 카테고리 필터 탭 -->
    <div class="disclosure-nav">
        <button class="disc-tab active" onclick="filterDisclosures('all', this)">
            🌐 전체 공시 <span class="tab-count">{total_disc_count}</span>
        </button>
        <button class="disc-tab" onclick="filterDisclosures('earnings', this)">
            📈 실적 발표 <span class="tab-count count-green">{earnings_count}</span>
        </button>
        <button class="disc-tab" onclick="filterDisclosures('buyback', this)">
            💰 자사주 취득 <span class="tab-count count-gold">{buyback_count}</span>
        </button>
        <button class="disc-tab" onclick="filterDisclosures('ir', this)">
            🎤 IR 일정 <span class="tab-count count-purple">{ir_count}</span>
        </button>
    </div>

    <!-- 1) 실적 발표 섹션 -->
    <div id="section-earnings" class="category-group">
        <div class="category-header header-green">
            <div class="cat-title">📈 <span>잠정실적 & 어닝 서프라이즈 레이더</span></div>
            <div class="cat-badge">컨센서스 대비 ±10% 판정 · {earnings_count}건</div>
        </div>
        <div class="disclosure-grid">
            {earnings_html or "<div class='empty-card'>최근 24시간 내 등록된 잠정실적 공시가 없습니다.</div>"}
        </div>
    </div>

    <!-- 2) 자사주 취득 섹션 -->
    <div id="section-buyback" class="category-group">
        <div class="category-header header-gold">
            <div class="cat-title">💰 <span>자사주 취득 결정 레이더</span></div>
            <div class="cat-badge">주주환원 · 취득규모 · {buyback_count}건</div>
        </div>
        <div class="disclosure-grid">
            {buyback_html or "<div class='empty-card'>최근 24시간 내 등록된 자사주 취득 공시가 없습니다.</div>"}
        </div>
    </div>

    <!-- 3) IR 일정 섹션 -->
    <div id="section-ir" class="category-group">
        <div class="category-header header-purple">
            <div class="cat-title">🎤 <span>실적발표 및 기업설명회(IR) 일정 레이더</span></div>
            <div class="cat-badge">개최 일시 · 대상 · 방식 · {ir_count}건</div>
        </div>
        <div class="disclosure-grid">
            {ir_html or "<div class='empty-card'>최근 24시간 내 등록된 IR 일정 공시가 없습니다.</div>"}
        </div>
    </div>

    <footer>
        비니stock 자동화 시스템 • 100% 무료 GitHub Pages 호스팅 • 매일 자동 업데이트
    </footer>

    <script>
        const guides = {{
            g0740: `{g0740_js}`,
            g0840: `{g0840_js}`,
            g1510: `{g1510_js}`,
            g1940: `{g1940_js}`
        }};

        function showGuide(key, btn) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if(btn) btn.classList.add('active');
            const cleanText = guides[key].replace(/<[^>]*>?/gm, '');
            document.getElementById('guide-box').innerText = cleanText;
        }}

        function filterDisclosures(type, btn) {{
            document.querySelectorAll('.disc-tab').forEach(b => b.classList.remove('active'));
            if(btn) btn.classList.add('active');

            const secEarnings = document.getElementById('section-earnings');
            const secBuyback = document.getElementById('section-buyback');
            const secIr = document.getElementById('section-ir');

            if (type === 'all') {{
                secEarnings.style.display = 'block';
                secBuyback.style.display = 'block';
                secIr.style.display = 'block';
            }} else if (type === 'earnings') {{
                secEarnings.style.display = 'block';
                secBuyback.style.display = 'none';
                secIr.style.display = 'none';
            }} else if (type === 'buyback') {{
                secEarnings.style.display = 'none';
                secBuyback.style.display = 'block';
                secIr.style.display = 'none';
            }} else if (type === 'ir') {{
                secEarnings.style.display = 'none';
                secBuyback.style.display = 'none';
                secIr.style.display = 'block';
            }}
        }}

        // 기본 활성 탭
        showGuide('g1940', document.querySelectorAll('.tab-btn')[3]);

        function switchRecTrack(track, btn) {{
            document.querySelectorAll('.rec-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('rec-closing-container').style.display = (track === 'closing') ? 'block' : 'none';
            document.getElementById('rec-swing-container').style.display = (track === 'swing') ? 'block' : 'none';
            document.getElementById('rec-breakout-container').style.display = (track === 'breakout') ? 'block' : 'none';
        }}
    </script>
</body>
</html>
"""
    # 저장 디렉토리 (dist/)
    out_dir = Path(__file__).parent / "dist"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"✓ 웹 대시보드 생성 완료: {out_file} ({out_file.stat().st_size} bytes)")
    return out_file


if __name__ == "__main__":
    generate_html()
