"""
주식 이벤트(잠정실적/어닝서프라이즈, 자사주 취득, IR 일정) 텔레그램 알림 단발 실행 스크립트

사용법:
    python disclosure_alert.py            # 신규 공시 알림
    python disclosure_alert.py --morning  # + 오늘의 실적발표(IR) 일정 요약
    python disclosure_alert.py --dry-run  # 텔레그램 전송 없이 출력만
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 콘솔 등에서 이모지 출력 시 cp949 인코딩 오류 방지
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from src import disclosure as d
from src.telegram_sender import send_economic_calendar_to_telegram_sync


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--morning', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    load_dotenv()

    api_key = os.getenv('DART_API_KEY')
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not api_key:
        print("DART_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)
    if not args.dry_run and not (token and chat_id):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)

    dart = d.Dart(api_key)
    state = d.load_state()
    watch = d.load_watchlist()
    now = datetime.now(d.KST)
    messages = []

    if args.morning:
        d.backfill_ir(dart, state)
        blocks = d.today_ir_blocks(state, watch)
        header = f"🗓 <b>오늘의 실적발표(IR) 일정</b> ({now.strftime('%m/%d')})\n\n"
        messages += d.split_messages(header, blocks) if blocks else [header + "오늘 예정된 IR 공시가 없습니다."]

    sections = d.collect_new_disclosures(dart, state, watch)
    slot = '오전' if now.hour < 12 else '오후'
    for title, blocks in sections:
        messages += d.split_messages(f"{title} ({now.strftime('%m/%d')} {slot})\n\n", blocks)
    if not sections:
        logging.info("신규 알림 대상 공시 없음")

    ok = True
    for m in messages:
        if args.dry_run:
            print(m, '\n' + '-' * 40)
        else:
            ok &= send_economic_calendar_to_telegram_sync(m, token, chat_id)
            time.sleep(1)

    if not args.dry_run:
        d.save_state(state)  # dry-run은 상태 저장 안 함 (같은 공시 재알림 가능하도록)
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
