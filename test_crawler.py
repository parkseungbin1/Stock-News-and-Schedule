"""
크롤러 테스트 스크립트
"""
import sys
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.crawler import get_high_impact_events


def test_crawler():
    """크롤러 테스트"""
    print("경제 캘린더 데이터 수집 중...")
    print("-" * 60)
    
    try:
        events, message = get_high_impact_events()
        
        print(f"수집된 이벤트 수: {len(events)}")
        print("-" * 60)
        print(message)
        print("-" * 60)
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_crawler()
