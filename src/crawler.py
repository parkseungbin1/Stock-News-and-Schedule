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
        Investing.com에서 이번 주(월~일) 글로벌 경제 캘린더 데이터 수집
        """
        events = self._fetch_investing()
        if events:
            logger.info(f"Investing.com 수집 성공: {len(events)}건")
            return events

        logger.warning("Investing.com 수집 실패 → 네이버 + ForexFactory로 대체합니다.")
        events = self._fetch_naver()
        events = self._merge(events, self._fetch_forexfactory())
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

    # ---------------- ForexFactory ----------------
    FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def _fetch_forexfactory(self):
        """ForexFactory 주간 JSON (미국 High 지표, 실제값은 제공 안 됨)"""
        try:
            r = requests.get(self.FF_URL, headers={'User-Agent': self.HEADERS['User-Agent']}, timeout=15)
            r.raise_for_status()
            items = r.json()
        except Exception as e:
            logger.error(f"ForexFactory API 오류: {e}")
            return []

        events = []
        for it in items:
            if it.get('country') != 'USD' or it.get('impact') != 'High':
                continue
            try:
                dt = datetime.fromisoformat(it['date']).astimezone(KST)
            except (KeyError, ValueError):
                continue
            events.append(self._event(dt.date(), dt.time().replace(second=0), '미국', it.get('title', ''),
                                      it.get('previous') or '-', '-', it.get('forecast') or '-'))
        return events

    @staticmethod
    def _merge(primary, extra):
        """같은 국가/날짜/시각 이벤트는 primary(네이버, 한글명) 우선"""
        keys = {(e['country'], e['parsed_date'], e['parsed_time']) for e in primary}
        return primary + [e for e in extra if (e['country'], e['parsed_date'], e['parsed_time']) not in keys]

    @staticmethod
    def _event(d, t, country, name, previous, actual, forecast):
        return {
            'date': d.strftime('%Y-%m-%d'),
            'time': t.strftime('%H:%M'),
            'country': country,
            'event': name,
            'importance': 3,
            'actual': actual,
            'forecast': forecast,
            'previous': previous,
            'parsed_date': d,
            'parsed_time': t,
            'unit': '',
            'is_release': actual != '-',
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

    def filter_high_impact_events(self, events, days=7):
        """
        매우 높은 영향도의 이벤트만 이번 주 월~일 필터링하여 반환
        """
        filtered_events = []
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).date()
        
        # 이번주 월요일부터 일요일까지
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        for event in events:
            event_date = event.get('parsed_date')
            
            # 중요도 3(최상)이고 타겟 국가이며 날짜가 이번 주 내에 포함될 경우
            country_en = 'United States' if event.get('country') == '미국' else 'South Korea' if event.get('country') == '한국' else ''
            
            if event.get('importance', 0) >= 3 and country_en in self.TARGET_COUNTRIES:
                if event_date and start_of_week <= event_date <= end_of_week:
                    filtered_events.append(event)

        # 날짜순 정렬
        kst = timezone(timedelta(hours=9))
        filtered_events.sort(key=lambda x: (x.get('parsed_date') or today, x.get('parsed_time') or datetime.now(kst).time()))
        return filtered_events

    def format_events_for_message(self, events):
        """
        이벤트를 메시지 형식으로 변환

        Args:
            events (list): 경제 이벤트 리스트

        Returns:
            str: 포맷된 메시지
        """
        if not events:
            return "이번주 시장 영향력 매우 높은 경제지표가 없습니다."

        message = "📊 <b>이번주 주요 경제지표</b>\n\n"

        current_date = None
        for event in events:
            event_date = event.get('parsed_date') or event.get('date')

            # 날짜가 변경되었을 때
            if event_date != current_date:
                current_date = event_date
                # MM/DD 형식으로 날짜 축소
                try:
                    if hasattr(event_date, 'strftime'):
                        date_str = event_date.strftime('%m/%d')
                    else:
                        date_str = str(event_date)[5:10] if len(str(event_date)) >= 10 else str(event_date)
                except Exception:
                    date_str = str(event_date)
                message += f"📅 <b>{date_str}</b>\n"

            release_status = '완료' if event.get('is_release') else '예정'
            
            # 국가 표시 간소화
            country = event.get('country', 'N/A')
            if country == '한국':
                country_display = '🇰🇷'
            elif country == '미국':
                country_display = '🇺🇸'
            else:
                country_display = f"[{country}]"

            # 이벤트 시간은 HH:MM만 표시되므로 그대로 사용
            message += f"▫️ {event.get('time', 'N/A')} {country_display} <b>{event.get('event', 'N/A')}</b>\n"
            
            unit = event.get('unit', '')
            unit_str = f"({unit})" if unit and unit.strip() else ""
            prev_val = event.get('previous', '-')
            actual_val = event.get('actual', '-')
            
            # 기간 표시 생략하고 단순화
            message += f"   📊 {prev_val} ➡️ {actual_val} {unit_str} 📣{release_status}\n\n"

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
