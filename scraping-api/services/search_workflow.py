"""
検索ワークフローモジュール
検索→スクレイピング→保存→通知の一連の処理を実行
"""

import asyncio
import csv
import io
import logging
from datetime import datetime
from typing import Optional

from models.job import Job, JobStatus
from services.serper import SerperClient
from services.gas_client import GASClient
from services.slack_notifier import SlackNotifier
from services.job_manager import JobManager
from services.llm_cleanser import LLMCleanser
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
        openai_api_key: Optional[str] = None,
    ):
        self.serper = serper_client
        self.gas = gas_client
        self.slack = slack_notifier
        self.job_manager = job_manager
        self.llm_cleanser = LLMCleanser(openai_api_key) if openai_api_key else None

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

            # ステップ2.5: LLMクレンジング（企業名正規化＋非企業サイト除外）
            if self.llm_cleanser:
                job.update_status(JobStatus.SEARCHING, "企業データをクレンジング中...", 25)
                self.job_manager.update_job(job)

                companies_dict = [
                    {"company_name": c.company_name, "url": c.url, "domain": c.domain}
                    for c in companies
                ]

                try:
                    # Dify仕様準拠: 企業HP以外を除外し、企業名を正規化
                    cleansed = await self.llm_cleanser.cleanse_companies(
                        companies_dict,
                        search_keyword=job.search_keyword,
                    )
                    original_count = len(companies)
                    # クレンジング結果でcompaniesを更新（有効な企業のみ残る）
                    from models.search import CompanyData
                    companies = [
                        CompanyData(
                            company_name=c["company_name"],
                            url=c["url"],
                            domain=c["domain"],
                        )
                        for c in cleansed
                    ]
                    excluded_count = original_count - len(companies)
                    logger.info(f"LLMクレンジング完了: {original_count}件 → {len(companies)}件（{excluded_count}件除外）")
                except Exception as e:
                    logger.warning(f"LLMクレンジングエラー（スキップ）: {e}")

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
            # - エラーがない企業はすべて含める（連絡先がなくても営業担当者が手動で探せる）
            # - top_page_failed と company_mismatch はサイトにアクセスできないか別の企業なので除外
            successful_results = [
                r for r in scraped_results
                if not r.error  # エラーなし = 正しい企業サイトにアクセス成功
            ]

            # 結果を連絡先ありを先に、なしを後にソート
            successful_results.sort(key=lambda r: (0 if r.contact_url or r.phone else 1))

            # フィルタ結果の詳細ログ
            with_contact = sum(1 for r in successful_results if r.contact_url or r.phone)
            without_contact = len(successful_results) - with_contact
            failed_count = len(scraped_results) - len(successful_results)

            logger.info(f"有効な結果: {len(successful_results)}件（連絡先あり: {with_contact}件、連絡先なし: {without_contact}件）")
            if failed_count > 0:
                # 失敗した企業の内訳
                top_failed = sum(1 for r in scraped_results if r.error == 'top_page_failed')
                mismatch = sum(1 for r in scraped_results if r.error == 'company_mismatch')
                job_portal = sum(1 for r in scraped_results if r.error == 'job_portal_site')
                logger.info(f"除外: {failed_count}件（アクセス失敗: {top_failed}件、企業名不一致: {mismatch}件、求人/ポータル: {job_portal}件）")

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

            # 完了通知（連絡先ありの件数も渡す）
            contact_count = sum(1 for r in successful_results if r.contact_url or r.phone)
            await self.slack.notify_completion(
                job.slack_channel_id,
                job.slack_thread_ts,
                job.search_keyword,
                len(successful_results),
                spreadsheet_url,
                contact_count=contact_count,
            )

            # CSVファイルを生成してSlackにアップロード
            if successful_results:
                csv_content = self._generate_csv(companies_to_save)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"sales_list_{timestamp}.csv"

                await self.slack.upload_file(
                    job.slack_channel_id,
                    csv_content,
                    filename,
                    title=f"営業リスト - {job.search_keyword}",
                    thread_ts=job.slack_thread_ts,
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

    def _generate_csv(self, companies: list[dict]) -> bytes:
        """
        企業データからCSVを生成

        Args:
            companies: 企業データのリスト

        Returns:
            CSVデータ（バイト）
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # ヘッダー
        writer.writerow(["企業名", "URL", "お問い合わせURL", "電話番号", "ドメイン"])

        # データ行
        for company in companies:
            writer.writerow([
                company.get("company_name", ""),
                company.get("base_url", ""),
                company.get("contact_url", ""),
                company.get("phone", ""),
                company.get("domain", ""),
            ])

        return output.getvalue().encode("utf-8-sig")  # BOM付きUTF-8（Excel対応）


async def run_workflow_async(
    job: Job,
    serper_api_key: str,
    slack_bot_token: str,
    gas_webhook_url: str,
    job_manager: JobManager,
    openai_api_key: Optional[str] = None,
) -> None:
    """
    バックグラウンドでワークフローを実行

    Args:
        job: 実行するジョブ
        serper_api_key: Serper APIキー
        slack_bot_token: Slack Bot Token
        gas_webhook_url: GAS Webhook URL
        job_manager: ジョブマネージャー
        openai_api_key: OpenAI APIキー（企業名クレンジング用、オプション）
    """
    workflow = SearchWorkflow(
        serper_client=SerperClient(serper_api_key),
        gas_client=GASClient(gas_webhook_url),
        slack_notifier=SlackNotifier(slack_bot_token),
        job_manager=job_manager,
        openai_api_key=openai_api_key,
    )

    await workflow.execute(job)
