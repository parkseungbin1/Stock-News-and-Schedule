"""
텔레그램 전송 테스트 스크립트
"""
import sys
import time
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.digest import build_daily_digest
from src.telegram_sender import send_economic_calendar_to_telegram_sync


def test_telegram():
    """날씨 + 경제 캘린더 전송 테스트"""
    print("날씨 + 경제 캘린더 전송 테스트 시작...")
    print("-" * 60)
    
    try:
        # 설정 검증
        Config.validate()
        
        # 데이터 수집
        digest = build_daily_digest()
        
        print(f"수집된 이벤트 수: {len(digest['events'])}")
        print("\n전송할 메시지:")
        print("[날씨]\n", digest['weather_message'])
        print("-" * 30)
        print("[경제]\n", digest['economic_message'])
        print("-" * 30)
        
        # 텔레그램 전송
        print("\n텔레그램으로 전송 중...")
        success_w = send_economic_calendar_to_telegram_sync(
            digest['weather_message'],
            Config.TELEGRAM_BOT_TOKEN,
            Config.TELEGRAM_CHAT_ID
        )
        
        # 메시지 간 간격을 두기 위해 3초 대기
        time.sleep(3)
        
        success_e = send_economic_calendar_to_telegram_sync(
            digest['economic_message'],
            Config.TELEGRAM_BOT_TOKEN,
            Config.TELEGRAM_CHAT_ID
        )
        
        if success_w and success_e:
            print("✓ 날씨 + 경제 캘린더 전송 성공!")
        else:
            print("✗ 텔레그램 전송 실패")
    
    except ValueError as e:
        print(f"설정 오류: {e}")
        print("\n.env 파일에 다음을 설정하세요:")
        print("TELEGRAM_BOT_TOKEN=your_bot_token")
        print("TELEGRAM_CHAT_ID=your_chat_id")
        sys.exit(1)
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    test_telegram()
