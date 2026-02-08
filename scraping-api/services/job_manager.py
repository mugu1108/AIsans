"""
ジョブ管理モジュール
非同期ジョブの作成・管理・状態取得
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class JobManager:
    """ジョブマネージャー（インメモリ）"""

    def __init__(self, job_ttl_hours: int = 24):
        """
        Args:
            job_ttl_hours: ジョブの保持時間（時間）
        """
        self._jobs: dict[str, Job] = {}
        self._job_ttl = timedelta(hours=job_ttl_hours)

    def create_job(
        self,
        search_keyword: str,
        target_count: int,
        queries: list[str],
        gas_webhook_url: str,
        slack_channel_id: str,
        slack_thread_ts: str,
    ) -> Job:
        """新しいジョブを作成"""
        self._cleanup_old_jobs()

        job = Job.create(
            search_keyword=search_keyword,
            target_count=target_count,
            queries=queries,
            gas_webhook_url=gas_webhook_url,
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
        )
        self._jobs[job.id] = job

        logger.info(f"ジョブ作成: {job.id} ({search_keyword}, {target_count}件)")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """ジョブを取得"""
        return self._jobs.get(job_id)

    def update_job(self, job: Job) -> None:
        """ジョブを更新"""
        if job.id in self._jobs:
            self._jobs[job.id] = job

    def list_jobs(self, limit: int = 100) -> list[Job]:
        """ジョブ一覧を取得"""
        jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def delete_job(self, job_id: str) -> bool:
        """ジョブを削除"""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def _cleanup_old_jobs(self) -> None:
        """古いジョブを削除"""
        now = datetime.now()
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.created_at > self._job_ttl
        ]
        for job_id in expired_ids:
            del self._jobs[job_id]
            logger.debug(f"期限切れジョブ削除: {job_id}")


# グローバルインスタンス
_job_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """ジョブマネージャーを取得"""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
