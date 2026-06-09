"""
날씨 + 경제 캘린더 조합 메시지 생성
"""
from src.crawler import get_high_impact_events
from src.config import Config
from src.weather import get_weather_forecast_message


def build_daily_digest():
    """날씨와 경제 캘린더를 합친 텔레그램 메시지 생성"""
    weather_data, weather_message = get_weather_forecast_message(
        latitude=Config.WEATHER_LATITUDE,
        longitude=Config.WEATHER_LONGITUDE,
        timezone=Config.WEATHER_TIMEZONE,
        city_name=Config.WEATHER_CITY,
    )

    events, economic_message = get_high_impact_events()

    message = f"{weather_message}\n\n{economic_message}"
    return {
        'weather_data': weather_data,
        'events': events,
        'message': message,
    }