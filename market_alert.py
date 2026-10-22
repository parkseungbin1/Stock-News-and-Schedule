"""
오늘의 시황 종합 점수 및 해설 텔레그램 발송 스크립트
(매일 오후 3시 10분, 오후 7시 40분 자동 실행)
"""
import logging
import os
import sys
from pathlib import Path

# Windows 콘솔 출력 시 이모지 인코딩 오류 방지
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.market_score import get_market_score_message
from src.telegram_sender import send_economic_calendar_to_telegram_sync


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    load_dotenv()

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not (token and chat_id):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)

    print("시황 점수 및 해설 생성 중...")
    msg = get_market_score_message()
    print("-" * 40)
    print(msg)
    print("-" * 40)

    print("텔레그램 전송 중...")
    ok = send_economic_calendar_to_telegram_sync(msg, token, chat_id)
    if ok:
        print("✓ 시황 알림 전송 성공!")
    else:
        print("✗ 시황 알림 전송 실패")
        sys.exit(1)


if __name__ == '__main__':
    main()
