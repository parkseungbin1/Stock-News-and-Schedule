"""
Investing.com 글로벌 경제 캘린더 크롤러
시장 영향력이 매우 높음인 항목만 수집

수집 순서:
1. Investing.com (curl_cffi 브라우저 위장으로 Cloudflare 우회)
2. 실패 시 네이버 증권(한국/미국) + ForexFactory(미국 High) 병합
"""
import time
import requests
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _week_range():
    today = datetime.now(KST).date()
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)

class EconomicCalendarCrawler:
    """Investing.com 경제 캘린더 크롤러 클래스"""
    
    BASE_URL = "https://kr.investing.com/economic-calendar/Service/getCalendarFilteredData"
    # Investing.com 국가 식별 (한국, 미국)
    TARGET_COUNTRIES = ['South Korea', 'United States']
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    def __init__(self):
        self.session = None
        try:
            # curl_cffi: 실제 크롬 TLS 지문을 흉내내 Cloudflare 403 차단을 우회
            from curl_cffi import requests as curl_requests
            self.session = curl_requests.Session(impersonate="chrome")
        except ImportError:
            logger.warning("curl_cffi가 설치되지 않았습니다. Investing.com은 건너뜁니다.")
        # BeautifulSoup 사용을 위해 선언 (설치된 패키지 확인 완료)
        try:
            from bs4 import BeautifulSoup
            self.BeautifulSoup = BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 패키지가 설치되지 않았습니다. 파싱에 실패할 수 있습니다.")
            self.BeautifulSoup = None

    def get_economic_calendar_data(self, nation_types=None):
        """
        이번 주(월~일) 글로벌 경제 캘린더 데이터 수집
        1. Investing.com 시도
        2. 차단/부족 시 ForexFactory + 한국 거시지표(TradingEconomics/네이버) 자동 병합
        """
        events = self._fetch_investing()
        if len(events) >= 3:
            logger.info(f"Investing.com 수집 성공: {len(events)}건")
            return events

        logger.info("ForexFactory 및 한국 거시경제 지표로 수집/보강합니다.")
        fallback = self._fetch_forexfactory()
        fallback = self._merge(fallback, self._fetch_korea_indicators())
        fallback = self._merge(fallback, self._fetch_naver())
        events = self._merge(events, fallback)
        return events

    # ---------------- Investing.com ----------------
    def _fetch_investing(self, retries=3):
        if not self.BeautifulSoup or self.session is None:
            return []

        start_of_week, end_of_week = _week_range()
        # 배열 파라미터는 반드시 (key, value) 튜플로 반복 인코딩해야 함
        data = urlencode([
            ('timeZone', '88'),  # Seoul (GMT+9)
            ('timeFilter', 'timeOnly'),
            ('currentTab', 'custom'),
            ('limit_from', '0'),
            ('dateFrom', start_of_week.strftime('%Y-%m-%d')),
            ('dateTo', end_of_week.strftime('%Y-%m-%d')),
            ('country[]', '5'),   # USA
            ('country[]', '11'),  # South Korea
            ('importance[]', '3'),
        ])

        for attempt in range(1, retries + 1):
            try:
                self.session.get('https://kr.investing.com/economic-calendar/', timeout=20)
                response = self.session.post(self.BASE_URL, data=data, headers={
                    **self.HEADERS,
                    'Referer': 'https://kr.investing.com/economic-calendar/',
                }, timeout=20)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}")
                return self._parse_html(response.json().get('data', ''))
            except Exception as e:
                logger.warning(f"Investing.com 접근 실패({attempt}/{retries}): {e}")
                if attempt < retries:
                    time.sleep(5 * attempt)
        return []

    # ---------------- 네이버 증권 ----------------
    NAVER_URL = "https://stock.naver.com/api/securityService/economic/indicator/nations/upcoming"

    def _fetch_naver(self):
        """네이버 증권 경제지표 (오늘 이후 예정 지표, 중요도 4 이상)"""
        try:
            r = requests.get(self.NAVER_URL, params=[
                ('nationTypeList', 'KOR'), ('nationTypeList', 'USA'), ('gteImportance', '4'),
            ], headers={'User-Agent': self.HEADERS['User-Agent']}, timeout=15)
            r.raise_for_status()
            items = r.json()
        except Exception as e:
            logger.error(f"네이버 경제지표 API 오류: {e}")
            return []

        def fmt(v):
            if v in (None, '', 0, 0.0):
                return '-'
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        events = []
        for it in items if isinstance(items, list) else []:
            try:
                d = datetime.strptime(str(it.get('releaseDate')), '%Y%m%d').date()
                t = datetime.strptime(str(it.get('releaseTime', '')).zfill(6), '%H%M%S').time()
            except ValueError:
                continue
            actual = fmt(it.get('actualValue')) if it.get('isRelease') else '-'
            events.append(self._event(d, t, it.get('nationKoreanName', ''), it.get('name', ''),
                                      fmt(it.get('previousValue')), actual, fmt(it.get('forecastValue'))))
        return events

    # ---------------- ForexFactory & 한국 경제지표 ----------------
    FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    FOREXFACTORY_TITLE_MAP = {
        'Unemployment Claims': '신규 실업수당청구건수',
        'Flash Manufacturing PMI': '제조업 구매관리자지수 (PMI 속보치)',
        'Flash Services PMI': '서비스업 구매관리자지수 (PMI 속보치)',
        'Revised UoM Consumer Sentiment': '미시간대 소비자심리지수',
        'Revised UoM Inflation Expectations': '미시간대 기대인플레이션',
        'Crude Oil Inventories': 'EIA 원유재고',
        'Building Permits': '건축승인건수',
        'Housing Starts': '주택착공건수',
        'Existing Home Sales': '기존주택판매',
        'New Home Sales': '신규주택판매',
        'Pending Home Sales m/m': '잠정주택판매 (MoM)',
        'Core CPI m/m': '근원 소비자물가지수 (MoM)',
        'CPI m/m': '소비자물가지수 (MoM)',
        'CPI y/y': '소비자물가지수 (YoY)',
        'Core PCE Price Index m/m': '근원 개인소비지출(PCE) 물가지수 (MoM)',
        'Non-Farm Employment Change': '비농업고용지수',
        'Unemployment Rate': '실업률',
        'Federal Funds Rate': '기준금리 결정 (FOMC)',
        'FOMC Statement': 'FOMC 성명서',
        'FOMC Press Conference': 'FOMC 기자회견',
        'GDP q/q': 'GDP 성장률 (QoQ)',
        'Advance GDP q/q': 'GDP 성장률 (속보치)',
        'Retail Sales m/m': '소매판매 (MoM)',
        'Core Retail Sales m/m': '근원 소매판매 (MoM)',
        'PPI m/m': '생산자물가지수 (MoM)',
        'ISM Manufacturing PMI': 'ISM 제조업 구매관리자지수',
        'ISM Services PMI': 'ISM 서비스업 구매관리자지수',
        'CB Consumer Confidence': 'CB 소비자신뢰지수',
        'JOLTS Job Openings': 'JOLTS 구인구직보고서',
    }

    def _fetch_forexfactory(self):
        """ForexFactory 주간 JSON (curl_cffi로 429 우회, 미국 주요 지표 수집)"""
        items = []
        try:
            if self.session:
                r = self.session.get(self.FF_URL, timeout=15)
            else:
                r = requests.get(self.FF_URL, headers={'User-Agent': self.HEADERS['User-Agent']}, timeout=15)
            if r.status_code == 200:
                items = r.json()
        except Exception as e:
            logger.error(f"ForexFactory API 오류: {e}")

        events = []
        for it in items if isinstance(items, list) else []:
            if it.get('country') != 'USD':
                continue
            imp = it.get('impact')
            title = it.get('title', '')
            # High/Medium 영향도 또는 주요 핵심 지표 수집
            if imp in ('High', 'Medium') or title in ('Crude Oil Inventories', 'Existing Home Sales', 'Building Permits', 'Housing Starts', 'New Home Sales'):
                try:
                    dt = datetime.fromisoformat(it['date']).astimezone(KST)
                except (KeyError, ValueError):
                    continue
                kr_name = self.FOREXFACTORY_TITLE_MAP.get(title, title)
                display_name = f"{kr_name} ({title})" if kr_name != title else title
                events.append(self._event(dt.date(), dt.time().replace(second=0), '미국', display_name,
                                          it.get('previous') or '-', '-', it.get('forecast') or '-'))
        return events

    def _fetch_korea_indicators(self):
        """한국 주요 거시경제지표 수집 (TradingEconomics 등)"""
        start_of_week, end_of_week = _week_range()
        events = []
        try:
            r = requests.get('https://tradingeconomics.com/south-korea/calendar',
                             headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=10)
            if r.status_code == 200 and self.BeautifulSoup:
                soup = self.BeautifulSoup(r.text, 'html.parser')
                table = soup.find('table', id='calendar')
                if table:
                    cur_date = None
                    KR_MAP = {
                        'Interest Rate Decision': '한국은행 기준금리 결정',
                        'Consumer Confidence': '소비자심리지수',
                        'GDP Growth Rate QoQ Adv': 'GDP 성장률 (QoQ 속보치)',
                        'GDP Growth Rate YoY Adv': 'GDP 성장률 (YoY 속보치)',
                        'Business Confidence': '기업경기실사지수 (BSI)',
                        'PPI MoM': '생산자물가지수 (MoM)',
                        'PPI YoY': '생산자물가지수 (YoY)',
                        'Inflation Rate YoY': '소비자물가지수 (YoY)',
                        'Balance of Trade': '무역수지',
                    }
                    for tr in table.find_all('tr'):
                        th = tr.find('th')
                        if th and th.text.strip() and any(m in th.text for m in [
                            'January','February','March','April','May','June','July','August','September','October','November','December']):
                            try:
                                cur_date = datetime.strptime(th.text.strip(), '%A %B %d %Y').date()
                            except Exception:
                                pass
                        if not cur_date or not (start_of_week <= cur_date <= end_of_week):
                            continue
                        tds = tr.find_all('td')
                        if len(tds) >= 4:
                            for en_key, kr_name in KR_MAP.items():
                                if any(en_key in td.text for td in tds):
                                    t_str = tds[0].text.strip()
                                    t_obj = datetime.strptime('09:00', '%H:%M').time()
                                    try:
                                        t_obj = datetime.strptime(t_str, '%I:%M %p').time()
                                    except Exception:
                                        pass
                                    actual = tds[-4].text.strip() if len(tds) >= 4 else '-'
                                    prev = tds[-3].text.strip() if len(tds) >= 3 else '-'
                                    fc = tds[-2].text.strip() if len(tds) >= 2 else '-'
                                    events.append(self._event(cur_date, t_obj, '한국', kr_name,
                                                              prev or '-', actual or '-', fc or '-'))
                                    break
        except Exception as e:
            logger.warning(f"한국 경제지표 수집 예외: {e}")
        return events

    @staticmethod
    def _merge(primary, extra):
        """같은 국가/날짜/시각/이벤트는 primary 우선 병합"""
        keys = {(e['country'], e['parsed_date'], e['event'][:8]) for e in primary}
        result = list(primary)
        for e in extra:
            key = (e['country'], e['parsed_date'], e['event'][:8])
            if key not in keys:
                keys.add(key)
                result.append(e)
        return result

    @staticmethod
    def _event(d, t, country, name, previous, actual, forecast):
        return {
            'date': d.strftime('%Y-%m-%d'),
            'time': t.strftime('%H:%M'),
            'country': country,
            'event': name,
            'importance': 3,
            'actual': actual if actual and actual != '-' else '-',
            'forecast': forecast if forecast and forecast != '-' else '-',
            'previous': previous if previous and previous != '-' else '-',
            'parsed_date': d,
            'parsed_time': t,
            'unit': '',
            'is_release': bool(actual and actual not in ('-', 'None', '')),
        }

    def _parse_html(self, html_content):
        """HTML 테이블에서 이벤트 파싱"""
        soup = self.BeautifulSoup(html_content, 'html.parser')
        events = []
        current_date_str = ''
        
        for row in soup.find_all('tr'):
            if 'theDay' in row.get('class', []):
                current_date_str = row.text.strip()
                continue
                
            if 'js-event-item' in row.get('class', []):
                # 날짜 추출
                dt_str = row.get('data-event-datetime', '')
                parsed_date = None
                parsed_time = None
                if dt_str:
                    try:
                        dt_obj = datetime.strptime(dt_str, '%Y/%m/%d %H:%M:%S')
                        parsed_date = dt_obj.date()
                        parsed_time = dt_obj.time()
                    except ValueError:
                        pass
                
                # 시간
                time_td = row.find('td', class_='time')
                time_str = time_td.text.strip() if time_td else ''
                
                # 국가
                flag_td = row.find('td', class_='flagCur')
                country = ''
                if flag_td:
                    span = flag_td.find('span')
                    if span and 'title' in span.attrs:
                        country = span['title']
                
                # 중요도 (황소 아이콘 갯수)
                imp_td = row.find('td', class_='sentiment')
                importance = 0
                if imp_td:
                    bulls = imp_td.find_all('i', class_='grayFullBullishIcon')
                    importance = len(bulls)
                    
                # 이벤트 이름
                event_td = row.find('td', class_='event')
                event_name = event_td.text.strip() if event_td else ''
                
                # 수치 (실제, 예상, 이전)
                actual_td = row.find('td', id=lambda x: x and x.startswith('eventActual'))
                actual = actual_td.text.strip() if actual_td else '-'
                if not actual: actual = '-'
                
                forecast_td = row.find('td', id=lambda x: x and x.startswith('eventForecast'))
                forecast = forecast_td.text.strip() if forecast_td else '-'
                if not forecast: forecast = '-'
                
                previous_td = row.find('td', id=lambda x: x and x.startswith('eventPrevious'))
                previous = previous_td.text.strip() if previous_td else '-'
                if not previous: previous = '-'

                # 한국어 매핑
                country_korean = '미국' if country == 'United States' else '한국' if country == 'South Korea' else country

                events.append({
                    'date': parsed_date.strftime('%Y-%m-%d') if parsed_date else current_date_str,
                    'time': time_str if time_str != 'All Day' else '종일',
                    'country': country_korean,
                    'event': event_name,
                    'importance': importance,
                    'actual': actual,
                    'forecast': forecast,
                    'previous': previous,
                    'parsed_date': parsed_date,
                    'parsed_time': parsed_time,
                    # 이전 호환성 필드
                    'unit': '',
                    'is_release': actual != '-',
                })

        return events

    WEEKDAY_KOR = ['월', '화', '수', '목', '금', '토', '일']

    def filter_high_impact_events(self, events, days=7):
        """
        주요 영향도 이벤트만 이번 주 월~일 필터링하여 반환
        """
        filtered_events = []
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).date()

        # 이번주 월요일부터 일요일까지
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        for event in events:
            event_date = event.get('parsed_date')
            country = event.get('country', '')

            # 타겟 국가(미국, 한국) 및 이번 주 범위 필터링
            if country in ('미국', '한국', 'United States', 'South Korea') and event_date:
                if start_of_week <= event_date <= end_of_week:
                    filtered_events.append(event)

        # 날짜순 및 시간순 정렬
        filtered_events.sort(key=lambda x: (x.get('parsed_date') or today, x.get('parsed_time') or datetime.now(kst).time()))
        return filtered_events

    def format_events_for_message(self, events):
        """
        이벤트를 가독성 높은 메시지 형식으로 변환 (요일 및 이전치/예측치/실제치 명확화)
        """
        if not events:
            return "이번주 시장 영향력 높은 주요 경제지표가 없습니다."

        message = "📊 <b>이번주 주요 경제지표</b>\n\n"

        current_date = None
        for event in events:
            event_date = event.get('parsed_date') or event.get('date')

            # 날짜가 변경되었을 때 요일 표기 추가
            if event_date != current_date:
                current_date = event_date
                try:
                    if hasattr(event_date, 'strftime'):
                        w = self.WEEKDAY_KOR[event_date.weekday()]
                        date_str = f"{event_date.strftime('%m/%d')}({w})"
                    else:
                        date_str = str(event_date)
                except Exception:
                    date_str = str(event_date)
                message += f"📅 <b>{date_str}</b>\n"

            # 국가 표시
            country = event.get('country', 'N/A')
            if country in ('한국', 'South Korea'):
                country_display = '🇰🇷'
            elif country in ('미국', 'United States'):
                country_display = '🇺🇸'
            else:
                country_display = f"[{country}]"

            time_str = event.get('time', 'N/A')
            event_name = event.get('event', 'N/A')
            message += f"▫️ {time_str} {country_display} <b>{event_name}</b>\n"

            unit = event.get('unit', '')
            unit_str = f" {unit}" if unit and unit.strip() else ""
            prev_val = event.get('previous', '-')
            actual_val = event.get('actual', '-')
            fc_val = event.get('forecast', '-')

            is_released = event.get('is_release', False)
            if is_released:
                # 발표 완료된 경우
                fc_text = f" (예측: {fc_val})" if fc_val != '-' else ""
                message += f"   📊 이전: {prev_val} ➡️ 실제: <b>{actual_val}</b>{unit_str}{fc_text} 📣완료\n\n"
            else:
                # 발표 예정인 경우
                fc_text = f"예측: {fc_val}" if fc_val != '-' else "예측: 미정"
                message += f"   📊 이전: {prev_val} ➡️ {fc_text}{unit_str} 📣예정\n\n"

        return message.strip()


def get_high_impact_events():
    """
    시장 영향력이 매우 높은 경제 이벤트 조회

    Returns:
        tuple: (이벤트 리스트, 포맷된 메시지)
    """
    crawler = EconomicCalendarCrawler()

    # 데이터 수집
    events = crawler.get_economic_calendar_data()

    # 매우 높은 영향도 이벤트만 필터링
    high_impact_events = crawler.filter_high_impact_events(events, days=7)

    # 메시지 포맷
    message = crawler.format_events_for_message(high_impact_events)

    return high_impact_events, message
