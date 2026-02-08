"""
ジョブモデル
非同期ジョブの状態管理
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid


class JobStatus(str, Enum):
    """ジョブステータス"""
    PENDING = "pending"
    SEARCHING = "searching"
    SCRAPING = "scraping"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """検索ジョブ"""

    id: str
    search_keyword: str
    target_count: int
    queries: list[str]
    gas_webhook_url: str
    slack_channel_id: str
    slack_thread_ts: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    result_count: int = 0
    spreadsheet_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        search_keyword: str,
        target_count: int,
        queries: list[str],
        gas_webhook_url: str,
        slack_channel_id: str,
        slack_thread_ts: str,
    ) -> "Job":
        """新しいジョブを作成"""
        return cls(
            id=str(uuid.uuid4()),
            search_keyword=search_keyword,
            target_count=target_count,
            queries=queries,
            gas_webhook_url=gas_webhook_url,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
        )

    def update_status(self, status: JobStatus, message: str = "", progress: int = -1) -> None:
        """ステータスを更新"""
        self.status = status
        if message:
            self.message = message
        if progress >= 0:
            self.progress = progress
        self.updated_at = datetime.now()

    def set_error(self, error: str) -> None:
        """エラーを設定"""
        self.status = JobStatus.FAILED
        self.error = error
        self.updated_at = datetime.now()

    def set_completed(self, result_count: int, spreadsheet_url: Optional[str] = None) -> None:
        """完了を設定"""
        self.status = JobStatus.COMPLETED
        self.result_count = result_count
        self.spreadsheet_url = spreadsheet_url
        self.progress = 100
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """辞書に変換"""
        return {
            "id": self.id,
            "search_keyword": self.search_keyword,
            "target_count": self.target_count,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result_count": self.result_count,
            "spreadsheet_url": self.spreadsheet_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
