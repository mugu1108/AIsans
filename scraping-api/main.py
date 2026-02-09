"""
スクレイピング & 検索 API
FastAPI + httpx + BeautifulSoup4

POST /scrape - 企業リストをスクレイピング
POST /search - 非同期検索ジョブを開始（Slack通知付き）
POST /search_sync - 同期検索（Difyワークフロー用）
GET /jobs/{job_id} - ジョブステータス確認
GET /health - ヘルスチェック
"""

import os
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from scraper import scrape_companies, is_excluded_domain, extract_domain
from config.settings import get_settings
from models.search import SearchRequest, SearchJobResponse, JobStatusResponse
from services.serper import SerperClient, generate_diverse_queries
from services.gas_client import GASClient
from services.job_manager import get_job_manager
from services.search_workflow import run_workflow_async

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# httpxの警告を抑制（SSL検証無効時）
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# FastAPIアプリ
app = FastAPI(
    title="AI-Shine Scraping API",
    description="営業リスト作成用スクレイピング & 検索API",
    version="2.0.0"
)


# ====================================
# リクエスト/レスポンスモデル（既存）
# ====================================

class CompanyInput(BaseModel):
    """入力: 企業情報"""
    company_name: str
    url: str


class ScrapeRequest(BaseModel):
    """リクエスト: スクレイピング対象"""
    companies: list[CompanyInput]


class CompanyResult(BaseModel):
    """結果: 企業ごとのスクレイピング結果"""
    company_name: str
    base_url: str
    contact_url: str
    phone: str
    domain: str
    error: str


class ScrapeResponse(BaseModel):
    """レスポンス: スクレイピング結果"""
    status: str
    results: list[CompanyResult]
    total: int
    scraped: int
    success_count: int


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""
    status: str
    message: str
    env_status: Optional[dict] = None


class SearchSyncRequest(BaseModel):
    """同期検索リクエスト（Difyワークフロー用）"""
    search_keyword: str
    target_count: int = 30
    queries: Optional[list[str]] = None


class SearchSyncResponse(BaseModel):
    """同期検索レスポンス"""
    status: str
    search_keyword: str
    target_count: int
    result_count: int
    search_count: int
    scrape_count: int
    success_count: int
    spreadsheet_url: str
    results: list[dict]
    message: str


# ====================================
# エンドポイント
# ====================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェック"""
    settings = get_settings()
    missing = settings.validate()

    return HealthResponse(
        status="ok" if not missing else "warning",
        message="Scraping API is running" if not missing else f"Missing env: {', '.join(missing)}",
        env_status={
            "SERPER_API_KEY": "set" if settings.serper_api_key else "missing",
            "SLACK_BOT_TOKEN": "set" if settings.slack_bot_token else "missing",
            "GAS_WEBHOOK_URL": "set" if settings.gas_webhook_url else "missing",
        }
    )


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    """
    企業リストをスクレイピング

    - 各企業のお問い合わせURL・電話番号を取得
    - 企業名一致チェックを実施
    - 並列処理で高速化
    """
    if not request.companies:
        raise HTTPException(status_code=400, detail="companies配列が必要です")

    logger.info(f"スクレイピング開始: {len(request.companies)}件")

    # 除外ドメインをフィルタリング
    valid_companies = []
    for company in request.companies:
        domain = extract_domain(company.url)
        if is_excluded_domain(domain):
            logger.info(f"除外ドメインスキップ: {company.company_name} ({domain})")
            continue
        valid_companies.append({
            'company_name': company.company_name,
            'url': company.url
        })

    logger.info(f"有効企業数: {len(valid_companies)}件（除外: {len(request.companies) - len(valid_companies)}件）")

    # スクレイピング実行
    results = await scrape_companies(valid_companies)

    # 結果を整形
    result_list = [
        CompanyResult(
            company_name=r.company_name,
            base_url=r.base_url,
            contact_url=r.contact_url,
            phone=r.phone,
            domain=r.domain,
            error=r.error
        )
        for r in results
    ]

    # 成功件数カウント（contact_urlまたはphoneが取れた件数）
    success_count = sum(1 for r in results if r.contact_url or r.phone)

    logger.info(f"スクレイピング完了: {len(results)}件処理, {success_count}件成功")

    return ScrapeResponse(
        status="success",
        results=result_list,
        total=len(request.companies),
        scraped=len(results),
        success_count=success_count
    )


@app.post("/search_sync", response_model=SearchSyncResponse)
async def search_sync(request: SearchSyncRequest):
    """
    同期版の検索エンドポイント（Difyワークフロー用）

    検索→スクレイピング→GAS保存を一括で実行し、
    完了後に結果を返す。
    """
    settings = get_settings()

    if not settings.serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY が未設定です")
    if not settings.gas_webhook_url:
        raise HTTPException(status_code=500, detail="GAS_WEBHOOK_URL が未設定です")

    max_count = getattr(settings, 'max_target_count', 200)
    if request.target_count > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"target_count は {max_count} 以下にしてください"
        )

    logger.info(f"=== 同期検索開始: {request.search_keyword} ({request.target_count}件) ===")

    serper_client = SerperClient(settings.serper_api_key)
    gas_client = GASClient(settings.gas_webhook_url)

    # STEP 1: 既存ドメイン取得
    existing_domains = await gas_client.get_existing_domains()
    logger.info(f"既存ドメイン: {len(existing_domains)}件")

    # STEP 2: 検索クエリ生成
    queries = request.queries or generate_diverse_queries(request.search_keyword)
    logger.info(f"検索クエリ {len(queries)}件")

    # STEP 3: Serper検索
    companies = await serper_client.search_companies(
        queries=queries,
        target_count=request.target_count,
        existing_domains=existing_domains,
    )
    logger.info(f"検索結果: {len(companies)}件")

    if not companies:
        return SearchSyncResponse(
            status="success",
            search_keyword=request.search_keyword,
            target_count=request.target_count,
            result_count=0, search_count=0, scrape_count=0, success_count=0,
            spreadsheet_url="", results=[],
            message="検索結果が0件でした。キーワードを変更してお試しください。",
        )

    # STEP 3.5: LLMクレンジング（企業名正規化＋非企業サイト除外）
    if settings.openai_api_key:
        logger.info(f"LLMクレンジング開始: {len(companies)}件")
        from services.llm_cleanser import LLMCleanser
        from models.search import CompanyData
        cleanser = LLMCleanser(settings.openai_api_key)
        companies_dict = [
            {"company_name": c.company_name, "url": c.url, "domain": c.domain}
            for c in companies
        ]
        try:
            # Dify仕様準拠: 企業HP以外を除外し、企業名を正規化
            cleansed = await cleanser.cleanse_companies(
                companies_dict,
                search_keyword=request.search_keyword,
            )
            original_count = len(companies)
            # クレンジング結果でcompaniesを更新（有効な企業のみ残る）
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
    else:
        logger.warning("LLMクレンジングスキップ: OPENAI_API_KEYが設定されていません")

    # STEP 4: スクレイピング
    companies_for_scrape = [
        {"company_name": c.company_name, "url": c.url}
        for c in companies
    ]
    scraped_results = await scrape_companies(companies_for_scrape)
    successful_results = [r for r in scraped_results if r.contact_url or r.phone]
    logger.info(f"スクレイピング完了: {len(scraped_results)}件中 {len(successful_results)}件成功")

    # STEP 5: GAS保存
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
                search_keyword=request.search_keyword,
            )
            spreadsheet_url = gas_response.get("spreadsheet_url", "")
        except Exception as e:
            logger.error(f"GAS保存エラー（結果は返却）: {e}")

    message = f"検索完了: {len(successful_results)}件の企業情報を取得しました。"
    if spreadsheet_url:
        message += f"\nスプレッドシート: {spreadsheet_url}"

    logger.info(f"=== 同期検索完了: {len(successful_results)}件 ===")

    return SearchSyncResponse(
        status="success",
        search_keyword=request.search_keyword,
        target_count=request.target_count,
        result_count=len(successful_results),
        search_count=len(companies),
        scrape_count=len(scraped_results),
        success_count=len(successful_results),
        spreadsheet_url=spreadsheet_url,
        results=companies_to_save,
        message=message,
    )


@app.post("/search", response_model=SearchJobResponse)
async def start_search(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    非同期検索ジョブを開始

    - Serperで企業URLを検索
    - スクレイピングでコンタクト情報を取得
    - GASでスプレッドシートに保存
    - Slackに結果を通知
    """
    settings = get_settings()
    missing = settings.validate()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"環境変数が設定されていません: {', '.join(missing)}"
        )

    # 件数制限チェック
    if request.target_count > settings.max_target_count:
        raise HTTPException(
            status_code=400,
            detail=f"target_countは{settings.max_target_count}以下にしてください"
        )

    # クエリ生成（指定がなければ自動生成）
    queries = request.queries or generate_diverse_queries(request.search_keyword)

    # ジョブ作成
    job_manager = get_job_manager()
    job = job_manager.create_job(
        search_keyword=request.search_keyword,
        target_count=request.target_count,
        queries=queries,
        gas_webhook_url=request.gas_webhook_url,
        slack_channel_id=request.slack_channel_id,
        slack_thread_ts=request.slack_thread_ts,
    )

    logger.info(f"検索ジョブ開始: {job.id} ({request.search_keyword}, {request.target_count}件)")

    # バックグラウンドでワークフロー実行
    background_tasks.add_task(
        run_workflow_async,
        job=job,
        serper_api_key=settings.serper_api_key,
        slack_bot_token=settings.slack_bot_token,
        gas_webhook_url=settings.gas_webhook_url,
        job_manager=job_manager,
        openai_api_key=settings.openai_api_key,
    )

    return SearchJobResponse(
        status="accepted",
        job_id=job.id,
        message=f"検索ジョブを開始しました（{len(queries)}クエリ）"
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """ジョブのステータスを取得"""
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    return JobStatusResponse(
        id=job.id,
        status=job.status.value,
        progress=job.progress,
        message=job.message,
        error=job.error,
        result_count=job.result_count,
        spreadsheet_url=job.spreadsheet_url,
    )


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """ジョブの結果を取得"""
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    return job.to_dict()


# ====================================
# メイン
# ====================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
