import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VIX_OPTION_REPORT_PATH = REPO_ROOT / "runtime" / "reports" / "vix_option_analysis" / "report.json"


class ResearchService:
    def get_vix_option_analysis(self) -> dict:
        if not VIX_OPTION_REPORT_PATH.exists():
            raise FileNotFoundError("VIX期权研究报告尚未生成")
        try:
            payload = json.loads(VIX_OPTION_REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("VIX期权研究报告读取失败") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("index_summaries"), list):
            raise RuntimeError("VIX期权研究报告格式无效")
        return payload
