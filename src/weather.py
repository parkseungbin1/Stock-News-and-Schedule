"""
Open-Meteo를 사용한 날씨 조회
기본 위치는 서울이며, 환경변수로 변경할 수 있습니다.
"""
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class WeatherService:
    """날씨 조회 서비스"""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    WEATHER_CODES = {
        0: "맑음",
        1: "대체로 맑음",
        2: "부분적으로 흐림",
        3: "흐림",
        45: "안개",
        48: "안개(상고대)",
        51: "가랑비",
        53: "약한 가랑비",
        55: "강한 가랑비",
        61: "약한 비",
        63: "보통 비",
        65: "강한 비",
        66: "약한 싸락비",
        67: "강한 싸락비",
        71: "약한 눈",
        73: "보통 눈",
        75: "강한 눈",
        77: "눈 알갱이",
        80: "소나기",
        81: "강한 소나기",
        82: "격한 소나기",
        85: "약한 눈 소나기",
        86: "강한 눈 소나기",
        95: "뇌우",
        96: "우박을 동반한 뇌우",
        99: "강한 우박을 동반한 뇌우",
    }

    def __init__(self, latitude=37.5665, longitude=126.9780, timezone="Asia/Seoul", city_name="서울"):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self.city_name = city_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def fetch_weather(self, forecast_days=3):
        """현재 날씨와 일별 예보를 조회"""
        params = {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'timezone': self.timezone,
            'forecast_days': forecast_days,
            'current_weather': 'true',
            'daily': 'weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        }

        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            current_weather = data.get('current_weather', {})
            daily = data.get('daily', {})

            return {
                'city_name': self.city_name,
                'timezone': data.get('timezone', self.timezone),
                'current': {
                    'time': current_weather.get('time', ''),
                    'temperature': current_weather.get('temperature'),
                    'wind_speed': current_weather.get('windspeed'),
                    'weather_code': current_weather.get('weathercode'),
                },
                'daily': self._build_daily_forecast(daily),
            }
        except requests.RequestException as e:
            logger.error(f"날씨 API 접근 오류: {e}")
        except ValueError as e:
            logger.error(f"날씨 JSON 파싱 오류: {e}")

        return {
            'city_name': self.city_name,
            'timezone': self.timezone,
            'current': {},
            'daily': [],
        }

    def _build_daily_forecast(self, daily_data):
        dates = daily_data.get('time', []) or []
        weather_codes = daily_data.get('weathercode', []) or []
        max_temps = daily_data.get('temperature_2m_max', []) or []
        min_temps = daily_data.get('temperature_2m_min', []) or []
        precipitation_probs = daily_data.get('precipitation_probability_max', []) or []

        forecast = []
        for index, date_value in enumerate(dates):
            forecast.append({
                'date': date_value,
                'weekday': self._get_weekday_label(date_value),
                'weather': self._describe_weather_code(weather_codes[index] if index < len(weather_codes) else None),
                'max_temp': max_temps[index] if index < len(max_temps) else None,
                'min_temp': min_temps[index] if index < len(min_temps) else None,
                'precipitation_probability': precipitation_probs[index] if index < len(precipitation_probs) else None,
            })

        return forecast

    def _describe_weather_code(self, weather_code):
        try:
            return self.WEATHER_CODES.get(int(weather_code), f"날씨 코드 {weather_code}")
        except (TypeError, ValueError):
            return "날씨 정보 없음"

    def _get_weekday_label(self, date_value):
        try:
            weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
            parsed_date = datetime.strptime(date_value, "%Y-%m-%d")
            return weekday_names[parsed_date.weekday()]
        except Exception:
            return ""

    def format_weather_for_message(self, weather_data):
        """텔레그램용 날씨 메시지 생성"""
        current = weather_data.get('current', {})
        daily = weather_data.get('daily', [])
        city_name = weather_data.get('city_name', self.city_name)

        lines = [
            f"🌤 오늘의 날씨 ({city_name})",
            f"{'=' * 50}",
        ]

        if current:
            lines.extend([
                f"⏰ 현재 시각: {current.get('time', 'N/A')}",
                f"🌡 현재 기온: {self._format_number(current.get('temperature'))}°C",
                f"🌬 바람: {self._format_number(current.get('wind_speed'))} m/s",
                f"☁️ 상태: {self._describe_weather_code(current.get('weather_code'))}",
            ])
        else:
            lines.append("날씨 정보를 불러오지 못했습니다.")

        if daily:
            lines.append("")
            lines.append("📅 3일 예보")
            for forecast in daily[:3]:
                lines.append(
                    f"- {forecast['date']} ({forecast['weekday']}): {forecast['weather']} | "
                    f"최저 {self._format_number(forecast['min_temp'])}° / 최고 {self._format_number(forecast['max_temp'])}°"
                )
                if forecast.get('precipitation_probability') is not None:
                    lines.append(f"  강수확률: {self._format_number(forecast.get('precipitation_probability'))}%")

        return "\n".join(lines)

    def _format_number(self, value):
        if value is None:
            return "-"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return f"{value}"


def get_weather_forecast_message(latitude=37.5665, longitude=126.9780, timezone="Asia/Seoul", city_name="서울"):
    """기본 서울 날씨 메시지 생성"""
    service = WeatherService(latitude=latitude, longitude=longitude, timezone=timezone, city_name=city_name)
    weather_data = service.fetch_weather()
    return weather_data, service.format_weather_for_message(weather_data)