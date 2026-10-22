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

    # 3. 최근 공시 수집
    disclosures_html = ""
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
                    badge_class = "badge-blue"
                    if "실적" in title:
                        badge_class = "badge-green"
                    elif "자사주" in title:
                        badge_class = "badge-gold"
                    elif "IR" in title:
                        badge_class = "badge-purple"

                    for block in blocks[:6]:
                        clean_block = block.replace('\n', '<br>')
                        disclosures_html += f"""
                        <div class="disclosure-card">
                            <div class="card-header">
                                <span class="badge {badge_class}">{title}</span>
                            </div>
                            <div class="card-body">{clean_block}</div>
                        </div>
                        """
            else:
                disclosures_html = "<div class='empty-card'>최근 등록된 관심종목 핵심 공시가 없습니다.</div>"
        else:
            disclosures_html = "<div class='empty-card'>DART_API_KEY가 설정되지 않았습니다.</div>"
    except Exception as e:
        disclosures_html = f"<div class='empty-card'>공시 데이터를 조회하는 중입니다 ({e})</div>"

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

        /* 공시 카드 그리드 */
        .disclosure-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 14px;
        }}
        .disclosure-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .corp-name {{
            font-weight: 700;
            font-size: 1.05rem;
            color: #fff;
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
        .badge-blue {{ background: rgba(59,130,246,0.2); color: #60a5fa; }}
        .card-title a {{
            color: var(--text-main);
            text-decoration: none;
            font-size: 0.92rem;
            font-weight: 600;
        }}
        .card-title a:hover {{ text-decoration: underline; color: #60a5fa; }}
        .card-body {{
            font-size: 0.85rem;
            color: var(--text-sub);
            margin-top: 8px;
            line-height: 1.6;
        }}
        .empty-card {{
            padding: 30px;
            text-align: center;
            color: var(--text-sub);
            background: var(--surface);
            border-radius: 14px;
            grid-column: 1 / -1;
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

    <!-- 3. 관심종목 핵심 공시 -->
    <div class="section-title">📢 관심종목 핵심 공시 레이더 (실적 · 자사주 · IR)</div>
    <div class="disclosure-grid">
        {disclosures_html}
    </div>

    <footer>
        비니stock 자동화 시스템 • 100% 무료 GitHub Pages 호스팅 • 매일 자동 업데이트
    </footer>

    <script>
        const guides = {{
            g0740: `{guide_0740.replace('`', '\\`')}`,
            g0840: `{guide_0840.replace('`', '\\`')}`,
            g1510: `{guide_1510.replace('`', '\\`')}`,
            g1940: `{guide_1940.replace('`', '\\`')}`
        }};

        function showGuide(key, btn) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if(btn) btn.classList.add('active');
            const cleanText = guides[key].replace(/<[^>]*>?/gm, '');
            document.getElementById('guide-box').innerText = cleanText;
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
