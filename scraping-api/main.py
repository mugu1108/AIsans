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

    検索→クレンジング→リトライ→スクレイピング→GAS保存を一括で実行し、
    完了後に結果を返す。

    v2対応: QueryPool方式 + 動的リトライ + スクレイピング後クレンジング
    """
    settings = get_settings()

    if not settings.serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY が未設定です")
    if not settings.gas_webhook_url:
        raise HTTPException(status_code=500, detail="GAS_WEBHOOK_URL が未設定です")

    max_count = getattr(settings, 'max_target_count', 500)
    if request.target_count > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"target_count は {max_count} 以下にしてください"
        )

    logger.info(f"=== 同期検索開始: {request.search_keyword} ({request.target_count}件) ===")

    # SearchWorkflowの同期版ロジックを実行
    from services.search_workflow_sync import run_sync_workflow

    try:
        result = await run_sync_workflow(
            search_keyword=request.search_keyword,
            target_count=request.target_count,
            serper_api_key=settings.serper_api_key,
            gas_webhook_url=settings.gas_webhook_url,
            openai_api_key=settings.openai_api_key,
            queries=request.queries,
        )

        logger.info(f"=== 同期検索完了: {result['result_count']}件 ===")

        return SearchSyncResponse(
            status="success",
            search_keyword=request.search_keyword,
            target_count=request.target_count,
            result_count=result["result_count"],
            search_count=result["search_count"],
            scrape_count=result["scrape_count"],
            success_count=result["result_count"],
            spreadsheet_url=result["spreadsheet_url"],
            results=result["results"],
            message=result["message"],
        )

    except Exception as e:
        logger.exception(f"同期検索エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
