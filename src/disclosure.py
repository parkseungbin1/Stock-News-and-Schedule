"""
DART 공시 + 네이버 컨센서스 기반 주식 이벤트 알림

- 잠정실적 공시 → 네이버 컨센서스와 비교해 어닝 서프라이즈/쇼크 판정
- 자기주식 취득 결정 공시
- 기업설명회(IR, 실적발표) 개최 공시 + 오늘의 IR 일정 요약
"""
import io
import json
import logging
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
DART_VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
NAVER_QUARTER_URL = "https://m.stock.naver.com/api/stock/{}/finance/quarter"
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}

SURPRISE_PCT = 10.0  # 컨센서스 대비 ±10% 이상이면 서프라이즈/쇼크

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / 'state' / 'disclosure_state.json'
WATCHLIST_FILE = ROOT / 'watchlist.txt'


# ---------------------------------------------------------------- 상태/관심종목
def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'seen': [], 'ir_dates': {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state['seen'] = state['seen'][-3000:]
    cutoff = (datetime.now(KST) - timedelta(days=30)).strftime('%Y%m%d')
    state['ir_dates'] = {k: v for k, v in state['ir_dates'].items() if k[:8] >= cutoff}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')


def load_watchlist():
    """watchlist.txt: 한 줄에 종목코드(6자리) [종목명], '#' 주석 허용"""
    codes = set()
    if WATCHLIST_FILE.exists():
        for line in WATCHLIST_FILE.read_text(encoding='utf-8').splitlines():
            m = re.match(r'\s*(\d{6})', line)
            if m:
                codes.add(m.group(1))
    return codes


# ---------------------------------------------------------------- DART
class Dart:
    def __init__(self, api_key):
        self.key = api_key

    def list(self, bgn_de, end_de, pblntf_ty):
        """기간 내 상장사(유가/코스닥) 공시 목록 전체 페이지 조회"""
        out, page = [], 1
        while True:
            r = requests.get(DART_LIST_URL, params={
                'crtfc_key': self.key, 'bgn_de': bgn_de, 'end_de': end_de,
                'pblntf_ty': pblntf_ty, 'page_no': page, 'page_count': 100,
            }, timeout=20)
            j = r.json()
            if j.get('status') == '013':  # 조회 데이터 없음
                break
            if j.get('status') != '000':
                raise RuntimeError(f"DART 오류 {j.get('status')}: {j.get('message')}")
            out += [x for x in j.get('list', []) if x.get('corp_cls') in ('Y', 'K')]
            if page >= int(j.get('total_page', 1)):
                break
            page += 1
        return out

    def document_text(self, rcept_no, max_retries=3):
        """공시 원문(XML) 텍스트 - DART 문서 생성 지연 시 재시도 포함"""
        for attempt in range(1, max_retries + 1):
            r = requests.get(DART_DOC_URL, params={'crtfc_key': self.key, 'rcept_no': rcept_no}, timeout=30)
            try:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                texts = []
                for name in z.namelist():
                    raw = z.read(name)
                    for enc in ('utf-8', 'euc-kr', 'cp949'):
                        try:
                            texts.append(raw.decode(enc))
                            break
                        except UnicodeDecodeError:
                            continue
                return '\n'.join(texts)
            except zipfile.BadZipFile:
                if '<status>014</status>' in r.text:
                    raise RuntimeError("원문 없음(014: 조회된 데이터가 없음)")
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise RuntimeError(f"원문 조회 실패: {r.text[:200]}")


def _rows(xml):
    """XML 표를 [[셀 텍스트...], ...] 행 리스트로 변환"""
    rows = []
    for tr in re.findall(r'<TR[^>]*>(.*?)</TR>', xml, flags=re.S | re.I):
        cells = re.findall(r'<(?:TD|TH|TE|TU)[^>]*>(.*?)</(?:TD|TH|TE|TU)>', tr, flags=re.S | re.I)
        cells = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip() for c in cells]
        if cells:
            rows.append(cells)
    return rows


def _num(s):
    s = s.replace(',', '').replace(' ', '')
    neg = s.startswith('(') and s.endswith(')') or s.startswith('-') or s.startswith('△')
    s = s.strip('()-△')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


UNIT_TO_EOK = {'원': 1e-8, '천원': 1e-5, '백만원': 1e-2, '십억원': 10, '억원': 1}


def parse_metrics_row(cells, unit):
    """표 행에서 당해 수치(억원), QoQ(%), YoY(%), 흑자/적자전환 여부 추출"""
    row_text = ' '.join(cells)
    val = None
    qoq_pct = None
    yoy_pct = None
    turnaround = None

    for kw in ('흑자전환', '적자전환', '적자지속'):
        if kw in row_text:
            turnaround = kw
            break

    nums = []
    for c in cells[1:]:
        n = _num(c)
        if n is not None:
            nums.append(n)

    if nums:
        val = nums[0] * unit

    if len(cells) >= 8:
        q = _num(cells[4])
        if q is not None:
            qoq_pct = q
        y = _num(cells[7])
        if y is not None:
            yoy_pct = y

    return {'val': val, 'qoq': qoq_pct, 'yoy': yoy_pct, 'turnaround': turnaround}


def parse_preliminary_earnings(xml):
    """잠정실적 원문에서 매출액/영업이익/순이익 및 YoY, QoQ, 흑자전환 등 입체적 수치 추출"""
    unit = 1e-2  # 기본 백만원
    m = re.search(r'단위\s*[:：]?\s*(십억원|백만원|천원|억원|원)', re.sub(r'<[^>]+>', ' ', xml))
    if m:
        unit = UNIT_TO_EOK[m.group(1)]

    result = {}
    rows = _rows(xml)
    for cells in rows:
        label = cells[0].replace(' ', '')
        if label.startswith('영업이익') and 'op' not in result:
            result['op'] = parse_metrics_row(cells, unit)
        elif label.startswith('매출액') and 'sales' not in result:
            result['sales'] = parse_metrics_row(cells, unit)
        elif label.startswith('당기순이익') and 'net' not in result:
            result['net'] = parse_metrics_row(cells, unit)

    return result


def parse_buyback_info(xml):
    """자기주식취득결정 또는 신탁계약 공시에서 금액, 주식수, 기간, 목적, 방법 상세 추출"""
    info = {
        'amount': None,
        'shares': None,
        'start': None,
        'end': None,
        'purpose': '',
        'method': '',
    }
    date_re = re.compile(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일')
    rows = _rows(xml)
    for cells in rows:
        label = cells[0].replace(' ', '')
        val = ' '.join(cells[1:])
        if ('취득예정금액' in label or '계약금액' in label) and info['amount'] is None:
            for c in cells[1:]:
                n = _num(c)
                if n and n > 0:
                    info['amount'] = n
                    break
        elif ('취득예정주식' in label) and info['shares'] is None:
            for c in cells[1:]:
                n = _num(c)
                if n and n > 0:
                    info['shares'] = n
                    break
        elif ('취득예상기간' in label or '계약기간' in label):
            dates = date_re.findall(val)
            if len(dates) >= 2:
                info['start'] = f"{dates[0][0]}.{int(dates[0][1]):02d}.{int(dates[0][2]):02d}"
                info['end'] = f"{dates[1][0]}.{int(dates[1][1]):02d}.{int(dates[1][2]):02d}"
            elif len(dates) == 1 and not info['start']:
                info['start'] = f"{dates[0][0]}.{int(dates[0][1]):02d}.{int(dates[0][2]):02d}"
        elif label in ('종료일', '취득종료예상일자') and not info['end']:
            m2 = date_re.search(val)
            if m2:
                info['end'] = f"{m2.group(1)}.{int(m2.group(2)):02d}.{int(m2.group(3)):02d}"
        elif '목적' in label and not info['purpose']:
            info['purpose'] = val.strip()[:60]
        elif ('방법' in label or '계약체결기관' in label or '수탁기관' in label) and not info['method']:
            info['method'] = val.strip()[:40]

    return info


def parse_cancellation_info(xml):
    """주식소각결정 또는 자기주식소각결정 공시에서 금액, 주식수, 소각예정일, 목적, 방법 상세 추출"""
    info = {
        'amount': None,
        'shares': None,
        'date': None,
        'purpose': '',
        'method': '',
    }
    date_re = re.compile(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일')
    for cells in _rows(xml):
        label = cells[0].replace(' ', '')
        val = ' '.join(cells[1:])
        if ('소각예정금액' in label or '소각대상' in label or '취득가액' in label or '예정금액' in label) and info['amount'] is None:
            for c in cells[1:]:
                n = _num(c)
                if n and n > 0:
                    info['amount'] = n
                    break
        elif ('소각할주식' in label or '보통주식' in label or '소각주식수' in label or '주식수' in label) and info['shares'] is None:
            for c in cells[1:]:
                n = _num(c)
                if n and n > 0:
                    info['shares'] = n
                    break
        elif ('소각예정일' in label or '소각일' in label) and not info['date']:
            m = date_re.search(val)
            if m:
                info['date'] = f"{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"
            else:
                m2 = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', val)
                if m2:
                    info['date'] = f"{m2.group(1)}.{int(m2.group(2)):02d}.{int(m2.group(3)):02d}"
        elif '목적' in label and not info['purpose']:
            info['purpose'] = val.strip()[:60]
        elif '방법' in label and not info['method']:
            info['method'] = val.strip()[:40]

    return info


def parse_ir_info(xml):
    """기업설명회 공시에서 개최일자, 시간, 방식, 대상, 목적 추출"""
    info = {'date': None, 'time': '', 'purpose': '', 'method': '', 'target': ''}
    date_re = re.compile(r'(20\d{2})\s*[.\-년/]\s*(\d{1,2})\s*[.\-월/]\s*(\d{1,2})')
    time_re = re.compile(r'(\d{1,2})\s*[:시]\s*(\d{2})?')

    for cells in _rows(xml):
        label = cells[0].replace(' ', '')
        val = ' '.join(cells[1:])
        if not info['date'] and any(k in label for k in ('일시', '일자')):
            m = date_re.search(val)
            if m:
                info['date'] = '%s%02d%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
            tm = time_re.search(val)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2)) if tm.group(2) else 0
                info['time'] = f"{hour:02d}:{minute:02d}"
        if not info['purpose'] and any(k in label for k in ('주요내용', '목적', '설명회내용')):
            info['purpose'] = val[:60]
        if not info['method'] and any(k in label for k in ('진행방식', '방식', '개최방법')):
            m_txt = val[:30]
            if '컨퍼런스' in m_txt or 'Conference' in m_txt:
                info['method'] = '컨퍼런스 콜'
            elif '온라인' in m_txt:
                info['method'] = '온라인 생중계'
            elif '대면' in m_txt:
                info['method'] = '대면 미팅'
            else:
                info['method'] = m_txt.strip()
        if not info['target'] and any(k in label for k in ('참석대상', '대상자', '대상')):
            t_txt = val[:30]
            if '기관' in t_txt or '애널리스트' in t_txt:
                info['target'] = '기관투자자/애널리스트'
            elif '주주' in t_txt:
                info['target'] = '일반주주'
            else:
                info['target'] = t_txt.strip()

    return info


# ---------------------------------------------------------------- 네이버 컨센서스
def naver_consensus(stock_code):
    """네이버 분기 재무에서 컨센서스(추정) 분기 값(억원) 조회"""
    try:
        j = requests.get(NAVER_QUARTER_URL.format(stock_code), headers=UA, timeout=15).json()
        info = j['financeInfo']
        cons = [t for t in info['trTitleList'] if t.get('isConsensus') == 'Y']
        if not cons:
            return None
        key = cons[0]['key']
        out = {'period': cons[0]['title']}
        for row in info['rowList']:
            field = {'매출액': 'sales', '영업이익': 'op', '당기순이익': 'net'}.get(row['title'])
            if field:
                v = _num((row['columns'].get(key) or {}).get('value') or '')
                if v is not None:
                    out[field] = v
        return out
    except Exception as e:
        logger.warning(f"네이버 컨센서스 조회 실패({stock_code}): {e}")
        return None


# ---------------------------------------------------------------- 분류/포맷
def classify(report_nm):
    n = report_nm.replace(' ', '')
    if '주식소각결정' in n or '자기주식소각결정' in n:
        return 'cancellation'
    if '잠정)실적' in n or '잠정실적' in n:
        return 'earnings'
    if '자기주식취득결정' in n or '자기주식취득신탁계약체결결정' in n:
        return 'buyback'
    if '기업설명회' in n:
        return 'ir'
    return None


def _fmt_eok(v):
    return f"{v:,.0f}억" if v is not None else '-'


def _star(item, watch):
    return '⭐ ' if item.get('stock_code') in watch else ''


def _link(item):
    name = escape(item['corp_name'])
    return f"<a href=\"{DART_VIEW_URL.format(item['rcept_no'])}\">{name}</a>"


WEEKDAYS_KOR = ['월', '화', '수', '목', '금', '토', '일']


def format_earnings(item, actual, cons, watch):
    op_info = actual.get('op', {})
    sales_info = actual.get('sales', {})
    net_info = actual.get('net', {})

    op = op_info.get('val')
    sales = sales_info.get('val')
    net = net_info.get('val')

    verdict = ''
    is_star = item.get('stock_code') in watch
    if cons and op is not None and cons.get('op'):
        diff = (op - cons['op']) / abs(cons['op']) * 100
        if diff >= SURPRISE_PCT:
            verdict = f"🚀 <b>어닝서프라이즈 {diff:+.0f}%</b>"
            is_star = True  # 알고리즘 자동 선별: 컨센서스 +10% 초과 달성
        elif diff <= -SURPRISE_PCT:
            verdict = f"🧊 <b>어닝쇼크 {diff:+.0f}%</b>"
        else:
            verdict = f"➖ 컨센 부합 {diff:+.0f}%"
        detail_head = f"   영업이익 {_fmt_eok(op)} (컨센 {_fmt_eok(cons['op'])}, {escape(cons['period'])})\n"
    else:
        detail_head = f"   영업이익 {_fmt_eok(op)} (컨센서스 없음)\n"

    turnaround = op_info.get('turnaround') or net_info.get('turnaround')
    if turnaround and '흑자전환' in str(turnaround):
        is_star = True  # 알고리즘 자동 선별: 흑자전환 턴어라운드

    yoy = op_info.get('yoy')
    if yoy is not None and yoy >= 100.0 and op is not None and op > 0:
        is_star = True  # 알고리즘 자동 선별: 영업이익 전년대비 +100% 이상 폭증

    star_prefix = '⭐ ' if is_star else ''
    line = f"{star_prefix}<b>{_link(item)}</b> 잠정실적\n{detail_head}"

    # 영업이익 입체 분석 태그 (서프라이즈 여부, YoY 증감률, QoQ 증감률, 흑자/적자전환)
    tags = []
    if verdict:
        tags.append(verdict)
    if op_info.get('turnaround'):
        tags.append(f"🔄 <b>{op_info['turnaround']}</b>")
    if op_info.get('yoy') is not None:
        tags.append(f"YoY {op_info['yoy']:+.1f}%")
    if op_info.get('qoq') is not None and not op_info.get('turnaround'):
        tags.append(f"QoQ {op_info['qoq']:+.1f}%")
    if tags:
        line += f"   {' | '.join(tags)}\n"

    # 매출액
    if sales is not None:
        cs = f" (컨센 {_fmt_eok(cons['sales'])})" if cons and cons.get('sales') else ''
        sales_growth = f" [YoY {sales_info['yoy']:+.1f}%]" if sales_info.get('yoy') is not None else ''
        line += f"   매출액 {_fmt_eok(sales)}{cs}{sales_growth}\n"

    # 당기순이익
    if net is not None:
        net_turn = f" ({net_info['turnaround']})" if net_info.get('turnaround') else (
            f" [YoY {net_info['yoy']:+.1f}%]" if net_info.get('yoy') is not None else "")
        line += f"   당기순이익 {_fmt_eok(net)}{net_turn}\n"

    return line


def format_cancellation(item, info, watch):
    """주식 소각 결정 공시를 입체적으로 포맷 (최고 등급 주주환원 초특급 호재)"""
    amt_eok = (info.get('amount') or 0) / 1e8
    amount_str = ""
    if info.get('amount'):
        if amt_eok >= 10000:
            amount_str = f"{amt_eok / 10000:.1f}조원"
        else:
            amount_str = f"{amt_eok:,.0f}억원"

    shares_str = ""
    if info.get('shares'):
        sh = info['shares']
        if sh >= 10000:
            shares_str = f"{sh / 10000:,.1f}만주"
        else:
            shares_str = f"{sh:,.0f}주"

    line = f"🔥 <b>{_link(item)}</b> 🔥 <b>[초특급 주주환원: 주식 소각 결정]</b>\n"
    if amount_str or shares_str:
        sh_part = f" (보통주 {shares_str})" if shares_str else ""
        line += f"   • 소각규모: <b>{amount_str or '-'}</b>{sh_part}\n"

    extra_tags = []
    if info.get('date'):
        extra_tags.append(f"소각예정일: {info['date']}")
    if info.get('method'):
        extra_tags.append(f"방법: {info['method']}")
    if extra_tags:
        line += f"   • {' | '.join(extra_tags)}\n"
    if info.get('purpose'):
        line += f"   • 목적: {info['purpose']}\n"

    return line


def format_buyback(item, info, watch):
    """자사주 취득 공시를 금액, 주식수, 목적, 기간까지 입체적으로 포맷 (100억 이상 또는 소각 목적 엄선)"""
    amt_eok = (info.get('amount') or 0) / 1e8
    is_star = item.get('stock_code') in watch
    has_burn = '소각' in str(info.get('purpose', ''))
    # 100억원 이상 대규모 자사주 취득 또는 주주가치 제고/소각 목적이면 알고리즘 자동 선별
    if amt_eok >= 100 or has_burn:
        is_star = True

    burn_badge = " 🔥 <b>(소각목적)</b>" if has_burn else ""
    star_prefix = '⭐ ' if is_star else ''
    title_label = "대규모 자사주 취득 결정" if amt_eok >= 100 else "자사주 취득 결정"
    line = f"{star_prefix}<b>{_link(item)}</b> 💰 <b>{title_label}</b>{burn_badge}\n"
    amount_str = ""
    if info.get('amount'):
        if amt_eok >= 10000:
            amount_str = f"{amt_eok / 10000:.1f}조원"
        else:
            amount_str = f"{amt_eok:,.0f}억원"

    shares_str = ""
    if info.get('shares'):
        sh = info['shares']
        if sh >= 10000:
            shares_str = f"{sh / 10000:,.1f}만주"
        else:
            shares_str = f"{sh:,.0f}주"

    if amount_str or shares_str:
        sh_part = f" (보통주 {shares_str})" if shares_str else ""
        line += f"   • 취득예정: <b>{amount_str or '-'}</b>{sh_part}\n"

    extra_tags = []
    if info.get('method'):
        m_short = info['method']
        if '장내' in m_short:
            m_short = '장내매수'
        elif '신탁' in m_short:
            m_short = '신탁계약'
        extra_tags.append(f"방식: {m_short}")
    if info.get('purpose'):
        extra_tags.append(f"목적: {info['purpose']}")
    if extra_tags:
        line += f"   • {' | '.join(extra_tags)}\n"

    if info.get('start') and info.get('end'):
        line += f"   • 기간: {info['start']} ~ {info['end']}\n"
    elif info.get('start'):
        line += f"   • 시작일: {info['start']}\n"

    return line


def format_ir(item, info, watch):
    """IR 공시를 개최 일시(요일 포함), 진행 방식, 대상까지 입체적으로 포맷"""
    d = info.get('date')
    when = '일자 미상'
    if d and len(d) == 8:
        try:
            dt = datetime.strptime(d, '%Y%m%d').date()
            w = WEEKDAYS_KOR[dt.weekday()]
            when = f"{d[4:6]}/{d[6:8]}({w})"
        except Exception:
            when = f"{d[4:6]}/{d[6:8]}"
    if info.get('time'):
        when += f" {info['time']}"

    line = f"{_star(item, watch)}<b>{_link(item)}</b> 🎤 IR <b>{when}</b>\n"
    details = []
    if info.get('method'):
        details.append(f"방식: {info['method']}")
    if info.get('target'):
        details.append(f"대상: {info['target']}")
    if details:
        line += f"   • {' | '.join(details)}\n"
    if info.get('purpose'):
        line += f"   • 내용: {escape(info['purpose'])}\n"
    return line


def format_simple(item, watch, extra=''):
    return f"{_star(item, watch)}<b>{_link(item)}</b> {extra}\n"


def split_messages(header, blocks, limit=3800):
    msgs, cur = [], header
    for b in blocks:
        if len(cur) + len(b) + 1 > limit:
            msgs.append(cur.rstrip())
            cur = header + '(계속)\n\n'
        cur += b + '\n'
    if blocks:
        msgs.append(cur.rstrip())
    return msgs


# ---------------------------------------------------------------- 메인 로직
def collect_new_disclosures(dart, state, watch, max_items=None):
    """신규 공시를 분류·분석해 메시지 블록 반환 (max_items 지원으로 웹 대시보드 초고속 빌드)"""
    now = datetime.now(KST)
    bgn = (now - timedelta(days=1)).strftime('%Y%m%d')
    end = now.strftime('%Y%m%d')
    seen = set(state['seen'])

    items = dart.list(bgn, end, 'I') + dart.list(bgn, end, 'B')
    # 최신 접수 번호 순(내림차순) 정렬
    items.sort(key=lambda x: x['rcept_no'], reverse=True)

    candidates = []
    for it in items:
        kind = classify(it['report_nm'])
        if kind and it['rcept_no'] not in seen:
            candidates.append((it, kind))
            if max_items and len(candidates) >= max_items:
                break

    earnings, buyback, cancellation, ir = [], [], [], []
    for it, kind in candidates:

        try:
            xml_text = dart.document_text(it['rcept_no'])
        except Exception as e:
            logger.warning(f"원문 조회 실패 {it['corp_name']} {it['report_nm']}: {e}")
            # DART 서버에 아직 파일 준비가 안 된 014인 경우 다음 번에 재수집하도록 seen에 넣지 않음
            continue

        state['seen'].append(it['rcept_no'])
        seen.add(it['rcept_no'])

        try:
            if kind == 'cancellation':
                info = parse_cancellation_info(xml_text)
                cancellation.append((it, format_cancellation(it, info, watch)))
            elif kind == 'earnings':
                if '정정' in it['report_nm']:
                    continue
                actual = parse_preliminary_earnings(xml_text)
                cons = naver_consensus(it['stock_code']) if it.get('stock_code') else None
                earnings.append((it, format_earnings(it, actual, cons, watch)))
            elif kind == 'buyback':
                info = parse_buyback_info(xml_text)
                amt_eok = (info.get('amount') or 0) / 1e8
                has_burn = '소각' in str(info.get('purpose', '')) or '소각' in it['report_nm']
                is_watch = it.get('stock_code') in watch

                # [100억 이상 컷오프 필터링]: 100억 미만 소액은 노이즈로 보고 제외
                # 단, '소각' 목적이 포함되어 있거나 사용자의 관심종목(watchlist)인 경우 예외로 전송
                if amt_eok < 100 and not has_burn and not is_watch:
                    logger.info(f"자사주 취득 100억 미만 필터링 제외: {it['corp_name']} ({amt_eok:.0f}억원)")
                    continue

                buyback.append((it, format_buyback(it, info, watch)))
            elif kind == 'ir':
                info = parse_ir_info(xml_text)
                if info['date']:
                    state['ir_dates'][it['rcept_no']] = {
                        'date': info['date'],
                        'time': info.get('time', ''),
                        'corp': it['corp_name'],
                        'code': it.get('stock_code', ''),
                        'purpose': info.get('purpose', ''),
                        'method': info.get('method', ''),
                        'target': info.get('target', ''),
                    }
                ir.append((it, format_ir(it, info, watch)))
        except Exception as e:
            logger.warning(f"공시 파싱 실패 {it['corp_name']} {it['report_nm']}: {e}")
            if kind == 'cancellation':
                cancellation.append((it, format_simple(it, watch, '🔥 주식 소각 결정 공시 [상세보기 🔗]')))
            elif kind == 'earnings':
                earnings.append((it, format_simple(it, watch, '잠정실적 공시 [상세보기 🔗]')))
            elif kind == 'buyback':
                buyback.append((it, format_simple(it, watch, '💰 자사주 취득 결정 공시')))
            elif kind == 'ir':
                ir.append((it, format_simple(it, watch, '🎤 기업설명회(IR) 개최 공시')))

    def order(lst):  # 핵심 포착 공시(⭐ 또는 🔥) 먼저
        return [b for _, b in sorted(lst, key=lambda x: ('🔥' not in x[1] and '⭐' not in x[1]))]

    sections = []
    if cancellation:
        sections.append(('🔥 <b>주식 소각(초특급 주주환원) 공시</b>', order(cancellation)))
    if earnings:
        sections.append(('📈 <b>잠정실적 발표</b>', order(earnings)))
    if buyback:
        sections.append(('💰 <b>대규모 자사주 취득 결정 (100억+ 또는 소각)</b>', order(buyback)))
    if ir:
        sections.append(('🎤 <b>실적발표(IR) 일정 공시</b>', order(ir)))
    return sections


def backfill_ir(dart, state, days=14):
    """최근 N일 IR 공시의 개최일자를 캐시에 채움 (오늘 IR 일정 요약용)"""
    now = datetime.now(KST)
    try:
        items = dart.list((now - timedelta(days=days)).strftime('%Y%m%d'), now.strftime('%Y%m%d'), 'I')
    except Exception as e:
        logger.warning(f"IR 백필 실패: {e}")
        return
    for it in items:
        if classify(it['report_nm']) != 'ir' or it['rcept_no'] in state['ir_dates']:
            continue
        try:
            info = parse_ir_info(dart.document_text(it['rcept_no']))
        except Exception:
            info = {'date': None, 'purpose': '', 'time': '', 'method': '', 'target': ''}
        state['ir_dates'][it['rcept_no']] = {
            'date': info['date'],
            'time': info.get('time', ''),
            'corp': it['corp_name'],
            'code': it.get('stock_code', ''),
            'purpose': info.get('purpose', ''),
            'method': info.get('method', ''),
            'target': info.get('target', ''),
        }


def today_ir_blocks(state, watch):
    today = datetime.now(KST).strftime('%Y%m%d')
    rows = {}
    for rcept, v in state['ir_dates'].items():
        if v.get('date') == today:
            rows[v['corp']] = (v, rcept)
    blocks = []
    for corp, (v, rcept) in sorted(rows.items(), key=lambda x: x[1][0].get('code') not in watch):
        star = '⭐ ' if v.get('code') in watch else ''
        time_part = f" {v['time']}" if v.get('time') else ""
        method_part = f" ({v['method']})" if v.get('method') else ""
        purpose = f" - {v.get('purpose', '')}" if v.get('purpose') else ""
        blocks.append(f"{star}<b><a href=\"{DART_VIEW_URL.format(rcept)}\">{escape(corp)}</a></b>{time_part}{method_part}{escape(purpose[:50])}")
    return blocks
