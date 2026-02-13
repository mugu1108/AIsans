"""
Serper.dev 検索モジュール
Google検索APIを使用して企業URLを取得

v3改善:
- ページング最適化（5→2ページ + 0件追加で打ち切り）
- 企業サイト軽量チェック（is_likely_company_title）
- クエリプール方式: 地域×業種×属性のクロス生成で数百のクエリを生成
- ラウンドごとにプールからバッチ取得（枯渇しない）
"""

import re
import logging
import random
from typing import Optional
from urllib.parse import urlparse

import httpx

from models.search import CompanyData

logger = logging.getLogger(__name__)


# ============================================================
# クエリ生成（初回）
# ============================================================

def generate_diverse_queries(keyword: str) -> list[str]:
    """
    キーワードから多様な検索クエリを生成（初回用）
    25〜30個のクエリを生成
    """
    queries = []

    base_patterns = [
        "{keyword} 株式会社",
        "{keyword} 有限会社",
        "{keyword} 合同会社",
        "{keyword} 企業",
        "{keyword} 会社",
    ]

    industry_variants = [
        "{keyword} システム開発",
        "{keyword} Web制作",
        "{keyword} ソフトウェア",
        "{keyword} アプリ開発",
        "{keyword} ソリューション",
    ]

    list_patterns = [
        "{keyword} 企業一覧",
        "{keyword} 会社一覧",
        "{keyword} 企業リスト",
        "{keyword} おすすめ企業",
        "{keyword} 優良企業",
    ]

    official_patterns = [
        "{keyword} site:co.jp",
        "{keyword} 本社",
        "{keyword} 会社概要",
        "{keyword} 公式",
    ]

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


# ============================================================
# クエリプール方式のリトライクエリ生成（v3）
# ============================================================

class QueryPool:
    """
    地域×業種×属性のクロス生成で大量のクエリプールを作り、
    ラウンドごとにバッチで取り出す。
    """

    def __init__(self, keyword: str):
        self.keyword = keyword
        parts = keyword.split()
        self.area, self.industry = self._parse_keyword(parts)
        self._pool: list[str] = []
        self._used: set[str] = set()
        self._build_pool()

    def _parse_keyword(self, parts: list[str]) -> tuple[str, str]:
        """キーワードを「地域」と「業種」に分離"""
        area = ""
        industry_parts = []

        for part in parts:
            if part in _AREA_KEYWORDS or part.endswith("区") or part.endswith("市") or part.endswith("県"):
                area = part
            else:
                industry_parts.append(part)

        industry = " ".join(industry_parts)
        return area, industry

    def _build_pool(self):
        """地域×業種×属性のクロスでクエリプールを生成"""
        areas = self._get_all_areas()
        variants = self._get_all_industry_variants()
        suffixes = self._get_suffixes()

        pool = set()

        # パターン1: 地域 × 業種バリエーション
        for area in areas:
            for variant in variants:
                pool.add(f"{area} {variant}")

        # パターン2: 地域 × 業種 × 属性サフィックス
        for area in areas:
            for variant in variants[:5]:  # 主要バリエーションのみ
                for suffix in suffixes:
                    pool.add(f"{area} {variant} {suffix}")

        # パターン3: 元キーワード × 属性サフィックス
        for suffix in suffixes:
            pool.add(f"{self.keyword} {suffix}")

        # パターン4: 業種 × site:co.jp（地域なし）
        for variant in variants:
            pool.add(f"{variant} 株式会社 site:co.jp")

        # パターン5: 元キーワード × 企業リスト系
        list_keywords = ["企業一覧", "会社一覧", "企業リスト", "会社リスト",
                         "有名企業", "成長企業", "注目企業"]
        for lk in list_keywords:
            pool.add(f"{self.keyword} {lk}")
            for area in areas[:6]:
                pool.add(f"{area} {self.industry} {lk}" if self.industry else f"{area} {lk}")

        self._pool = list(pool)
        random.shuffle(self._pool)  # シャッフルして偏りを防ぐ

        logger.info(f"クエリプール生成: {len(self._pool)}個（地域{len(areas)}×業種{len(variants)}×属性{len(suffixes)}）")

    def _get_all_areas(self) -> list[str]:
        """検索対象の全地域（メインエリア + サブエリア + 周辺）"""
        areas = []

        # メインエリア
        if self.area:
            areas.append(self.area)

        # サブエリア
        sub = _SUB_AREAS.get(self.area, [])
        areas.extend(sub)

        # 周辺エリア
        nearby = _NEARBY_AREAS.get(self.area, [])
        areas.extend(nearby)

        # エリアがない場合は主要都市
        if not areas:
            areas = ["東京", "大阪", "名古屋", "福岡", "横浜", "札幌"]

        return areas

    def _get_all_industry_variants(self) -> list[str]:
        """業種の全バリエーション"""
        variants = []

        # メイン業種
        if self.industry:
            variants.append(self.industry)

        # 業種バリエーション辞書から取得
        for key, vals in _INDUSTRY_VARIANTS.items():
            if key in (self.industry or ""):
                variants.extend(vals)
                break
        else:
            # マッチしない場合は汎用
            if self.industry:
                variants.extend([
                    f"{self.industry} 株式会社",
                    f"{self.industry} 中小企業",
                    f"{self.industry} 優良企業",
                ])

        # 重複除去しつつ順序保持
        seen = set()
        unique = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique.append(v)

        return unique

    def _get_suffixes(self) -> list[str]:
        """属性サフィックス"""
        return [
            "株式会社", "site:co.jp",
            "ベンチャー", "スタートアップ", "中堅", "老舗",
            "上場企業", "非上場", "急成長",
            "BtoB", "自社サービス", "受託",
            "設立 2020年以降", "設立 2015年以降",
        ]

    def mark_used(self, queries: list[str]):
        """使用済みとしてマーク"""
        self._used.update(queries)

    def get_batch(self, batch_size: int = 15) -> list[str]:
        """未使用のクエリをバッチで取得"""
        batch = []
        for q in self._pool:
            if q not in self._used:
                batch.append(q)
                if len(batch) >= batch_size:
                    break

        # 取得したものを使用済みに
        self._used.update(batch)

        remaining = len([q for q in self._pool if q not in self._used])
        logger.info(f"クエリバッチ取得: {len(batch)}個（残り{remaining}個）")

        return batch

    @property
    def remaining_count(self) -> int:
        return len([q for q in self._pool if q not in self._used])


# --- 定数データ ---

_AREA_KEYWORDS = {
    "東京", "大阪", "名古屋", "福岡", "札幌", "横浜", "神戸", "京都",
    "埼玉", "千葉", "神奈川", "愛知", "兵庫", "北海道", "広島", "仙台",
    "渋谷", "新宿", "品川", "千代田", "中央区", "目黒",
    "さいたま", "川崎", "相模原", "堺", "北九州", "浜松", "熊本",
}

_SUB_AREAS = {
    "東京": ["渋谷区", "新宿区", "港区", "千代田区", "品川区", "中央区",
             "目黒区", "豊島区", "文京区", "台東区", "江東区", "墨田区",
             "世田谷区", "大田区", "杉並区", "練馬区", "板橋区", "北区",
             "中野区", "荒川区", "足立区", "葛飾区", "江戸川区"],
    "大阪": ["大阪市北区", "大阪市中央区", "大阪市淀川区", "大阪市西区",
             "堺市", "豊中市", "吹田市", "東大阪市", "高槻市", "枚方市"],
    "名古屋": ["名古屋市中区", "名古屋市中村区", "名古屋市東区",
               "名古屋市西区", "名古屋市千種区", "名古屋市名東区"],
    "福岡": ["福岡市博多区", "福岡市中央区", "北九州市", "久留米市", "福岡市早良区"],
    "横浜": ["横浜市西区", "横浜市中区", "横浜市港北区", "横浜市神奈川区", "横浜市鶴見区"],
    "札幌": ["札幌市中央区", "札幌市北区", "札幌市東区", "札幌市白石区"],
    "神戸": ["神戸市中央区", "神戸市兵庫区", "神戸市東灘区", "神戸市灘区"],
    "京都": ["京都市下京区", "京都市中京区", "京都市上京区", "京都市南区"],
}

_NEARBY_AREAS = {
    "東京": ["神奈川", "横浜", "川崎", "埼玉", "さいたま市", "千葉", "船橋", "柏", "立川", "八王子", "町田", "武蔵野市", "三鷹市"],
    "大阪": ["兵庫", "神戸", "京都", "奈良", "堺", "尼崎", "西宮"],
    "名古屋": ["愛知", "岐阜", "三重", "豊田", "豊橋", "一宮"],
    "福岡": ["北九州", "佐賀", "熊本", "大分", "長崎"],
    "横浜": ["東京", "川崎", "藤沢", "相模原", "鎌倉", "横須賀"],
    "札幌": ["旭川", "函館", "小樽", "帯広", "釧路"],
}

_INDUSTRY_VARIANTS = {
    "IT": ["IT企業", "システム開発", "Web制作", "アプリ開発", "SaaS", "クラウド",
           "AI", "セキュリティ", "インフラ", "データ分析", "DX推進", "SES",
           "ソフトウェア", "SI企業", "受託開発", "業務システム", "ECサイト",
           "IoT", "フィンテック", "ブロックチェーン", "VR", "AR"],
    "IT企業": ["IT企業", "システム開発", "Web制作", "アプリ開発", "SaaS", "クラウド",
               "AI", "セキュリティ", "インフラ", "データ分析", "DX推進", "SES",
               "ソフトウェア", "SI企業", "受託開発", "業務システム", "ECサイト",
               "IoT", "フィンテック", "ブロックチェーン", "VR", "AR"],
    "システム開発": ["SI企業", "受託開発", "業務システム", "Web開発", "ソフトウェア",
                    "基幹システム", "組込みシステム", "ERP"],
    "Web制作": ["ホームページ制作", "Webデザイン", "ECサイト構築", "CMS開発",
               "Webマーケティング", "SEO対策", "LP制作"],
    "製造業": ["メーカー", "工場", "製造", "ものづくり", "部品加工", "金属加工",
               "プラスチック成形", "電子部品", "精密機器", "自動車部品",
               "食品製造", "化学メーカー", "機械メーカー"],
    "建設": ["建設会社", "ゼネコン", "施工管理", "設備工事", "電気工事", "内装工事",
            "土木", "リフォーム", "建築設計"],
    "不動産": ["不動産会社", "デベロッパー", "管理会社", "仲介", "賃貸管理",
              "不動産投資", "マンション", "ビル管理"],
    "飲食": ["飲食店", "レストラン", "フードサービス", "ケータリング", "給食",
            "居酒屋", "カフェ", "外食"],
    "物流": ["物流会社", "運送", "倉庫", "配送", "ロジスティクス", "宅配", "運輸"],
    "広告": ["広告代理店", "マーケティング", "PR会社", "デジタルマーケティング",
            "クリエイティブ", "ブランディング"],
    "人材": ["人材紹介", "人材派遣", "採用支援", "HRテック", "研修", "コーチング"],
    "コンサルティング": ["経営コンサルタント", "ITコンサル", "戦略コンサル", "業務改善",
                       "DXコンサル", "財務コンサル"],
}


# ============================================================
# 後方互換: generate_retry_queries（QueryPoolを使う版）
# ============================================================

# グローバルにQueryPoolインスタンスを保持
_query_pools: dict[str, QueryPool] = {}


def generate_retry_queries(
    keyword: str,
    round_num: int,
    used_queries: set[str] = None,
) -> list[str]:
    """
    リトライ用クエリを生成（QueryPool方式）。
    何ラウンド目でもプールから未使用のクエリを返せる。
    """
    if used_queries is None:
        used_queries = set()

    # QueryPoolの取得（初回のみ生成）
    if keyword not in _query_pools:
        _query_pools[keyword] = QueryPool(keyword)

    pool = _query_pools[keyword]
    pool.mark_used(used_queries)

    # バッチサイズ: ラウンドが進むほど少なめに（効率化）
    batch_size = max(8, 20 - round_num * 2)
    queries = pool.get_batch(batch_size)

    logger.info(f"リトライクエリ生成(round={round_num}): {len(queries)}個取得"
                f"（プール残り{pool.remaining_count}個）")

    return queries


# ============================================================
# 除外フィルタ
# ============================================================

EXCLUDE_SUFFIXES = ['.go.jp', '.lg.jp', '.ed.jp', '.ac.jp']

EXCLUDE_TITLE_PATTERNS = [
    # 求人・転職系
    "転職", "求人", "採用情報", "年収", "就職", "インターン",
    "応援サイト", "お仕事", "仕事を探す", "仕事探し", "会員登録",
    "派遣", "正社員", "アルバイト", "パート", "工場求人",
    "製造求人", "軽作業", "工場で働く", "ものづくり企業で働く",
    # 就活・キャリア系
    "就活", "キャリア", "新卒", "内定", "エントリー",
    # ポータル・検索系
    "企業検索", "会社検索", "法人検索", "企業データベース",
    # 明確なまとめサイトパターン
    "社を紹介", "社まとめ", "件を紹介", "企業を紹介",
    "徹底比較", "口コミ", "評判",
    # ランキング・TOP系
    "TOP100", "TOP50", "TOP10", "ランキングTOP",
]

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
    # まとめ・ランキングサイト
    'mersenne.jp', '3utsu.com', 'fallabs.com', 'boxil.jp', 'itreview.jp',
    'ferret-plus.com', 'liskul.com', 'webtan.impress.co.jp',
    'seleck.cc', 'leverages.jp', 'aippear.net', 'techcrunch.com',
    'bridge-salon.jp', 'it-trend.jp', 'aspic.or.jp', 'meetsmore.com',
    'proengineer.internous.co.jp', 'crowdworks.jp', 'lancers.jp',
    # 比較・マッチングサイト
    'biz.ne.jp', 'web-kanji.com', 'system-kanji.com', 'video-kanji.com',
    'app-kanji.com', 'meibo-kanji.com', 'kanji-inc.co.jp',
    'bizitora.jp', 'system-dev-navi.com', 'emeao.jp', 'hnavi.co.jp',
    'hacchu-navi.com', 'rekaiz.com', 'b-pos.jp',
    'compareit.jp', 'itpropartners.com', 'pro-d-use.jp',
    # 就活・キャリア系サイト
    'carrikatu-it.com', 'unison-career.jp', 'career-tasu.jp',
    'job-terminal.com', 'shukatsu-mirai.com', 'onecareer.jp',
    'goodfind.jp', 'offerbox.jp', 'digmee.jp', 'jobrass.com',
    'rebe.jp', 'careerpark.jp', 'shukatsu-kaigi.jp',
]


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
    if any(excluded in domain_lower for excluded in EXCLUDE_DOMAINS):
        return True
    if any(domain_lower.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return True
    return False


def is_excluded_title(title: str) -> bool:
    """除外すべきタイトル（まとめ記事等）かチェック"""
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in EXCLUDE_TITLE_PATTERNS)


def is_likely_company_title(title: str) -> bool:
    """
    タイトルが企業サイトっぽいかの軽量チェック。
    True = 企業っぽい（残す）
    False = 企業っぽくない（除外）
    """
    if re.search(r'株式会社|有限会社|合同会社|Inc\.|Corp\.|Co\.,?\s*Ltd|LLC', title, re.IGNORECASE):
        return True
    if re.search(r'\d+選', title):
        return False
    if re.search(r'とは[？?]?\s*$|とは[|｜]', title):
        return False
    if re.search(r'厳選|完全ガイド|徹底解説|まとめ記事', title):
        return False
    return True


# ============================================================
# Serper API クライアント
# ============================================================

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
        """Serper APIで検索"""
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
        max_pages_per_query: int = 1,
    ) -> list[CompanyData]:
        """
        複数クエリで企業を検索し、重複除去して返す
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
                skipped_not_company = 0
                added = 0

                for result in results:
                    if len(companies) >= target_count:
                        break

                    url = result.get("link", "")
                    title = result.get("title", "")
                    if not url:
                        continue

                    domain = extract_domain(url)

                    if is_excluded_domain(domain):
                        skipped_domain += 1
                        continue

                    if is_excluded_title(title):
                        skipped_title += 1
                        continue

                    if domain in found_domains:
                        skipped_dup += 1
                        continue

                    if not domain.endswith('.co.jp') and not is_likely_company_title(title):
                        skipped_not_company += 1
                        continue

                    found_domains.add(domain)
                    companies.append(CompanyData(
                        company_name=title,
                        url=url,
                        domain=domain,
                        snippet=result.get("snippet", ""),
                    ))
                    added += 1

                if skipped_domain or skipped_title or skipped_not_company:
                    logger.debug(f"  スキップ: ドメイン除外={skipped_domain}, タイトル除外={skipped_title}, "
                                 f"非企業={skipped_not_company}, 重複={skipped_dup}, 追加={added}")

                logger.info(f"検索完了: {query} (page={page+1}) - 現在{len(companies)}件")

                # このページで追加0件なら次のクエリへ
                if added == 0:
                    logger.debug(f"  page={page+1}で追加0件。次のクエリへスキップ。")
                    break

        logger.info(f"検索終了: 合計{len(companies)}件の企業を発見（クエリ数: {len(queries)}）")
        return companies