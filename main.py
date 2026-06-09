"""
메인 실행 파일
네이버 증권 글로벌 경제 캘린더에서 시장 영향력 매우 높은 항목을 
매일 아침 7시에 텔레그램으로 전송
"""
import sys
import logging
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.logger import setup_logger
from src.scheduler import create_scheduler


def main():
    """메인 함수"""
    
    # 로거 설정
    logger = setup_logger()
    logger.info("="*60)
    logger.info("경제 캘린더 텔레그램 봇 시작")
    logger.info("="*60)
    
    try:
        # 설정 검증
        Config.validate()
        logger.info(f"설정 검증 완료")
        logger.info(f"전송 시간: {Config.SCHEDULE_HOUR:02d}:{Config.SCHEDULE_MINUTE:02d}")
        
        # 스케줄러 생성 및 시작
        scheduler = create_scheduler(
            bot_token=Config.TELEGRAM_BOT_TOKEN,
            chat_id=Config.TELEGRAM_CHAT_ID,
            hour=Config.SCHEDULE_HOUR,
            minute=Config.SCHEDULE_MINUTE
        )
        
        logger.info("스케줄러가 시작되었습니다.")
        logger.info("프로그램을 종료하려면 Ctrl+C를 입력하세요.")
        
        # 무한 실행
        import time
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except ValueError as e:
        logger.error(f"설정 오류: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
