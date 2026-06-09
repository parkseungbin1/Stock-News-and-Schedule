"""
네이버 증권 글로벌 경제 캘린더 크롤러
시장 영향력이 매우 높음인 항목만 수집
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class EconomicCalendarCrawler:
    """네이버 증권 글로벌 경제 캘린더 크롤러"""
    
    # 네이버 증권 글로벌 경제 캘린더 URL
    BASE_URL = "https://finance.naver.com/world/economic_calendar.naver"
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # 영향도 매핑
    IMPACT_LEVELS = {
        '매우높음': 'very_high',
        'high': 'high',
        'medium': 'medium',
        '낮음': 'low'
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def get_economic_calendar_data(self):
        """
        네이버 증권에서 글로벌 경제 캘린더 데이터 수집
        
        Returns:
            list: 경제 이벤트 데이터 리스트
        """
        try:
            # 페이지 요청
            response = self.session.get(self.BASE_URL, timeout=10)
            response.encoding = 'euc-kr'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 테이블 찾기
            table = soup.find('table', {'class': 'type_2'})
            if not table:
                logger.warning("경제 캘린더 테이블을 찾을 수 없습니다")
                return []
            
            events = []
            rows = table.find_all('tr')[1:]  # 헤더 제외
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 6:
                    continue
                
                try:
                    event_data = {
                        'date': cells[0].text.strip(),
                        'time': cells[1].text.strip(),
                        'country': cells[2].text.strip(),
                        'event': cells[3].text.strip(),
                        'importance': cells[4].text.strip(),
                        'forecast': cells[5].text.strip() if len(cells) > 5 else '',
                        'previous': cells[6].text.strip() if len(cells) > 6 else '',
                        'result': cells[7].text.strip() if len(cells) > 7 else ''
                    }
                    events.append(event_data)
                except Exception as e:
                    logger.error(f"행 파싱 오류: {e}")
                    continue
            
            return events
            
        except requests.RequestException as e:
            logger.error(f"네이버 증권 접근 오류: {e}")
            return []
    
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
            # 영향도가 "매우 높음"인 경우만
            if '매우높음' in event.get('importance', '') or '매우 높음' in event.get('importance', ''):
                try:
                    event_date = self._parse_date(event['date'])
                    # 1주일 범위 내인지 확인
                    if event_date and today <= event_date <= week_later:
                        event['parsed_date'] = event_date
                        filtered_events.append(event)
                except Exception as e:
                    logger.error(f"날짜 파싱 오류: {e}")
                    continue
        
        # 날짜순 정렬
        filtered_events.sort(key=lambda x: x.get('parsed_date', datetime.now().date()))
        return filtered_events
    
    def _parse_date(self, date_str):
        """
        날짜 문자열 파싱
        
        Args:
            date_str (str): 날짜 문자열
        
        Returns:
            date: 파싱된 날짜 객체
        """
        try:
            # 다양한 날짜 형식 지원
            for fmt in ['%m/%d', '%Y-%m-%d', '%Y.%m.%d']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    # 월/일 형식인 경우 올해 연도 추가
                    if '%Y' not in fmt:
                        date_obj = date_obj.replace(year=datetime.now().year)
                    return date_obj.date()
                except ValueError:
                    continue
        except Exception as e:
            logger.error(f"날짜 파싱 실패 ({date_str}): {e}")
        
        return None
    
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
            event_date = event.get('parsed_date', event.get('date'))
            
            # 날짜가 변경되었을 때
            if event_date != current_date:
                current_date = event_date
                message += f"📅 {event_date}\n"
            
            message += f"⏰ {event.get('time', 'N/A')}\n"
            message += f"🌍 {event.get('country', 'N/A')}\n"
            message += f"📈 {event.get('event', 'N/A')}\n"
            
            # 예측값과 이전값
            forecast = event.get('forecast', '')
            previous = event.get('previous', '')
            if forecast or previous:
                message += f"📊 예측: {forecast} | 이전: {previous}\n"
            
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
