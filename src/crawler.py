"""
네이버 증권 글로벌 경제 캘린더 크롤러
시장 영향력이 매우 높음인 항목만 수집
"""
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class EconomicCalendarCrawler:
    """네이버 증권 글로벌 경제 캘린더 크롤러"""

    # 네이버 증권 경제지표 API URL
    BASE_URL = "https://stock.naver.com/api/securityService/economic/indicator/nations/upcoming"
    DEFAULT_NATION_TYPES = ("KOR", "USA")
    HIGH_IMPACT_THRESHOLD = 4

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _fetch_nation_events(self, nation_type):
        """
        특정 국가의 경제지표 데이터를 수집

        Args:
            nation_type (str): 국가 코드

        Returns:
            list: 원본 API 응답 목록
        """
        params = [
            ('nationTypeList', nation_type),
            ('nationTypeList', nation_type),
            ('gteImportance', str(self.HIGH_IMPACT_THRESHOLD)),
        ]

        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, list):
                logger.warning(f"경제 지표 응답 형식이 올바르지 않습니다: {nation_type}")
                return []

            return data

        except requests.RequestException as e:
            logger.error(f"네이버 증권 경제지표 API 접근 오류({nation_type}): {e}")
            return []
        except ValueError as e:
            logger.error(f"경제지표 JSON 파싱 오류({nation_type}): {e}")
            return []

    def get_economic_calendar_data(self, nation_types=None):
        """
        네이버 증권에서 글로벌 경제 캘린더 데이터 수집

        Args:
            nation_types (list|tuple|None): 국가 코드 목록

        Returns:
            list: 경제 이벤트 데이터 리스트
        """
        nation_types = nation_types or self.DEFAULT_NATION_TYPES
        events = []
        seen = set()

        for nation_type in nation_types:
            for item in self._fetch_nation_events(nation_type):
                event_key = (
                    item.get('reutersCode'),
                    item.get('releaseDate'),
                    item.get('releaseTime'),
                )
                if event_key in seen:
                    continue
                seen.add(event_key)

                events.append({
                    'date': self._format_release_date(item.get('releaseDate', '')),
                    'time': self._format_release_time(item.get('releaseTime', '')),
                    'country': item.get('nationKoreanName', nation_type),
                    'event': item.get('name', ''),
                    'importance': int(item.get('importance', 0) or 0),
                    'importance_label': self._format_importance(item.get('importance', 0)),
                    'period': item.get('period', ''),
                    'previous': self._format_value(item.get('previousValue')),
                    'actual': self._format_value(item.get('actualValue')),
                    'unit': self._build_unit_label(item.get('indicatorUnit'), item.get('unitScale')),
                    'is_release': bool(item.get('isRelease')),
                    'parsed_date': self._parse_release_date(item.get('releaseDate', '')),
                    'parsed_time': self._parse_release_time(item.get('releaseTime', '')),
                })

        events.sort(key=lambda x: (x.get('parsed_date') or datetime.max.date(), x.get('parsed_time') or datetime.max.time()))
        return events

    def _format_release_date(self, release_date):
        """날짜 문자열을 사람이 읽기 쉬운 형식으로 변환"""
        parsed_date = self._parse_release_date(release_date)
        return parsed_date.strftime('%Y-%m-%d') if parsed_date else release_date

    def _format_release_time(self, release_time):
        """시간 문자열을 HH:MM 형식으로 변환"""
        parsed_time = self._parse_release_time(release_time)
        return parsed_time.strftime('%H:%M') if parsed_time else release_time

    def _parse_release_date(self, release_date):
        """YYYYMMDD 형식의 날짜를 date로 변환"""
        try:
            return datetime.strptime(str(release_date), '%Y%m%d').date()
        except ValueError:
            return None

    def _parse_release_time(self, release_time):
        """HHMMSS 형식의 시간을 time으로 변환"""
        try:
            return datetime.strptime(str(release_time).zfill(6), '%H%M%S').time()
        except ValueError:
            return None

    def _format_importance(self, importance):
        """숫자 중요도를 메시지용 텍스트로 변환"""
        return '매우 높음' if int(importance or 0) >= self.HIGH_IMPACT_THRESHOLD else '높음'

    def _format_value(self, value):
        """숫자나 빈 값을 문자열로 정리"""
        if value in (None, '', 0, 0.0):
            return '-'
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _build_unit_label(self, indicator_unit, unit_scale):
        """단위와 스케일을 합쳐 표시용 문자열로 변환"""
        parts = [part for part in [indicator_unit, unit_scale] if part]
        return ' '.join(parts)

    def filter_high_impact_events(self, events, days=7):
        """
        매우 높은 영향도의 이벤트만 필터링

        Args:
            events (list): 모든 경제 이벤트
            days (int): 조회 기간 (기본값 7일)

        Returns:
            list: 필터링된 이벤트
        """
        filtered_events = []
        today = datetime.now().date()
        week_later = today + timedelta(days=days)

        for event in events:
            event_date = event.get('parsed_date') or self._parse_release_date(event.get('date', ''))

            if event.get('importance', 0) >= self.HIGH_IMPACT_THRESHOLD and event_date and today <= event_date <= week_later:
                event['parsed_date'] = event_date
                filtered_events.append(event)

        # 날짜순 정렬
        filtered_events.sort(key=lambda x: (x.get('parsed_date') or today, x.get('parsed_time') or datetime.now().time()))
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

        message = "📊 이번주 주요 경제지표 (시장 영향력: 매우 높음)\n"
        message += f"{'='*50}\n\n"

        current_date = None
        for event in events:
            event_date = event.get('parsed_date') or event.get('date')

            # 날짜가 변경되었을 때
            if event_date != current_date:
                current_date = event_date
                message += f"📅 {event_date}\n"

            message += f"⏰ {event.get('time', 'N/A')} | 🌍 {event.get('country', 'N/A')} | {event.get('importance_label', '매우 높음')}\n"
            message += f"📈 {event.get('event', 'N/A')}\n"
            if event.get('period'):
                message += f"📌 기간: {event.get('period')}\n"
            if event.get('previous') or event.get('actual'):
                message += f"📊 이전: {event.get('previous', '-')} | 실제: {event.get('actual', '-')}\n"
            if event.get('unit'):
                message += f"📐 단위: {event.get('unit')}\n"

            message += "\n"

        return message


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
