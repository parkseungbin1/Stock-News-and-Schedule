"""
날씨 + 경제 캘린더를 합쳐 텔레그램으로 전송하는 단발 실행 스크립트
"""
import sys
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.digest import build_daily_digest
from src.telegram_sender import send_economic_calendar_to_telegram_sync


def main():
    print("날씨 + 경제 캘린더 전송 시작...")
    print("-" * 60)

    try:
        Config.validate()

        digest = build_daily_digest()
        print(f"수집된 경제 이벤트 수: {len(digest['events'])}")
        print("\n전송할 메시지:")
        print("-" * 60)
        print(digest['message'])
        print("-" * 60)

        print("\n텔레그램으로 전송 중...")
        success = send_economic_calendar_to_telegram_sync(
            digest['message'],
            Config.TELEGRAM_BOT_TOKEN,
            Config.TELEGRAM_CHAT_ID,
        )

        if success:
            print("✓ 날씨 + 경제 캘린더 전송 성공!")
        else:
            print("✗ 텔레그램 전송 실패")
            sys.exit(1)

    except ValueError as e:
        print(f"설정 오류: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()