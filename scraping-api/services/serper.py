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


# クエリ生成パターン（Difyワークフローを参考に多様なクエリを生成）
# A. 業種の細分化、B. 地域の細分化、C. 企業規模、D. リスト系、E. 公式サイト系
def generate_diverse_queries(keyword: str) -> list[str]:
    """
    キーワードから多様な検索クエリを生成（Difyワークフロー準拠）
    25〜30個のクエリを生成
    """
    queries = []

    # 基本パターン
    base_patterns = [
        "{keyword} 株式会社",
        "{keyword} 有限会社",
        "{keyword} 合同会社",
        "{keyword} 企業",
        "{keyword} 会社",
    ]

    # 業種の別表現（IT企業の場合の例）
    industry_variants = [
        "{keyword} システム開発",
        "{keyword} Web制作",
        "{keyword} ソフトウェア",
        "{keyword} アプリ開発",
        "{keyword} ソリューション",
    ]

    # リスト・一覧系
    list_patterns = [
        "{keyword} 企業一覧",
        "{keyword} 会社一覧",
        "{keyword} 企業リスト",
        "{keyword} おすすめ企業",
        "{keyword} 優良企業",
    ]

    # 公式サイト特化
    official_patterns = [
        "{keyword} site:co.jp",
        "{keyword} 本社",
        "{keyword} 会社概要",
        "{keyword} 公式",
    ]

    # 協会・団体系
    association_patterns = [
        "{keyword} 協会 会員",
        "{keyword} 連盟",
    ]

    all_patterns = (
        base_patterns +
        industry_variants +
        list_patterns +
        official_patterns +
        association_patterns
    )

    for pattern in all_patterns:
        queries.append(pattern.format(keyword=keyword))

    return queries


# 除外ドメインサフィックス（政府・自治体・教育機関）
EXCLUDE_SUFFIXES = ['.go.jp', '.lg.jp', '.ed.jp', '.ac.jp']

# 除外タイトルパターン（まとめ記事、ランキング記事、求人サイト等を除外）
EXCLUDE_TITLE_PATTERNS = [
    # 求人・転職系（最優先で除外）
    "転職", "求人", "採用情報", "年収", "就職", "インターン",
    "応援サイト", "お仕事", "仕事を探す", "仕事探し", "会員登録",
    "派遣", "正社員", "アルバイト", "パート", "工場求人",
    "製造求人", "軽作業", "工場で働く", "ものづくり企業で働く",
    # ポータル・検索系
    "企業検索", "会社検索", "法人検索", "企業データベース",
    # 明確なまとめサイトパターン（「〇〇社を紹介」など）
    "社を紹介", "社まとめ", "件を紹介", "企業を紹介",
    "徹底比較", "口コミ", "評判",
]
# 注意: 「一覧」「ランキング」「おすすめ」「比較」は除外しない
# （検索クエリ自体にこれらが含まれるため、企業HPもヒットする可能性がある）

# 除外ドメイン（scraper.pyと共通）
EXCLUDE_DOMAINS = [
    # 求人サイト（主要）
    'indeed.com', 'indeed.jp', 'mynavi.jp', 'rikunabi.com', 'doda.jp',
    'en-japan.com', 'baitoru.com', 'careerconnection.jp', 'jobchange.jp', 'hatarako.net',
    # 求人サイト（工場・製造系）
    'tama-monozukuri.jp', 'job-gear.jp', 'e-aidem.com', 'hellowork.mhlw.go.jp',
    'persol-factorypartners.co.jp', 'factory-job.jp', 'kojo-job.jp', 'kojo-navi.jp',
    'job-list.net', 'monozukuri-matching.jp', 'jobpaper.net', 'nikkan.co.jp',
    # 求人サイト（IT・クリエイティブ系）
    'findjob.jp', 'forkwell.com', 'geekly.co.jp', 'paiza.jp', 'levtech.jp',
    # 派遣・人材系
    'tempstaff.co.jp', 'pasona.co.jp', 'manpowergroup.jp', 'adecco.co.jp',
    'staffservice.co.jp', 'haken.en-japan.com',
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




def extract_domain(url: str) -> str:
    """URLからドメインを抽出"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return url


def is_excluded_domain(domain: str) -> bool:
    """除外ドメインかチェック（ドメインリスト + サフィックス）"""
    domain_lower = domain.lower()
    # 除外ドメインリストチェック
    if any(excluded in domain_lower for excluded in EXCLUDE_DOMAINS):
        return True
    # 除外サフィックスチェック（政府・自治体・教育機関）
    if any(domain_lower.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return True
    return False


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
