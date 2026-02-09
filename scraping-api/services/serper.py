"""
Serper.dev 検索モジュール
Google検索APIを使用して企業URLを取得

v2改善:
- ページング最適化（5→2ページ + 0件追加で打ち切り）
- 企業サイト軽量チェック（is_likely_company_title）
- 汎用リトライクエリ生成（業種・地域を自動判定）
"""

import re
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from models.search import CompanyData

logger = logging.getLogger(__name__)


# ============================================================
# クエリ生成
# ============================================================

def generate_diverse_queries(keyword: str) -> list[str]:
    """
    キーワードから多様な検索クエリを生成（Difyワークフロー準拠）
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
# 汎用リトライクエリ生成（v2追加）
# ============================================================

def generate_retry_queries(
    keyword: str,
    round_num: int,
    used_queries: set[str] = None,
) -> list[str]:
    """
    キーワードを分析して、業種・地域に適したリトライクエリを生成する。

    Args:
        keyword: 元の検索キーワード（例: "東京 IT企業", "大阪 製造業"）
        round_num: リトライ回数（1, 2, 3）
        used_queries: 使用済みクエリのセット
    """
    if used_queries is None:
        used_queries = set()

    parts = keyword.split()
    area, industry = _parse_keyword(parts)

    candidates = []

    if round_num == 1:
        # リトライ1回目: 業態バリエーション
        industry_variants = _get_industry_variants(industry)
        for variant in industry_variants:
            candidates.append(f"{area} {variant}" if area else variant)

        # 企業規模系（汎用）
        for scale in ["ベンチャー", "スタートアップ", "中堅", "老舗"]:
            candidates.append(f"{keyword} {scale}")

        # 法人格系（汎用）
        for corp in ["株式会社", "site:co.jp"]:
            for variant in industry_variants[:3]:
                q = f"{area} {variant} {corp}" if area else f"{variant} {corp}"
                candidates.append(q)

    elif round_num == 2:
        # リトライ2回目: 地域の細分化
        sub_areas = _get_sub_areas(area)
        for sub in sub_areas:
            candidates.append(f"{sub} {industry}" if industry else f"{sub} 企業")
            candidates.append(f"{sub} {industry} 株式会社" if industry else f"{sub} 株式会社")

        # 属性系（汎用）
        for attr in ["上場企業", "非上場", "急成長", "設立 2020年以降"]:
            candidates.append(f"{keyword} {attr}")

    elif round_num >= 3:
        # リトライ3回目: 周辺地域 + ニッチ切り口
        nearby_areas = _get_nearby_areas(area)
        for nearby in nearby_areas:
            candidates.append(f"{nearby} {industry}" if industry else f"{nearby} 企業")
            candidates.append(f"{nearby} {industry} 株式会社" if industry else f"{nearby} 株式会社")

        # ニッチ（汎用）
        for niche in ["BtoB", "自社サービス", "グローバル", "IPO"]:
            candidates.append(f"{keyword} {niche}")

    # 使用済みを除外
    new_queries = [q for q in candidates if q not in used_queries]

    logger.info(f"リトライクエリ生成(round={round_num}): {len(candidates)}候補 → "
                f"{len(new_queries)}個（{len(candidates) - len(new_queries)}個は使用済み）")

    return new_queries


# --- キーワード分析ヘルパー ---

# 地域キーワード一覧
_AREA_KEYWORDS = {
    "東京", "大阪", "名古屋", "福岡", "札幌", "横浜", "神戸", "京都",
    "埼玉", "千葉", "神奈川", "愛知", "兵庫", "北海道", "広島", "仙台",
    "渋谷", "新宿", "品川", "千代田", "中央区", "目黒",
    "さいたま", "川崎", "相模原", "堺", "北九州", "浜松", "熊本",
}


def _parse_keyword(parts: list[str]) -> tuple[str, str]:
    """キーワードを「地域」と「業種」に分離する"""
    area = ""
    industry_parts = []

    for part in parts:
        if part in _AREA_KEYWORDS or part.endswith("区") or part.endswith("市") or part.endswith("県"):
            area = part
        else:
            industry_parts.append(part)

    industry = " ".join(industry_parts)
    return area, industry


def _get_industry_variants(industry: str) -> list[str]:
    """業種に応じたバリエーションクエリを返す"""
    VARIANTS = {
        "IT": ["IT企業", "システム開発", "Web制作", "アプリ開発", "SaaS", "クラウド",
               "AI", "セキュリティ", "インフラ", "データ分析", "DX推進", "SES"],
        "IT企業": ["IT企業", "システム開発", "Web制作", "アプリ開発", "SaaS", "クラウド",
                   "AI", "セキュリティ", "インフラ", "データ分析", "DX推進", "SES"],
        "システム開発": ["SI企業", "受託開発", "業務システム", "Web開発", "ソフトウェア"],
        "Web制作": ["ホームページ制作", "Webデザイン", "ECサイト構築", "CMS開発"],
        "製造業": ["メーカー", "工場", "製造", "ものづくり", "部品加工", "金属加工",
                   "プラスチック成形", "電子部品", "精密機器", "自動車部品"],
        "メーカー": ["製造業", "工場", "OEM", "部品", "組立"],
        "建設": ["建設会社", "ゼネコン", "施工管理", "設備工事", "電気工事", "内装工事"],
        "不動産": ["不動産会社", "デベロッパー", "管理会社", "仲介", "賃貸管理"],
        "飲食": ["飲食店", "レストラン", "フードサービス", "ケータリング", "給食"],
        "物流": ["物流会社", "運送", "倉庫", "配送", "ロジスティクス"],
        "広告": ["広告代理店", "マーケティング", "PR会社", "デジタルマーケティング"],
        "人材": ["人材紹介", "人材派遣", "採用支援", "HRテック"],
        "コンサルティング": ["経営コンサルタント", "ITコンサル", "戦略コンサル", "業務改善"],
    }

    # 完全一致
    if industry in VARIANTS:
        return VARIANTS[industry]

    # 部分一致
    for key, variants in VARIANTS.items():
        if key in industry:
            return variants

    # マッチしない場合は汎用
    return [
        f"{industry} 株式会社",
        f"{industry} 中小企業",
        f"{industry} 優良企業",
        f"{industry} 会社一覧",
        f"{industry} site:co.jp",
    ]


def _get_sub_areas(area: str) -> list[str]:
    """地域の細分化（区・市レベル）"""
    SUB_AREAS = {
        "東京": ["渋谷区", "新宿区", "港区", "千代田区", "品川区", "中央区",
                 "目黒区", "豊島区", "文京区", "台東区", "江東区", "墨田区"],
        "大阪": ["大阪市北区", "大阪市中央区", "大阪市淀川区", "大阪市西区",
                 "堺市", "豊中市", "吹田市", "東大阪市"],
        "名古屋": ["名古屋市中区", "名古屋市中村区", "名古屋市東区",
                   "名古屋市西区", "名古屋市千種区"],
        "福岡": ["福岡市博多区", "福岡市中央区", "北九州市", "久留米市"],
        "横浜": ["横浜市西区", "横浜市中区", "横浜市港北区", "横浜市神奈川区"],
        "札幌": ["札幌市中央区", "札幌市北区", "札幌市東区"],
        "神戸": ["神戸市中央区", "神戸市兵庫区", "神戸市東灘区"],
        "京都": ["京都市下京区", "京都市中京区", "京都市上京区"],
    }
    return SUB_AREAS.get(area, [f"{area}市", f"{area}区"])


def _get_nearby_areas(area: str) -> list[str]:
    """周辺地域"""
    NEARBY = {
        "東京": ["神奈川", "横浜", "川崎", "埼玉", "さいたま市", "千葉"],
        "大阪": ["兵庫", "神戸", "京都", "奈良", "堺"],
        "名古屋": ["愛知", "岐阜", "三重", "豊田"],
        "福岡": ["北九州", "佐賀", "熊本", "大分"],
        "横浜": ["東京", "川崎", "藤沢", "相模原"],
        "札幌": ["旭川", "函館", "小樽"],
    }
    return NEARBY.get(area, [])


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
    # 追加: まとめ・ランキングサイト
    'mersenne.jp', '3utsu.com', 'fallabs.com', 'boxil.jp', 'itreview.jp',
    '発注ナビ.jp', 'ferret-plus.com', 'liskul.com', 'webtan.impress.co.jp',
    'seleck.cc', 'leverages.jp', 'aippear.net', 'techcrunch.com',
    'bridge-salon.jp', 'it-trend.jp', 'aspic.or.jp', 'meetsmore.com',
    'proengineer.internous.co.jp', 'crowdworks.jp', 'lancers.jp',
    # 追加: 比較・マッチングサイト
    'biz.ne.jp', 'web-kanji.com', 'system-kanji.com', 'video-kanji.com',
    'app-kanji.com', 'meibo-kanji.com', 'kanji-inc.co.jp',
    'bizitora.jp', 'system-dev-navi.com', 'emeao.jp', 'hnavi.co.jp',
    'hacchu-navi.com', 'rekaiz.com', '発注ナビ.com', 'b-pos.jp',
    'compareit.jp', 'itpropartners.com', 'pro-d-use.jp',
    # 追加: 就活・キャリア系サイト
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
    タイトルが企業サイトっぽいかの軽量チェック（v2追加）。
    LLMに送る前に明らかに企業でないものを落とす。

    True = 企業っぽい（残す）
    False = 企業っぽくない（除外）
    """
    # 法人格を含むなら企業サイトの可能性高い → 残す
    if re.search(r'株式会社|有限会社|合同会社|Inc\.|Corp\.|Co\.,?\s*Ltd|LLC', title, re.IGNORECASE):
        return True

    # 明らかに企業でないパターン → 除外
    # 数字+選のまとめ記事
    if re.search(r'\d+選', title):
        return False
    # 「〜とは」の解説記事
    if re.search(r'とは[？?]?\s*$|とは[|｜]', title):
        return False
    # 明確なまとめ・比較記事パターン
    if re.search(r'厳選|完全ガイド|徹底解説|まとめ記事', title):
        return False

    # 判定不能 → LLMに委ねる（残す）
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
        max_pages_per_query: int = 2,  # ★v2: 5→2に削減
    ) -> list[CompanyData]:
        """
        複数クエリで企業を検索し、重複除去して返す

        v2改善:
        - max_pages_per_query デフォルト 5→2 に削減
        - ページ内で追加0件なら次のクエリへスキップ
        - is_likely_company_title() で企業サイト軽量チェック
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
                skipped_not_company = 0  # ★v2追加
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

                    # 除外タイトルチェック
                    if is_excluded_title(title):
                        skipped_title += 1
                        continue

                    # 重複チェック
                    if domain in found_domains:
                        skipped_dup += 1
                        continue

                    # ★v2追加: 企業サイト軽量チェック
                    # .co.jp ドメインは法人格チェック免除（企業用ドメインなので）
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

                # ★v2追加: このページで追加0件なら次のクエリへ（後続ページも空振りの可能性大）
                if added == 0:
                    logger.debug(f"  page={page+1}で追加0件。次のクエリへスキップ。")
                    break

        logger.info(f"検索終了: 合計{len(companies)}件の企業を発見（クエリ数: {len(queries)}）")
        return companies