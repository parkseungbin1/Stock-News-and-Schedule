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
    get_market_score_message,
)

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
        watch_tag = '<span class="watch-tag">⭐ 관심종목</span>' if is_watch else ''
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
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 28px;
        }}
        .metric-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .metric-card:hover {{
            border-color: rgba(255,255,255,0.2);
            transform: translateY(-2px);
        }}
        .metric-label {{
            font-size: 0.8rem;
            color: var(--text-sub);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .metric-value {{
            font-size: 1.35rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 4px;
        }}
        .up {{ color: #f87171; }}
        .down {{ color: #60a5fa; }}
        .metric-sub {{
            font-size: 0.78rem;
            color: var(--text-sub);
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
            background: rgba(59, 130, 246, 0.15);
            border-color: #3b82f6;
            color: #60a5fa;
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
            padding: 2px 8px;
            border-radius: 6px;
            border: 1px solid rgba(245, 158, 11, 0.3);
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
            font-size: 0.95rem;
            font-weight: 700;
            color: #fff;
            margin-bottom: 8px;
            line-height: 1.45;
        }}
        .card-main-title a {{
            color: #60a5fa;
            text-decoration: none;
        }}
        .card-main-title a:hover {{
            text-decoration: underline;
        }}
        .card-details {{
            font-size: 0.84rem;
            color: var(--text-sub);
            line-height: 1.65;
            background: rgba(0, 0, 0, 0.25);
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }}
        .card-details b {{
            color: var(--text-main);
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
            <div class="metric-label">🇺🇸 E-mini 나스닥100 선물</div>
            <div class="metric-value">{fut_display}</div>
            <div class="metric-sub">{fut_badge} (CME 실시간)</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">💻 필라델피아 반도체</div>
            <div class="metric-value">{sox_display}</div>
            <div class="metric-sub">{sox_badge}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">🇰🇷 코스피 & 수급</div>
            <div class="metric-value">{kp_display}</div>
            <div class="metric-sub">{kp_badge} | 외인 {kp_for}억</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">🇰🇷 코스닥 & 수급</div>
            <div class="metric-value">{kd_display}</div>
            <div class="metric-sub">{kd_badge} | 외인 {kd_for}억</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">💱 원/달러 환율</div>
            <div class="metric-value">{fx_display}</div>
            <div class="metric-sub">{fx_badge}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">🧭 CNN 공포/탐욕</div>
            <div class="metric-value">{cnn_score:.0f}점</div>
            <div class="metric-sub">{cnn_rating.upper()}</div>
        </div>
    </div>

    <!-- 2. 실전 4대 종가베팅/매도 가이드 -->
    <div class="section-title">⏱️ 실전 4대 트레이딩 라이프사이클 가이드</div>
    <div class="tabs">
        <button class="tab-btn" onclick="showGuide('g0740', this)">🌅 07:40 NXT 매도</button>
        <button class="tab-btn" onclick="showGuide('g0840', this)">🌅 08:40 정규장 매도</button>
        <button class="tab-btn" onclick="showGuide('g1510', this)">🎯 15:10 정규장 종가베팅</button>
        <button class="tab-btn active" onclick="showGuide('g1940', this)">🎯 19:40 NXT 최종 종가베팅</button>
    </div>

    <div id="guide-box" class="guide-content"></div>

    <!-- 3. 관심종목 핵심 공시 레이더 (실적 · 자사주 · IR 카테고리 분리) -->
    <div class="section-title">
        <span>📢 관심종목 핵심 공시 레이더</span>
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
