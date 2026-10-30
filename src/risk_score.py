"""
AI 실시간 시장 리스크 스코어 모듈 (Market Risk Index Engine)

[산출 원리 & 가중치 기준]
글로벌 금융시장 및 국내 증시의 7대 핵심 선행/동행 지표를 실시간 수집하여,
0점(극단적 안정/저위험) ~ 100점(극단적 패닉/고위험)의 복합 위험도를 산출합니다.

1. 미국 E-mini 나스닥100 선물 등락률 (25% 가중치):
   - 야간/주간 글로벌 기술주 투자심리의 최우선 선행 지표 (하락폭 클수록 위험도 급증)
2. 필라델피아 반도체 지수 등락률 (20% 가중치):
   - 코스피 시총 30%를 차지하는 삼성전자/SK하이닉스 주가의 직결 선행 지표
3. 국내 코스피 & 코스닥 등락률 (25% 가중치: 코스피 15% + 코스닥 10%):
   - 국내 장중 실시간 지수 하락 압력 및 투매 강도 측정
4. 원/달러 환율 등락률 (10% 가중치):
   - 환율 급등 시 외국인 자금 이탈 가속화 위험 반영
5. VIX 변동성 지수 (10% 가중치):
   - 미국 S&P500 옵션 시장의 변동성 및 월가 공포 수치 (20 이상 시 위험도 급증)
6. CNN Fear & Greed Index (5% 가중치):
   - 글로벌 투자자 심리 상태 (공포 구간일수록 리스크 상승)
7. 미국 10년물 국채금리 일간 변동폭 (5% 가중치):
   - 금리 급등 시 밸류에이션 부담 및 성장주 하방 압력 반영
"""
import logging

logger = logging.getLogger(__name__)


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """값을 [min_val, max_val] 범위로 제한"""
    return max(min_val, min(max_val, value))


def compute_risk_score(context: dict) -> int:
    """
    시장 컨텍스트 딕셔너리로부터 0~100점의 위험도 점수를 산출
    (0점: 매우 안정/호황 ~ 100점: 극단적 패닉/폭락장)
    """
    fut_ratio = float(context.get('fut_ratio', 0.0) or 0.0)
    sox_ratio = float(context.get('sox_ratio', 0.0) or 0.0)
    kp_ratio = float(context.get('kp_ratio', 0.0) or 0.0)
    kd_ratio = float(context.get('kd_ratio', 0.0) or 0.0)
    fx_ratio = float(context.get('fx_ratio', 0.0) or 0.0)
    cnn_score = float(context.get('cnn_score', 50.0) or 50.0)
    vix = float(context.get('vix', 18.0) or 18.0)
    us10y_diff = float(context.get('us10y', 0.0) or 0.0)

    # 1. 나스닥 선물 위험도 (기준: -1.5% 이하 시 1.0, +1.5% 이상 시 0.0)
    fut_risk = clamp(0.5 - (fut_ratio / 3.0)) * 25.0

    # 2. 반도체 지수 위험도 (기준: -2.0% 이하 시 1.0, +2.0% 이상 시 0.0)
    sox_risk = clamp(0.5 - (sox_ratio / 4.0)) * 20.0

    # 3. 코스피/코스닥 위험도 (기준: -2.0% 이하 시 1.0, +2.0% 이상 시 0.0)
    kp_risk = clamp(0.5 - (kp_ratio / 4.0)) * 15.0
    kd_risk = clamp(0.5 - (kd_ratio / 4.0)) * 10.0

    # 4. 원/달러 환율 위험도 (환율 +1.0% 급등 시 1.0, -1.0% 하락 시 0.0)
    fx_risk = clamp(0.5 + (fx_ratio / 2.0)) * 10.0

    # 5. VIX 변동성 위험도 (12 이하 0.0, 35 이상 1.0)
    vix_risk = clamp((vix - 12.0) / 23.0) * 10.0

    # 6. CNN 공포탐욕 위험도 (0점 극단공포 -> 위험도 1.0, 100점 극단탐욕 -> 위험도 0.0)
    cnn_risk = clamp((100.0 - cnn_score) / 100.0) * 5.0

    # 7. 미국 10년물 금리 변동 위험도 (+0.06%p 급등 시 1.0, -0.06%p 급락 시 0.0)
    us10y_risk = clamp(0.5 + (us10y_diff / 0.12)) * 5.0

    total_score = fut_risk + sox_risk + kp_risk + kd_risk + fx_risk + vix_risk + cnn_risk + us10y_risk
    clamped_score = int(round(clamp(total_score, 0.0, 100.0)))
    return clamped_score


def get_risk_assessment(score: int) -> dict:
    """점수별 상세 진단 및 행동 지침 반환"""
    if score < 35:
        return {
            'score': score,
            'grade': '안정 (저위험)',
            'color': '#10b981',
            'badge_class': 'risk-good',
            'desc': '시장 위험도 낮음: 공격적 매매 및 종가베팅 비중 100% 정상 운용 가능 (상승 우세 장세)'
        }
    elif score < 65:
        return {
            'score': score,
            'grade': '주의 (중위험)',
            'color': '#f59e0b',
            'badge_class': 'risk-caution',
            'desc': '단기 변동성 주의: 분할 매수 및 기계적 익절(+3%~+5%) 원칙 엄격 준수 (박스권/혼조세)'
        }
    else:
        return {
            'score': score,
            'grade': '경고 (고위험)',
            'color': '#ef4444',
            'badge_class': 'risk-danger',
            'desc': '시장 하방 압력 경계: 현금 비중 50% 이상 확보 및 보수적 매매 대응 (글로벌/국내 급락 장세)'
        }
