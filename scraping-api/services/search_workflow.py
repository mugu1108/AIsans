"""
検索ワークフローモジュール
検索→スクレイピング→保存→通知の一連の処理を実行
"""

import asyncio
import logging
from typing import Optional

from models.job import Job, JobStatus
from services.serper import SerperClient
from services.gas_client import GASClient
from services.slack_notifier import SlackNotifier
from services.job_manager import JobManager
from scraper import scrape_companies, is_excluded_domain, extract_domain

logger = logging.getLogger(__name__)


class SearchWorkflow:
    """検索ワークフロー実行クラス"""

    def __init__(
        self,
        serper_client: SerperClient,
        gas_client: GASClient,
        slack_notifier: SlackNotifier,
        job_manager: JobManager,
    ):
        self.serper = serper_client
        self.gas = gas_client
        self.slack = slack_notifier
        self.job_manager = job_manager

    async def execute(self, job: Job) -> None:
        """
        検索ワークフローを実行

        Args:
            job: 実行するジョブ
        """
        try:
            # ステップ1: 既存リスト取得
            job.update_status(JobStatus.SEARCHING, "既存リストを取得中...", 5)
            self.job_manager.update_job(job)

            existing_domains = await self.gas.get_existing_domains()
            logger.info(f"既存ドメイン: {len(existing_domains)}件")

            # ステップ2: Serper検索
            job.update_status(JobStatus.SEARCHING, "企業を検索中...", 15)
            self.job_manager.update_job(job)

            companies = await self.serper.search_companies(
                queries=job.queries,
                target_count=job.target_count,
                existing_domains=existing_domains,
            )
            logger.info(f"検索結果: {len(companies)}件")

            if not companies:
                job.set_error("検索結果が0件でした")
                self.job_manager.update_job(job)
                await self.slack.notify_error(
                    job.slack_channel_id,
                    job.slack_thread_ts,
                    "検索結果が0件でした。検索キーワードを変更してお試しください。"
                )
                return

            # ステップ3: スクレイピング
            job.update_status(JobStatus.SCRAPING, f"{len(companies)}件をスクレイピング中...", 35)
            self.job_manager.update_job(job)

            # スクレイピング用のデータ形式に変換
            companies_for_scrape = [
                {"company_name": c.company_name, "url": c.url}
                for c in companies
            ]

            scraped_results = await scrape_companies(companies_for_scrape)
            logger.info(f"スクレイピング完了: {len(scraped_results)}件")

            # 成功した結果をフィルタ
            successful_results = [
                r for r in scraped_results
                if r.contact_url or r.phone
            ]
            logger.info(f"有効な結果: {len(successful_results)}件")

            # ステップ4: GAS保存
            job.update_status(JobStatus.SAVING, "スプレッドシートに保存中...", 80)
            self.job_manager.update_job(job)

            # 保存用データ形式に変換
            companies_to_save = [
                {
                    "company_name": r.company_name,
                    "base_url": r.base_url,
                    "contact_url": r.contact_url,
                    "phone": r.phone,
                    "domain": r.domain,
                }
                for r in successful_results
            ]

            gas_response = await self.gas.save_results(
                companies=companies_to_save,
                search_keyword=job.search_keyword,
            )

            spreadsheet_url = gas_response.get("spreadsheet_url")
            logger.info(f"GAS保存完了: {spreadsheet_url}")

            # ステップ5: 完了
            job.set_completed(
                result_count=len(successful_results),
                spreadsheet_url=spreadsheet_url,
            )
            self.job_manager.update_job(job)

            # 完了通知
            await self.slack.notify_completion(
                job.slack_channel_id,
                job.slack_thread_ts,
                job.search_keyword,
                len(successful_results),
                spreadsheet_url,
            )

            logger.info(f"ジョブ完了: {job.id} ({len(successful_results)}件)")

        except Exception as e:
            logger.exception(f"ワークフローエラー: {e}")
            job.set_error(str(e))
            self.job_manager.update_job(job)

            await self.slack.notify_error(
                job.slack_channel_id,
                job.slack_thread_ts,
                f"処理中にエラーが発生しました: {str(e)}"
            )


async def run_workflow_async(
    job: Job,
    serper_api_key: str,
    slack_bot_token: str,
    gas_webhook_url: str,
    job_manager: JobManager,
) -> None:
    """
    バックグラウンドでワークフローを実行

    Args:
        job: 実行するジョブ
        serper_api_key: Serper APIキー
        slack_bot_token: Slack Bot Token
        gas_webhook_url: GAS Webhook URL
        job_manager: ジョブマネージャー
    """
    workflow = SearchWorkflow(
        serper_client=SerperClient(serper_api_key),
        gas_client=GASClient(gas_webhook_url),
        slack_notifier=SlackNotifier(slack_bot_token),
        job_manager=job_manager,
    )

    await workflow.execute(job)
