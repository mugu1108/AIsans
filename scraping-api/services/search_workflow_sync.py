"""
同期版検索ワークフロー（Difyワークフロー用）

search_workflow.py と同等の処理をSlack通知なしで実行し、
結果を直接返す。

v2対応: QueryPool方式 + 動的リトライ + スクレイピング後クレンジング
"""

import logging
from typing import Optional

from models.search import CompanyData
from services.serper import SerperClient, generate_diverse_queries, generate_retry_queries
from services.gas_client import GASClient
from services.llm_cleanser import LLMCleanser, normalize_company_name, is_invalid_company_name
from scraper import scrape_companies

logger = logging.getLogger(__name__)


# 定数
GIVE_UP_THRESHOLD = 0.8    # 目標の80%以上で打ち切り
SCRAPING_BUFFER = 1.15     # スクレイピング脱落分15%上乗せ


async def run_sync_workflow(
    search_keyword: str,
    target_count: int,
    serper_api_key: str,
    gas_webhook_url: str,
    openai_api_key: Optional[str] = None,
    queries: Optional[list[str]] = None,
) -> dict:
    """
    同期版ワークフローを実行

    Args:
        search_keyword: 検索キーワード
        target_count: 目標件数
        serper_api_key: Serper APIキー
        gas_webhook_url: GAS Webhook URL
        openai_api_key: OpenAI APIキー（任意）
        queries: カスタムクエリリスト（任意）

    Returns:
        結果辞書 {result_count, search_count, scrape_count, spreadsheet_url, results, message}
    """
    serper_client = SerperClient(serper_api_key)
    gas_client = GASClient(gas_webhook_url)
    llm_cleanser = LLMCleanser(openai_api_key) if openai_api_key else None

    # STEP 1: 既存ドメイン取得
    existing_domains = await gas_client.get_existing_domains()
    logger.info(f"既存ドメイン: {len(existing_domains)}件")

    # STEP 2: 検索 → クレンジング → リトライループ
    companies = await _search_with_retry(
        search_keyword=search_keyword,
        target_count=target_count,
        serper_client=serper_client,
        llm_cleanser=llm_cleanser,
        existing_domains=existing_domains,
        initial_queries=queries,
    )

    search_count = len(companies)

    if not companies:
        return {
            "result_count": 0,
            "search_count": 0,
            "scrape_count": 0,
            "spreadsheet_url": "",
            "results": [],
            "message": "検索結果が0件でした。キーワードを変更してお試しください。",
        }

    # STEP 3: スクレイピング
    logger.info(f"スクレイピング開始: {len(companies)}件")
    companies_for_scrape = [
        {"company_name": c.company_name, "url": c.url}
        for c in companies
    ]

    scraped_results = await scrape_companies(companies_for_scrape)
    logger.info(f"スクレイピング完了: {len(scraped_results)}件")

    successful_results = [r for r in scraped_results if not r.error]
    successful_results.sort(key=lambda r: (0 if r.contact_url or r.phone else 1))

    with_contact = sum(1 for r in successful_results if r.contact_url or r.phone)
    logger.info(f"有効な結果: {len(successful_results)}件（連絡先あり: {with_contact}件）")

    # 目標数を超えた場合は切り詰め
    if len(successful_results) > target_count:
        successful_results = successful_results[:target_count]
        logger.info(f"目標数に切り詰め: {target_count}件")

    # STEP 3.5: スクレイピング後の企業名正規化 + 無効企業名の除外
    cleaned_results = []
    post_scrape_excluded = 0
    for r in successful_results:
        original_name = r.company_name
        r.company_name = normalize_company_name(r.company_name)

        if r.company_name != original_name:
            logger.debug(f"スクレイピング後正規化: {original_name} → {r.company_name}")

        if is_invalid_company_name(r.company_name):
            logger.info(f"スクレイピング後除外: {original_name} → {r.company_name}")
            post_scrape_excluded += 1
            continue

        cleaned_results.append(r)

    if post_scrape_excluded > 0:
        logger.info(f"スクレイピング後クレンジング: {len(successful_results)}件 → {len(cleaned_results)}件")

    successful_results = cleaned_results

    # STEP 4: GAS保存
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

    spreadsheet_url = ""
    if companies_to_save:
        try:
            gas_response = await gas_client.save_results(
                companies=companies_to_save,
                search_keyword=search_keyword,
            )
            spreadsheet_url = gas_response.get("spreadsheet_url", "")
            logger.info(f"GAS保存完了: {spreadsheet_url}")
        except Exception as e:
            logger.error(f"GAS保存エラー（結果は返却）: {e}")

    # 結果メッセージ生成
    contact_count = sum(1 for r in successful_results if r.contact_url or r.phone)
    message = f"検索完了: {len(successful_results)}件の企業情報を取得しました（連絡先あり: {contact_count}件）"
    if spreadsheet_url:
        message += f"\nスプレッドシート: {spreadsheet_url}"

    return {
        "result_count": len(successful_results),
        "search_count": search_count,
        "scrape_count": len(scraped_results),
        "spreadsheet_url": spreadsheet_url,
        "results": companies_to_save,
        "message": message,
    }


async def _search_with_retry(
    search_keyword: str,
    target_count: int,
    serper_client: SerperClient,
    llm_cleanser: Optional[LLMCleanser],
    existing_domains: list[str],
    initial_queries: Optional[list[str]] = None,
) -> list[CompanyData]:
    """
    目標件数に達するまで検索→クレンジングを繰り返す。
    リトライ時は業種・地域に応じた新しいクエリを生成する。
    """
    # スクレイピング脱落分を見越して多めに取得
    buffered_target = int(target_count * SCRAPING_BUFFER)
    logger.info(f"検索目標: {target_count}件 → バッファ込み{buffered_target}件")

    # リトライ回数を制限（クレジット消費を抑える）
    max_retries = min(5, max(3, target_count // 50))
    logger.info(f"最大リトライ回数: {max_retries}回")

    all_cleansed: list[CompanyData] = []
    used_domains = set(existing_domains)
    used_names: set[str] = set()
    used_queries: set[str] = set()

    for round_num in range(1, max_retries + 2):
        is_retry = round_num > 1
        shortage = buffered_target - len(all_cleansed)

        # --- クエリ生成 ---
        if is_retry:
            queries = generate_retry_queries(
                keyword=search_keyword,
                round_num=round_num - 1,
                used_queries=used_queries,
            )
            if not queries:
                logger.info("新しいクエリが生成できません。リトライ終了。")
                break

            logger.info(f"=== リトライ {round_num - 1}/{max_retries} === "
                       f"不足: {shortage}件, 新クエリ: {len(queries)}個")
        else:
            queries = initial_queries or generate_diverse_queries(search_keyword)
            logger.info(f"初回検索クエリ: {len(queries)}個")

        used_queries.update(queries)

        # --- 検索 ---
        search_target = shortage * 2 if is_retry else buffered_target

        companies = await serper_client.search_companies(
            queries=queries,
            target_count=search_target,
            existing_domains=used_domains,
        )
        logger.info(f"ラウンド{round_num} 検索結果: {len(companies)}件")

        if not companies:
            if is_retry:
                logger.info("追加検索結果が0件。リトライ終了。")
                break
            else:
                return []

        # --- LLMクレンジング ---
        if llm_cleanser:
            companies_dict = [
                {"company_name": c.company_name, "url": c.url, "domain": c.domain}
                for c in companies
            ]

            try:
                cleansed = await llm_cleanser.cleanse_companies(
                    companies_dict,
                    search_keyword=search_keyword,
                )
                logger.info(f"ラウンド{round_num} クレンジング: {len(companies)}件 → {len(cleansed)}件")
            except Exception as e:
                logger.warning(f"LLMクレンジングエラー（スキップ）: {e}")
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

            if domain and domain in used_domains:
                continue
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

        logger.info(f"ラウンド{round_num} 新規追加: {new_count}件 → "
                    f"累積: {len(all_cleansed)}件（目標: {buffered_target}件）")

        # --- 目標達成チェック ---
        if len(all_cleansed) >= buffered_target:
            logger.info(f"目標達成！ {len(all_cleansed)}/{buffered_target}件")
            break

        # --- リトライ打ち切り判定 ---
        if round_num > max_retries:
            logger.info(f"最大リトライ回数到達。{len(all_cleansed)}/{buffered_target}件で終了。")
            break

        if new_count == 0:
            logger.info(f"新規企業が見つかりません。{len(all_cleansed)}/{buffered_target}件で終了。")
            break

        if len(all_cleansed) >= buffered_target * GIVE_UP_THRESHOLD and new_count < 3:
            logger.info(f"目標の80%以上達成、追加が少ないためリトライ終了。")
            break

    # 目標数を超えた場合は切り詰め
    if len(all_cleansed) > buffered_target:
        all_cleansed = all_cleansed[:buffered_target]
        logger.info(f"バッファ目標に切り詰め: {buffered_target}件")

    logger.info(f"検索+クレンジング完了: {len(all_cleansed)}件（{round_num}ラウンド）")
    return all_cleansed
