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

    def document_text(self, rcept_no):
        """공시 원문(XML) 텍스트"""
        r = requests.get(DART_DOC_URL, params={'crtfc_key': self.key, 'rcept_no': rcept_no}, timeout=30)
        try:
            z = zipfile.ZipFile(io.BytesIO(r.content))
        except zipfile.BadZipFile:
            raise RuntimeError(f"원문 조회 실패: {r.text[:200]}")
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


def parse_preliminary_earnings(xml):
    """잠정실적 원문에서 당기 매출액/영업이익/순이익(억원) 추출"""
    unit = 1e-2  # 기본 백만원
    m = re.search(r'단위\s*[:：]?\s*(십억원|백만원|천원|억원|원)', re.sub(r'<[^>]+>', ' ', xml))
    if m:
        unit = UNIT_TO_EOK[m.group(1)]

    result = {}
    keys = {'매출액': 'sales', '영업이익': 'op', '당기순이익': 'net', '법인세비용차감전계속사업이익': None}
    rows = _rows(xml)
    for i, cells in enumerate(rows):
        label = cells[0].replace(' ', '')
        for k, field in keys.items():
            if field and label.startswith(k) and field not in result:
                # '당해실적' 행: 라벨 다음 셀이 '당해실적'이면 그 뒤부터 숫자
                nums = [_num(c) for c in cells[1:]]
                nums = [n for n in nums if n is not None]
                if nums:
                    result[field] = nums[0] * unit
    return result


IR_DATE_RE = re.compile(r'(20\d{2})\s*[.\-년/]\s*(\d{1,2})\s*[.\-월/]\s*(\d{1,2})')


def parse_ir_info(xml):
    """기업설명회 공시에서 개최일자/목적 추출"""
    info = {'date': None, 'purpose': ''}
    for cells in _rows(xml):
        label = cells[0].replace(' ', '')
        val = ' '.join(cells[1:])
        if not info['date'] and ('일자' in label or '일시' in label):
            m = IR_DATE_RE.search(val)
            if m:
                info['date'] = '%s%02d%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
        if not info['purpose'] and '목적' in label:
            info['purpose'] = val[:80]
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


def format_earnings(item, actual, cons, watch):
    line = f"{_star(item, watch)}<b>{_link(item)}</b> 잠정실적\n"
    op = actual.get('op')
    verdict = ''
    if cons and op is not None and cons.get('op'):
        diff = (op - cons['op']) / abs(cons['op']) * 100
        if diff >= SURPRISE_PCT:
            verdict = f"🚀 <b>어닝서프라이즈 {diff:+.0f}%</b>"
        elif diff <= -SURPRISE_PCT:
            verdict = f"🧊 <b>어닝쇼크 {diff:+.0f}%</b>"
        else:
            verdict = f"➖ 컨센 부합 {diff:+.0f}%"
        line += f"   영업이익 {_fmt_eok(op)} (컨센 {_fmt_eok(cons['op'])}, {escape(cons['period'])})\n"
    else:
        line += f"   영업이익 {_fmt_eok(op)} (컨센서스 없음)\n"
    if actual.get('sales') is not None:
        cs = f" (컨센 {_fmt_eok(cons['sales'])})" if cons and cons.get('sales') else ''
        line += f"   매출액 {_fmt_eok(actual['sales'])}{cs}\n"
    if verdict:
        line += f"   {verdict}\n"
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
def collect_new_disclosures(dart, state, watch):
    """신규 공시를 분류·분석해 메시지 블록 반환"""
    now = datetime.now(KST)
    bgn = (now - timedelta(days=1)).strftime('%Y%m%d')
    end = now.strftime('%Y%m%d')
    seen = set(state['seen'])

    items = dart.list(bgn, end, 'I') + dart.list(bgn, end, 'B')
    items.sort(key=lambda x: x['rcept_no'])

    earnings, buyback, ir = [], [], []
    for it in items:
        kind = classify(it['report_nm'])
        if not kind or it['rcept_no'] in seen:
            continue
        state['seen'].append(it['rcept_no'])
        seen.add(it['rcept_no'])
        try:
            if kind == 'earnings':
                if '정정' in it['report_nm']:
                    continue
                actual = parse_preliminary_earnings(dart.document_text(it['rcept_no']))
                cons = naver_consensus(it['stock_code']) if it.get('stock_code') else None
                earnings.append((it, format_earnings(it, actual, cons, watch)))
            elif kind == 'buyback':
                buyback.append((it, format_simple(it, watch, '💰 자사주 취득 결정')))
            elif kind == 'ir':
                info = parse_ir_info(dart.document_text(it['rcept_no']))
                if info['date']:
                    state['ir_dates'][it['rcept_no']] = {
                        'date': info['date'], 'corp': it['corp_name'], 'code': it.get('stock_code', ''),
                        'purpose': info['purpose']}
                d = info['date']
                when = f"{d[4:6]}/{d[6:8]}" if d else '일자 미상'
                ir.append((it, format_simple(it, watch, f"🎤 IR {when} {escape(info['purpose'][:40])}")))
        except Exception as e:
            logger.warning(f"공시 처리 실패 {it['corp_name']} {it['report_nm']}: {e}")
            if kind == 'earnings':
                earnings.append((it, format_simple(it, watch, '잠정실적 (수치 파싱 실패)')))

    def order(lst):  # 관심종목 먼저
        return [b for _, b in sorted(lst, key=lambda x: x[0].get('stock_code') not in watch)]

    sections = []
    if earnings:
        sections.append(('📈 <b>잠정실적 발표</b>', order(earnings)))
    if buyback:
        sections.append(('💰 <b>자사주 취득 결정</b>', order(buyback)))
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
            info = {'date': None, 'purpose': ''}
        state['ir_dates'][it['rcept_no']] = {
            'date': info['date'], 'corp': it['corp_name'], 'code': it.get('stock_code', ''),
            'purpose': info['purpose']}


def today_ir_blocks(state, watch):
    today = datetime.now(KST).strftime('%Y%m%d')
    rows = {}
    for rcept, v in state['ir_dates'].items():
        if v.get('date') == today:
            rows[v['corp']] = (v, rcept)
    blocks = []
    for corp, (v, rcept) in sorted(rows.items(), key=lambda x: x[1][0].get('code') not in watch):
        star = '⭐ ' if v.get('code') in watch else ''
        blocks.append(f"{star}<b><a href=\"{DART_VIEW_URL.format(rcept)}\">{escape(corp)}</a></b> {escape(v.get('purpose', '')[:50])}")
    return blocks
