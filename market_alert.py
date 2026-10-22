"""
종가베팅 & 시초가 매도 타이밍 전문 시황 알림 텔레그램 발송 스크립트
1. [아침 07:40] 🌅 장전 시초가 매도 가이드
2. [오후 15:10] 🎯 장 마감 종가베팅 진입 가이드
3. [저녁 19:40] 🌙 종가베팅 야간 리스크 점검
"""
import argparse
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
    parser = argparse.ArgumentParser(description="종가베팅 & 시초가 매도 시황 알림 발송")
    parser.add_argument('--mode', choices=['morning', 'closing', 'night'], default=None,
                        help="발송 모드 강제 지정 (미지정 시 KST 시간 자동 판별)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    load_dotenv()

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not (token and chat_id):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)

    print(f"시황 가이드 생성 중... (모드: {args.mode or '시간대 자동 판별'})")
    msg = get_market_score_message(mode=args.mode)
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
