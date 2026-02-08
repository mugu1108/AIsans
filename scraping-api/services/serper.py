"""
Serper.dev 検索モジュール
Google検索APIを使用して企業URLを取得
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from models.search import CompanyData

logger = logging.getLogger(__name__)


# クエリ生成パターン
QUERY_PATTERNS = [
    "{keyword} 企業一覧",
    "{keyword} 会社",
    "{keyword} 株式会社",
    "{keyword} ランキング",
    "{keyword} おすすめ",
    "{keyword} 比較",
    "{keyword} co.jp",
]

# 除外ドメイン（scraper.pyと共通）
EXCLUDE_DOMAINS = [
    # 求人サイト
    'indeed.com', 'indeed.jp', 'mynavi.jp', 'rikunabi.com', 'doda.jp',
    'en-japan.com', 'baitoru.com', 'careerconnection.jp', 'jobchange.jp', 'hatarako.net',
    # ニュース・メディア
    'yahoo.co.jp', 'news.yahoo.co.jp', 'nikkei.com', 'asahi.com', 'yomiuri.co.jp',
    'mainichi.jp', 'sankei.com',
    # SNS
    'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
    'youtube.com', 'tiktok.com', 'linkedin.com',
    # 百科事典
    'wikipedia.org', 'ja.wikipedia.org',
    # EC・大手
    'google.com', 'amazon.co.jp', 'rakuten.co.jp',
    # 企業情報・口コミサイト
    'bizmap.jp', 'baseconnect.in', 'wantedly.com', 'vorkers.com', 'openwork.jp',
    # 地図・ナビ・施設検索
    'navitime.co.jp', 'mapion.co.jp', 'mapfan.com', 'ekiten.jp',
    'hotpepper.jp', 'tabelog.com', 'gnavi.co.jp', 'retty.me',
    # 転職・キャリア系ポータル
    'career-x.co.jp', 'type.jp', 'green-japan.com', 'mid-tenshoku.com',
    # ブログ・技術系
    'note.com', 'qiita.com', 'zenn.dev', 'hateblo.jp', 'ameblo.jp',
    # プレスリリース
    'prtimes.jp', 'atpress.ne.jp',
    # 企業リスト・まとめ
    'geekly.co.jp', 'imitsu.jp', 'houjin.jp',
    'factoring.southagency.co.jp', 'mics.city.shinagawa.tokyo.jp',
    'best100.v-tsushin.jp', 'isms.jp', 'itnabi.com',
    'appstars.io', 'ikesai.com', 'rekaizen.com', 'careerforum.net',
    'startupclass.co.jp', 'herp.careers', 'readycrew.jp', 'ai-taiwan.com.tw',
    'utilly.ne.jp', 'hatarakigai.info', 'officenomikata.jp', 'cheercareer.jp'
]


def generate_search_queries(keyword: str) -> list[str]:
    """
    キーワードから検索クエリを生成

    Args:
        keyword: 検索キーワード（例: "東京 IT企業"）

    Returns:
        生成されたクエリのリスト
    """
    queries = []
    for pattern in QUERY_PATTERNS:
        queries.append(pattern.format(keyword=keyword))
    return queries


def extract_domain(url: str) -> str:
    """URLからドメインを抽出"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return url


def is_excluded_domain(domain: str) -> bool:
    """除外ドメインかチェック"""
    domain_lower = domain.lower()
    return any(excluded in domain_lower for excluded in EXCLUDE_DOMAINS)


class SerperClient:
    """Serper.dev APIクライアント"""

    API_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        num: int = 100,
        start: int = 0,
        gl: str = "jp",
        hl: str = "ja",
    ) -> list[dict]:
        """
        Serper APIで検索

        Args:
            query: 検索クエリ
            num: 取得件数（最大100）
            start: オフセット
            gl: 国コード
            hl: 言語コード

        Returns:
            検索結果のリスト
        """
        payload = {
            "q": query,
            "num": min(num, 100),
            "gl": gl,
            "hl": hl,
        }
        if start > 0:
            payload["start"] = start

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.API_URL,
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("organic", [])
        except httpx.HTTPStatusError as e:
            logger.error(f"Serper API HTTP error: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Serper API error: {e}")
            raise

    async def search_companies(
        self,
        queries: list[str],
        target_count: int,
        existing_domains: Optional[set[str]] = None,
        max_pages_per_query: int = 3,
    ) -> list[CompanyData]:
        """
        複数クエリで企業を検索し、重複除去して返す

        Args:
            queries: 検索クエリのリスト
            target_count: 目標件数
            existing_domains: 既存のドメインセット（重複排除用）
            max_pages_per_query: クエリごとの最大ページ数

        Returns:
            CompanyDataのリスト
        """
        if existing_domains is None:
            existing_domains = set()

        found_domains: set[str] = set(existing_domains)
        companies: list[CompanyData] = []

        for query in queries:
            if len(companies) >= target_count:
                break

            logger.info(f"検索クエリ: {query}")

            for page in range(max_pages_per_query):
                if len(companies) >= target_count:
                    break

                start = page * 100
                try:
                    results = await self.search(query, num=100, start=start)
                except Exception as e:
                    logger.warning(f"検索エラー (query={query}, page={page}): {e}")
                    break

                if not results:
                    logger.debug(f"結果なし: {query} (page={page})")
                    break

                for result in results:
                    if len(companies) >= target_count:
                        break

                    url = result.get("link", "")
                    if not url:
                        continue

                    domain = extract_domain(url)

                    # 除外ドメインチェック
                    if is_excluded_domain(domain):
                        continue

                    # 重複チェック
                    if domain in found_domains:
                        continue

                    found_domains.add(domain)
                    companies.append(CompanyData(
                        company_name=result.get("title", ""),
                        url=url,
                        domain=domain,
                        snippet=result.get("snippet", ""),
                    ))

                logger.info(f"検索完了: {query} (page={page+1}) - 現在{len(companies)}件")

        logger.info(f"検索終了: 合計{len(companies)}件の企業を発見")
        return companies
