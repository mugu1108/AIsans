"""
スクレイピングAPI
FastAPI + httpx + BeautifulSoup4

POST /scrape - 企業リストをスクレイピング
GET /health - ヘルスチェック
"""

import os
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from scraper import scrape_companies, is_excluded_domain, extract_domain

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
    description="営業リスト作成用スクレイピングAPI",
    version="1.0.0"
)


# ====================================
# リクエスト/レスポンスモデル
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


# ====================================
# エンドポイント
# ====================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェック"""
    return HealthResponse(
        status="ok",
        message="Scraping API is running"
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
