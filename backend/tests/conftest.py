"""pytest 公共配置"""
import sys
from pathlib import Path

# 让测试能直接 `from app...` 导入，不需要把 backend 装成包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
