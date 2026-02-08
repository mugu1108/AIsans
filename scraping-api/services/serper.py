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


# クエリ生成パターン（企業公式サイトを見つけやすいクエリ）
# シンプルなクエリで企業サイトを検索
QUERY_PATTERNS = [
    "{keyword} 株式会社",
    "{keyword} 有限会社",
    "{keyword} 合同会社",
    "{keyword} site:co.jp",
    "{keyword} site:or.jp",
]

# 除外タイトルパターン（まとめ記事、ランキング記事等を除外）
EXCLUDE_TITLE_PATTERNS = [
    "ランキング", "一覧", "比較", "おすすめ", "選び方", "まとめ",
    "厳選", "徹底比較", "口コミ", "評判", "人気", "top", "best",
    "選", "社を紹介", "社まとめ", "件を紹介", "企業を紹介",
    "転職", "求人", "採用情報", "年収", "就職", "インターン",
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
    'utilly.ne.jp', 'hatarakigai.info', 'officenomikata.jp', 'cheercareer.jp',
    # 追加: まとめ・ランキングサイト
    'mersenne.jp', '3utsu.com', 'fallabs.com', 'boxil.jp', 'itreview.jp',
    '発注ナビ.jp', 'ferret-plus.com', 'liskul.com', 'webtan.impress.co.jp',
    'seleck.cc', 'leverages.jp', 'aippear.net', 'techcrunch.com',
    'bridge-salon.jp', 'it-trend.jp', 'aspic.or.jp', 'meetsmore.com',
    'proengineer.internous.co.jp', 'crowdworks.jp', 'lancers.jp',
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


def is_excluded_title(title: str) -> bool:
    """除外すべきタイトル（まとめ記事等）かチェック"""
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in EXCLUDE_TITLE_PATTERNS)


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
        max_pages_per_query: int = 5,
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

                skipped_domain = 0
                skipped_title = 0
                skipped_dup = 0
                added = 0

                for result in results:
                    if len(companies) >= target_count:
                        break

                    url = result.get("link", "")
                    title = result.get("title", "")
                    if not url:
                        continue

                    domain = extract_domain(url)

                    # 除外ドメインチェック
                    if is_excluded_domain(domain):
                        skipped_domain += 1
                        continue

                    # 除外タイトルチェック（まとめ記事等をスキップ）
                    if is_excluded_title(title):
                        skipped_title += 1
                        continue

                    # 重複チェック
                    if domain in found_domains:
                        skipped_dup += 1
                        continue

                    found_domains.add(domain)
                    companies.append(CompanyData(
                        company_name=title,
                        url=url,
                        domain=domain,
                        snippet=result.get("snippet", ""),
                    ))
                    added += 1

                if skipped_domain or skipped_title:
                    logger.debug(f"  スキップ: ドメイン除外={skipped_domain}, タイトル除外={skipped_title}, 重複={skipped_dup}, 追加={added}")

                logger.info(f"検索完了: {query} (page={page+1}) - 現在{len(companies)}件")

        logger.info(f"検索終了: 合計{len(companies)}件の企業を発見")
        return companies
