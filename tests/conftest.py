"""pytest 全局配置"""
import os
import sys

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试环境：禁用 LangSmith、离线模式
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["AUTO_APPROVE_SEARCH"] = "true"