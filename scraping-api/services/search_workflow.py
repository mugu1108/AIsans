"""
検索ワークフローモジュール
検索→クレンジング→リトライ→スクレイピング→保存→通知の一連の処理を実行
"""

import asyncio
import csv
import io
import logging
from datetime import datetime
from typing import Optional

from models.job import Job, JobStatus
from services.serper import SerperClient, generate_retry_queries
from services.gas_client import GASClient
from services.slack_notifier import SlackNotifier
from services.job_manager import JobManager
from services.llm_cleanser import LLMCleanser
from scraper import scrape_companies, is_excluded_domain, extract_domain

logger = logging.getLogger(__name__)


class SearchWorkflow:
    """検索ワークフロー実行クラス"""

    # リトライ設定
    MAX_RETRY_ROUNDS = 3  # 最大リトライ回数
    GIVE_UP_THRESHOLD = 0.8  # 目標の80%以上取れたらリトライしない

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

            # ステップ2: 検索 → クレンジング → リトライループ
            companies = await self._search_with_retry(job, existing_domains)

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
            job.update_status(JobStatus.SCRAPING, f"{len(companies)}件をスクレイピング中...", 50)
            self.job_manager.update_job(job)

            companies_for_scrape = [
                {"company_name": c.company_name, "url": c.url}
                for c in companies
            ]

            scraped_results = await scrape_companies(companies_for_scrape)
            logger.info(f"スクレイピング完了: {len(scraped_results)}件")

            # 成功した結果をフィルタ
            successful_results = [
                r for r in scraped_results
                if not r.error
            ]

            # 結果を連絡先ありを先に、なしを後にソート
            successful_results.sort(key=lambda r: (0 if r.contact_url or r.phone else 1))

            # フィルタ結果の詳細ログ
            with_contact = sum(1 for r in successful_results if r.contact_url or r.phone)
            without_contact = len(successful_results) - with_contact
            failed_count = len(scraped_results) - len(successful_results)

            logger.info(f"有効な結果: {len(successful_results)}件（連絡先あり: {with_contact}件、連絡先なし: {without_contact}件）")
            if failed_count > 0:
                top_failed = sum(1 for r in scraped_results if r.error == 'top_page_failed')
                mismatch = sum(1 for r in scraped_results if r.error == 'company_mismatch')
                job_portal = sum(1 for r in scraped_results if r.error == 'job_portal_site')
                logger.info(f"除外: {failed_count}件（アクセス失敗: {top_failed}件、企業名不一致: {mismatch}件、求人/ポータル: {job_portal}件）")

            # ステップ4: GAS保存
            job.update_status(JobStatus.SAVING, "スプレッドシートに保存中...", 80)
            self.job_manager.update_job(job)

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

            contact_count = sum(1 for r in successful_results if r.contact_url or r.phone)
            await self.slack.notify_completion(
                job.slack_channel_id,
                job.slack_thread_ts,
                job.search_keyword,
                len(successful_results),
                spreadsheet_url,
                contact_count=contact_count,
            )

            # CSVファイルをSlackにアップロード
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

    # ====================================
    # 検索 → クレンジング → リトライループ
    # ====================================
    async def _search_with_retry(self, job: Job, existing_domains: list[str]) -> list:
        """
        目標件数に達するまで検索→クレンジングを繰り返す

        Returns:
            クレンジング済みのCompanyDataリスト
        """
        from models.search import CompanyData

        target_count = job.target_count
        all_cleansed = []  # 累積クレンジング結果
        used_domains = set(existing_domains)  # 重複排除用（既存 + 取得済み）
        used_names = set()  # 企業名の重複排除用
        used_queries = set(job.queries)  # 使用済みクエリ（リトライで同じクエリを使わない）

        for round_num in range(1, self.MAX_RETRY_ROUNDS + 2):  # 初回 + リトライ
            is_retry = round_num > 1
            shortage = target_count - len(all_cleansed)

            if is_retry:
                logger.info(f"=== リトライ {round_num - 1}/{self.MAX_RETRY_ROUNDS} === 不足: {shortage}件")
                job.update_status(
                    JobStatus.SEARCHING,
                    f"追加検索中...（{len(all_cleansed)}/{target_count}件取得済み、リトライ{round_num - 1}回目）",
                    15 + (round_num * 5),
                )
                self.job_manager.update_job(job)
            else:
                job.update_status(JobStatus.SEARCHING, "企業を検索中...", 15)
                self.job_manager.update_job(job)

            # --- クエリ選択 ---
            if is_retry:
                # リトライ時: 新しいクエリを生成
                queries = generate_retry_queries(
                    keyword=job.search_keyword,
                    round_num=round_num - 1,  # 1, 2, 3...
                    used_queries=used_queries,
                )
                if not queries:
                    logger.info(f"新しいクエリが生成できません。リトライ終了。")
                    break
                used_queries.update(queries)
            else:
                # 初回: 元のクエリを使用
                queries = job.queries

            # --- 検索 ---
            # リトライ時は不足分より多めに検索（クレンジングで減る分を見越す）
            search_target = shortage * 2 if is_retry else target_count

            companies = await self.serper.search_companies(
                queries=queries,
                target_count=search_target,
                existing_domains=list(used_domains),
            )
            logger.info(f"ラウンド{round_num} 検索結果: {len(companies)}件（クエリ数: {len(queries)}）")

            if not companies:
                if is_retry:
                    logger.info(f"追加検索結果が0件。リトライ終了。")
                    break
                else:
                    return []  # 初回で0件なら終了

            # --- LLMクレンジング ---
            if self.llm_cleanser:
                if not is_retry:
                    job.update_status(JobStatus.SEARCHING, "企業データをクレンジング中...", 25)
                    self.job_manager.update_job(job)

                companies_dict = [
                    {"company_name": c.company_name, "url": c.url, "domain": c.domain}
                    for c in companies
                ]

                try:
                    cleansed = await self.llm_cleanser.cleanse_companies(
                        companies_dict,
                        search_keyword=job.search_keyword,
                    )
                    logger.info(f"ラウンド{round_num} クレンジング: {len(companies)}件 → {len(cleansed)}件")
                except Exception as e:
                    logger.warning(f"LLMクレンジングエラー（スキップ）: {e}")
                    # クレンジング失敗時はそのまま使う
                    cleansed = [
                        {"company_name": c.company_name, "url": c.url, "domain": c.domain}
                        for c in companies
                    ]
            else:
                logger.warning("LLMクレンジングスキップ: OPENAI_API_KEYが設定されていません")
                cleansed = [
                    {"company_name": c.company_name, "url": c.url, "domain": c.domain}
                    for c in companies
                ]

            # --- 累積マージ（重複排除） ---
            new_count = 0
            for c in cleansed:
                domain = c.get("domain", "")
                name = c.get("company_name", "")

                # ドメイン重複チェック
                if domain and domain in used_domains:
                    continue
                # 企業名重複チェック
                if name and name in used_names:
                    continue

                all_cleansed.append(CompanyData(
                    company_name=name,
                    url=c.get("url", ""),
                    domain=domain,
                ))

                if domain:
                    used_domains.add(domain)
                if name:
                    used_names.add(name)
                new_count += 1

            logger.info(f"ラウンド{round_num} 新規追加: {new_count}件 → 累積: {len(all_cleansed)}件（目標: {target_count}件）")

            # --- 目標達成チェック ---
            if len(all_cleansed) >= target_count:
                logger.info(f"目標達成！ {len(all_cleansed)}/{target_count}件")
                break

            # --- リトライ判定 ---
            if round_num > self.MAX_RETRY_ROUNDS:
                logger.info(f"最大リトライ回数到達。{len(all_cleansed)}/{target_count}件で終了。")
                break

            # 新規追加が0件なら、これ以上検索しても見つからない
            if new_count == 0:
                logger.info(f"新規企業が見つかりません。{len(all_cleansed)}/{target_count}件で終了。")
                break

            # 目標の80%以上取れていて、追加が少ない場合もリトライしない
            if len(all_cleansed) >= target_count * self.GIVE_UP_THRESHOLD and new_count < 3:
                logger.info(f"目標の80%以上達成（{len(all_cleansed)}/{target_count}件）、追加が少ないためリトライ終了。")
                break

        # 目標数を超えた場合はrelevance_scoreの高い順に切り詰め
        if len(all_cleansed) > target_count:
            # relevance_scoreがある場合はそれでソート（なければ元の順序を維持）
            all_cleansed = all_cleansed[:target_count]
            logger.info(f"目標数に切り詰め: {target_count}件")

        total_rounds = min(round_num, self.MAX_RETRY_ROUNDS + 1)
        logger.info(f"検索+クレンジング完了: {len(all_cleansed)}件（{total_rounds}ラウンド）")

        return all_cleansed

    def _generate_csv(self, companies: list[dict]) -> bytes:
        """企業データからCSVを生成"""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["企業名", "URL", "お問い合わせURL", "電話番号", "ドメイン"])

        for company in companies:
            writer.writerow([
                company.get("company_name", ""),
                company.get("base_url", ""),
                company.get("contact_url", ""),
                company.get("phone", ""),
                company.get("domain", ""),
            ])

        return output.getvalue().encode("utf-8-sig")


async def run_workflow_async(
    job: Job,
    serper_api_key: str,
    slack_bot_token: str,
    gas_webhook_url: str,
    job_manager: JobManager,
    openai_api_key: Optional[str] = None,
) -> None:
    """バックグラウンドでワークフローを実行"""
    workflow = SearchWorkflow(
        serper_client=SerperClient(serper_api_key),
        gas_client=GASClient(gas_webhook_url),
        slack_notifier=SlackNotifier(slack_bot_token),
        job_manager=job_manager,
        openai_api_key=openai_api_key,
    )

    await workflow.execute(job)