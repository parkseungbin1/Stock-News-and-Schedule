"""
텔레그램 전송 테스트 스크립트
"""
import sys
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.crawler import get_high_impact_events
from src.telegram_sender import send_economic_calendar_to_telegram_sync


def test_telegram():
    """텔레그램 전송 테스트"""
    print("텔레그램 전송 테스트 시작...")
    print("-" * 60)
    
    try:
        # 설정 검증
        Config.validate()
        
        # 데이터 수집
        events, message = get_high_impact_events()
        
        print(f"수집된 이벤트 수: {len(events)}")
        print("\n전송할 메시지:")
        print("-" * 60)
        print(message)
        print("-" * 60)
        
        # 텔레그램 전송
        print("\n텔레그램으로 전송 중...")
        success = send_economic_calendar_to_telegram_sync(
            message,
            Config.TELEGRAM_BOT_TOKEN,
            Config.TELEGRAM_CHAT_ID
        )
        
        if success:
            print("✓ 텔레그램 전송 성공!")
        else:
            print("✗ 텔레그램 전송 실패")
    
    except ValueError as e:
        print(f"설정 오류: {e}")
        print("\n.env 파일에 다음을 설정하세요:")
        print("TELEGRAM_BOT_TOKEN=your_bot_token")
        print("TELEGRAM_CHAT_ID=your_chat_id")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_telegram()
