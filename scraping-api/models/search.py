"""
検索モデル
検索リクエスト・結果のデータ構造
"""

from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel


class SearchRequest(BaseModel):
    """検索リクエスト（APIエンドポイント用）"""
    search_keyword: str
    target_count: int = 100
    queries: Optional[list[str]] = None
    gas_webhook_url: str
    slack_channel_id: str
    slack_thread_ts: str


class SearchJobResponse(BaseModel):
    """検索ジョブ開始レスポンス"""
    status: str
    job_id: str
    message: str


class JobStatusResponse(BaseModel):
    """ジョブステータスレスポンス"""
    id: str
    status: str
    progress: int
    message: str
    error: Optional[str] = None
    result_count: int = 0
    spreadsheet_url: Optional[str] = None


@dataclass
class CompanyData:
    """企業データ（検索結果）"""
    company_name: str
    url: str
    domain: str
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        """辞書に変換"""
        return {
            "company_name": self.company_name,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
        }


@dataclass
class SearchResult:
    """検索結果"""
    companies: list[CompanyData]
    total_found: int
    queries_used: int

    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "companies": [c.to_dict() for c in self.companies],
            "total_found": self.total_found,
            "queries_used": self.queries_used,
        }
