@echo off
chcp 65001 > nul
title BiniStock AI 실시간 시장 리스크 & 15:10 종가베팅 진단
cd /d "%~dp0"
python scripts\check_live_risk.py
