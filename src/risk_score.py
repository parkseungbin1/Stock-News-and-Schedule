"""
AI 리스크 스코어 모듈
각 시장 지표, 공시, SR, 재료 등을 가중치에 따라 합산해 0‑100 점수 산출.
"""
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 기본 가중치 (사용자 커스터마이징 가능)
DEFAULT_WEIGHTS = {
    "fut_ratio": 0.20,
    "sox_ratio": 0.15,
    "kp_ratio": 0.10,
    "kd_ratio": 0.10,
    "fx_ratio": 0.10,
    "cnn_score": 0.10,
    "vix": 0.10,
    "us10y": 0.05,
    "sr_status": 0.05,
    "catalyst": 0.05,
}

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_weights.json"

def load_weights():
    if WEIGHTS_PATH.exists():
        try:
            with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"리스크 가중치 로드 실패: {e}, 기본값 사용")
    return DEFAULT_WEIGHTS.copy()

def normalize(value, min_val, max_val):
    """값을 0‑1 로 스케일링"""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)

def compute_risk_score(context: dict) -> int:
    """시장 컨텍스트 dict 로부터 0‑100 위험 점수 반환.
    context 예시:
    {
        'fut_ratio': 0.6,
        'sox_ratio': 1.2,
        'kp_ratio': 0.8,
        'kd_ratio': -0.3,
        'fx_ratio': -0.4,
        'cnn_score': 30,
        'vix': 22,
        'us10y': -0.02,
        'sr_status': '강력 지지',
        'catalyst': True,
    }
    """
    weights = load_weights()
    normalized = {
        'fut_ratio': normalize(context.get('fut_ratio', 0), -1, 1),
        'sox_ratio': normalize(context.get('sox_ratio', 0), -2, 2),
        'kp_ratio': normalize(context.get('kp_ratio', 0), -2, 2),
        'kd_ratio': normalize(context.get('kd_ratio', 0), -2, 2),
        'fx_ratio': normalize(context.get('fx_ratio', 0), -1, 1),
        'cnn_score': normalize(context.get('cnn_score', 50), 0, 100),
        'vix': normalize(context.get('vix', 20), 10, 40),
        'us10y': normalize(context.get('us10y', 0), -0.5, 0.5),
        'sr_status': 1.0 if context.get('sr_status') else 0.0,
        'catalyst': 1.0 if context.get('catalyst') else 0.0,
    }
    score = sum(normalized.get(k, 0) * w for k, w in weights.items())
    return int(round(score * 100))

def render_risk_gauge(score: int) -> str:
    """HTML 원형 게이지 반환 (CSS는 generate_web 에서 정의)"""
    color = "#10b981" if score < 30 else ("#f59e0b" if score < 60 else "#ef4444")
    return f'''<div class="risk-gauge" style="background: conic-gradient({color} {score}%, #444 {score}% )">{score}%</div>'''
