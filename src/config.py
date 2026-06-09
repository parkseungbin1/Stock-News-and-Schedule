"""
설정 관리
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class Config:
    """기본 설정"""
    
    # 텔레그램 설정
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # 스케줄링 설정
    SCHEDULE_HOUR = int(os.getenv('SCHEDULE_HOUR', '7'))
    SCHEDULE_MINUTE = int(os.getenv('SCHEDULE_MINUTE', '0'))

    # 날씨 설정
    WEATHER_CITY = os.getenv('WEATHER_CITY', '서울')
    WEATHER_LATITUDE = float(os.getenv('WEATHER_LATITUDE', '37.5665'))
    WEATHER_LONGITUDE = float(os.getenv('WEATHER_LONGITUDE', '126.9780'))
    WEATHER_TIMEZONE = os.getenv('WEATHER_TIMEZONE', 'Asia/Seoul')
    
    # 로깅 설정
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'economic_calendar.log')
    
    # 크롤링 관련
    USER_AGENT = os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # 데이터 조회 기간 (일)
    DATA_DAYS = int(os.getenv('DATA_DAYS', '7'))
    
    @classmethod
    def validate(cls):
        """필수 설정값 검증"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다")
        if not cls.TELEGRAM_CHAT_ID:
            raise ValueError("TELEGRAM_CHAT_ID가 설정되지 않았습니다")
        return True


class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """운영 환경 설정"""
    DEBUG = False
    LOG_LEVEL = 'INFO'


def get_config(env='development'):
    """
    환경에 따른 설정 객체 반환
    
    Args:
        env (str): 환경 ('development' 또는 'production')
    
    Returns:
        Config: 설정 객체
    """
    if env == 'production':
        return ProductionConfig
    return DevelopmentConfig
