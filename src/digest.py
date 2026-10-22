"""
날씨 + 시황 스코어 + 경제 캘린더 조합 메시지 생성
"""
from src.crawler import get_high_impact_events
from src.config import Config
from src.weather import get_weather_forecast_message
from src.market_score import get_market_score_message


def build_daily_digest():
    """날씨, 오늘의 시황 스코어, 경제 캘린더를 합친 텔레그램 메시지 생성"""
    weather_data, weather_message = get_weather_forecast_message(
        latitude=Config.WEATHER_LATITUDE,
        longitude=Config.WEATHER_LONGITUDE,
        timezone=Config.WEATHER_TIMEZONE,
        city_name=Config.WEATHER_CITY,
    )

    events, economic_message = get_high_impact_events()
    market_message = get_market_score_message()

    return {
        'weather_data': weather_data,
        'weather_message': weather_message,
        'market_message': market_message,
        'events': events,
        'economic_message': economic_message,
    }