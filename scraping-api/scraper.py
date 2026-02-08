"""
スクレイピングロジック
GASコードからの移植 + 企業名一致チェック機能
"""

import re
import asyncio
import logging
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ====================================
# 定数
# ====================================

# 除外ドメイン（求人サイト、ニュース、SNS等）
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

# お問い合わせURL検索キーワード
CONTACT_KEYWORDS = [
    'contact', 'inquiry', 'enquiry', 'toiawase', 'otoiawase',
    'お問い合わせ', 'お問合せ', 'お問合わせ', 'おといあわせ',
    'form', 'mail', 'support'
]

# よくあるお問い合わせURLパターン
COMMON_CONTACT_PATHS = [
    'contact/',
    'contact',
    'inquiry/',
    'contact.html',
    'toiawase/',
    'otoiawase/',
    'form/',
    'contact-us/',
    'contactus/',
    'mail/',
    'support/',
    'info/',
    'ask/',
    'inquiry.html',
    'contact/index.html',
]

# 法人格除去パターン（企業名正規化用）
CORPORATE_SUFFIXES = [
    '株式会社', '(株)', '（株）',
    '有限会社', '(有)', '（有）',
    '合同会社', '合資会社', '合名会社',
    '一般社団法人', '一般財団法人', '公益社団法人', '公益財団法人',
    '特定非営利活動法人', 'NPO法人',
    'Inc.', 'Co.,Ltd.', 'Ltd.', 'Corp.', 'LLC', 'LLP',
    'Corporation', 'Company', 'Co.'
]

# HTTPヘッダー
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3'
}

HTTP_TIMEOUT = 10.0  # 秒
MAX_CONCURRENT = 10  # 同時接続数


# ====================================
# データクラス
# ====================================

@dataclass
class ScrapeResult:
    """スクレイピング結果"""
    company_name: str
    base_url: str
    contact_url: str
    phone: str
    domain: str
    error: str


# ====================================
# URL操作関数
# ====================================

def normalize_to_top_page(url: str) -> str:
    """URLをトップページに正規化"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return url


def extract_domain(url: str) -> str:
    """URLからドメインを抽出"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return url


def is_same_domain(url1: str, url2: str) -> bool:
    """同一ドメインかチェック"""
    return extract_domain(url1) == extract_domain(url2)


def is_excluded_domain(domain: str) -> bool:
    """除外ドメインかチェック"""
    domain_lower = domain.lower()
    return any(excluded in domain_lower for excluded in EXCLUDE_DOMAINS)


def resolve_url(base_url: str, relative_url: str) -> str:
    """相対URLを絶対URLに変換"""
    if relative_url.startswith('http'):
        return relative_url
    return urljoin(base_url, relative_url)


# ====================================
# 企業名正規化・一致チェック
# ====================================

def normalize_company_name(name: str) -> str:
    """
    企業名を正規化
    - 小文字化
    - 法人格除去
    - 空白・記号除去
    """
    normalized = name.lower()

    # 法人格除去
    for suffix in CORPORATE_SUFFIXES:
        normalized = normalized.replace(suffix.lower(), '')

    # 空白・記号除去
    normalized = re.sub(r'[\s\u3000・\-\(\)（）【】「」『』\[\]]+', '', normalized)

    return normalized.strip()


def check_company_match(company_name: str, html: str) -> bool:
    """
    企業名とページ内容の一致をチェック

    Returns:
        True: 一致（OK）
        False: 不一致（company_mismatch）
    """
    normalized_name = normalize_company_name(company_name)

    # 正規化後の企業名が2文字未満の場合、チェックスキップ
    if len(normalized_name) < 2:
        return True

    soup = BeautifulSoup(html, 'lxml')

    # titleタグ取得
    title = ''
    title_tag = soup.find('title')
    if title_tag:
        title = normalize_company_name(title_tag.get_text())

    # og:site_name取得
    og_site_name = ''
    og_tag = soup.find('meta', property='og:site_name')
    if og_tag and og_tag.get('content'):
        og_site_name = normalize_company_name(og_tag['content'])

    # 一致判定
    # name が title または og に含まれている
    if normalized_name in title:
        return True
    if normalized_name in og_site_name:
        return True

    # title（2文字以上）が name に含まれている
    if len(title) >= 2 and title in normalized_name:
        return True

    # og（2文字以上）が name に含まれている
    if len(og_site_name) >= 2 and og_site_name in normalized_name:
        return True

    # ヘッダー・フッター・会社概要セクションから企業名を検索
    # これにより、タイトルに企業名がなくても本文にあれば一致とみなす
    for selector in ['header', 'footer', '.company', '#company', '.about', '#about', '.corp', '#corp']:
        elements = soup.select(selector)
        for elem in elements:
            elem_text = normalize_company_name(elem.get_text())
            if normalized_name in elem_text:
                return True

    # 企業名の主要部分（3文字以上）がページ全体に含まれているかチェック
    if len(normalized_name) >= 3:
        # ページ全体のテキストを取得（スクリプト・スタイル除去）
        for script in soup(['script', 'style', 'noscript']):
            script.decompose()
        body_text = normalize_company_name(soup.get_text())

        # 企業名がページ本文に含まれている場合
        if normalized_name in body_text:
            return True

    return False


# ====================================
# 電話番号処理
# ====================================

def is_valid_phone_number(phone: str) -> bool:
    """電話番号のバリデーション"""
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 10 or len(digits) > 11:
        return False
    if not digits.startswith('0'):
        return False
    if '0000' in digits:
        return False
    return True


def format_phone_number(phone: str) -> str:
    """電話番号をフォーマット"""
    digits = re.sub(r'\D', '', phone)

    # 03始まり10桁
    if len(digits) == 10 and digits[:2] == '03':
        return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"

    # 携帯番号11桁
    if len(digits) == 11 and digits[:2] in ('09', '08', '07'):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"

    # 0120始まり10桁
    if len(digits) == 10 and digits[:4] == '0120':
        return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"

    # ハイフンが既にある場合はそのまま
    if '-' in phone:
        return phone

    # その他10桁
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

    # その他11桁
    return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"


def extract_phone_from_html(html: str) -> str:
    """HTMLから電話番号を抽出"""

    # パターン1: tel:リンク（最優先）
    tel_pattern = r'href=["\']tel:([0-9\-]+)["\']'
    tel_matches = re.findall(tel_pattern, html)
    for match in tel_matches:
        phone = re.sub(r'[^\d\-]', '', match).replace('--', '-')
        if is_valid_phone_number(phone):
            return format_phone_number(phone)

    # パターン2: ラベル付き電話番号
    labeled_pattern = r'(?:TEL|Tel|tel|電話|電話番号|☎|📞|℡|代表)[:\s：]*?\(?0\d{1,4}\)?[-\s\.\-]?\d{1,4}[-\s\.\-]?\d{3,4}'
    labeled_matches = re.findall(labeled_pattern, html)
    for match in labeled_matches:
        phone = re.sub(r'[^\d\-]', '', match).replace('--', '-')
        if is_valid_phone_number(phone):
            return format_phone_number(phone)

    # パターン3: 数字パターンのみ
    digit_pattern = r'\b0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}\b'
    digit_matches = re.findall(digit_pattern, html)
    for match in digit_matches:
        phone = re.sub(r'[^\d\-]', '', match).replace('--', '-')
        if is_valid_phone_number(phone):
            return format_phone_number(phone)

    return ''


# ====================================
# お問い合わせURL抽出
# ====================================

def calculate_contact_score(href: str, text: str) -> int:
    """お問い合わせURLのスコア計算"""
    score = 0
    href_lower = href.lower()
    text_lower = text.lower()

    if 'contact' in href_lower:
        score += 10
    if 'inquiry' in href_lower:
        score += 10
    if 'toiawase' in href_lower:
        score += 10
    if 'お問い合わせ' in text_lower:
        score += 8
    if 'お問合せ' in text_lower:
        score += 8
    if 'form' in href_lower:
        score += 5

    # パスの深さ
    path_depth = href.count('/')
    score += max(0, 5 - path_depth)

    return score


def extract_contact_from_html(html: str, base_url: str) -> str:
    """HTMLからお問い合わせURLを抽出"""
    soup = BeautifulSoup(html, 'lxml')
    candidates = []

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        text = a_tag.get_text(strip=True).lower()
        href_lower = href.lower()

        # 除外パターン
        if href_lower.startswith('mailto:'):
            continue
        if href_lower.startswith('javascript:'):
            continue
        if href_lower.startswith('tel:'):
            continue

        # #で始まるリンクは #contact のみ許可
        if href.startswith('#'):
            if href_lower != '#contact':
                continue

        # 外部ドメインへのリンクは除外
        if href_lower.startswith('http') and not is_same_domain(base_url, href):
            continue

        # キーワードマッチ
        for keyword in CONTACT_KEYWORDS:
            if keyword in href_lower or keyword in text:
                if href_lower == '#contact':
                    full_url = base_url + '#contact'
                else:
                    full_url = resolve_url(base_url, href)
                score = calculate_contact_score(href, text)
                candidates.append({'url': full_url, 'score': score})
                break

    if candidates:
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[0]['url']

    return ''


# ====================================
# 非同期HTTP取得
# ====================================

async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_retries: int = 1
) -> Optional[str]:
    """リトライ付きで非同期HTTP取得"""
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(
                url,
                headers=HTTP_HEADERS,
                timeout=HTTP_TIMEOUT,
                follow_redirects=True
            )
            if response.status_code == 200:
                return response.text
            else:
                logger.debug(f"HTTP {response.status_code}: {url}")
        except httpx.TimeoutException:
            logger.debug(f"タイムアウト: {url}")
        except Exception as e:
            logger.debug(f"HTTP取得エラー: {url} - {type(e).__name__}")
        if attempt < max_retries:
            await asyncio.sleep(0.3)
    return None


async def try_common_contact_urls(
    client: httpx.AsyncClient,
    base_url: str
) -> str:
    """よくあるお問い合わせURLパターンを試す"""
    for path in COMMON_CONTACT_PATHS:
        test_url = base_url + path
        html = await fetch_with_retry(client, test_url, max_retries=0)
        if html:
            html_lower = html.lower()
            if '<form' in html_lower or 'お問い合わせ' in html_lower or 'contact' in html_lower:
                return test_url
    return ''


# ====================================
# 単一企業スクレイピング
# ====================================

async def scrape_company(
    client: httpx.AsyncClient,
    company_name: str,
    url: str
) -> ScrapeResult:
    """単一企業のスクレイピング"""
    base_url = normalize_to_top_page(url)
    domain = extract_domain(base_url)
    contact_url = ''
    phone = ''
    error = ''

    logger.debug(f"スクレイピング開始: {company_name} ({base_url})")

    # STEP 1: トップページ取得
    top_page_html = await fetch_with_retry(client, base_url, max_retries=1)

    if not top_page_html:
        logger.warning(f"トップページ取得失敗: {company_name} ({base_url})")
        return ScrapeResult(
            company_name=company_name,
            base_url=base_url,
            contact_url='',
            phone='',
            domain=domain,
            error='top_page_failed'
        )

    # STEP 2: 企業名一致チェック
    if not check_company_match(company_name, top_page_html):
        logger.warning(f"企業名不一致: {company_name} ({base_url})")
        return ScrapeResult(
            company_name=company_name,
            base_url=base_url,
            contact_url='',
            phone='',
            domain=domain,
            error='company_mismatch'
        )

    # STEP 3: お問い合わせURL抽出
    contact_url = extract_contact_from_html(top_page_html, base_url)

    # STEP 4: 電話番号抽出（トップページから）
    phone = extract_phone_from_html(top_page_html)

    # STEP 5: お問い合わせページから電話番号取得
    if contact_url and not phone and '#' not in contact_url:
        contact_html = await fetch_with_retry(client, contact_url, max_retries=1)
        if contact_html:
            phone = extract_phone_from_html(contact_html)

    # STEP 6: よくあるパターンを試す（お問い合わせURLが見つからない場合）
    if not contact_url:
        contact_url = await try_common_contact_urls(client, base_url)

    # STEP 7: 会社概要から電話番号取得
    if not phone:
        about_urls = [base_url + 'company/', base_url + 'about/']
        for about_url in about_urls:
            about_html = await fetch_with_retry(client, about_url, max_retries=1)
            if about_html:
                phone = extract_phone_from_html(about_html)
                if phone:
                    break

    result = ScrapeResult(
        company_name=company_name,
        base_url=base_url,
        contact_url=contact_url,
        phone=phone,
        domain=domain,
        error=error
    )

    if contact_url or phone:
        logger.info(f"スクレイピング成功: {company_name} (contact: {bool(contact_url)}, phone: {bool(phone)})")
    else:
        logger.warning(f"連絡先未検出: {company_name} ({base_url})")

    return result


# ====================================
# バッチスクレイピング（並列処理）
# ====================================

async def scrape_companies(
    companies: list[dict]
) -> list[ScrapeResult]:
    """
    複数企業を並列スクレイピング

    Args:
        companies: [{"company_name": "...", "url": "..."}, ...]

    Returns:
        ScrapeResult のリスト
    """
    results = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def scrape_with_semaphore(client: httpx.AsyncClient, company: dict) -> ScrapeResult:
        async with semaphore:
            result = await scrape_company(
                client,
                company.get('company_name', ''),
                company.get('url', '')
            )
            await asyncio.sleep(0.2)  # インターバル
            return result

    # SSL検証無効でクライアント作成
    async with httpx.AsyncClient(verify=False) as client:
        tasks = [
            scrape_with_semaphore(client, company)
            for company in companies
        ]
        results = await asyncio.gather(*tasks)

    # スクレイピング結果のサマリーをログ出力
    results_list = list(results)
    total = len(results_list)
    success = sum(1 for r in results_list if r.contact_url or r.phone)
    top_failed = sum(1 for r in results_list if r.error == 'top_page_failed')
    mismatch = sum(1 for r in results_list if r.error == 'company_mismatch')
    no_contact = sum(1 for r in results_list if not r.error and not r.contact_url and not r.phone)

    logger.info(f"スクレイピング結果サマリー: 総数={total}, 成功={success}, トップページ失敗={top_failed}, 企業名不一致={mismatch}, 連絡先未検出={no_contact}")

    return results_list
