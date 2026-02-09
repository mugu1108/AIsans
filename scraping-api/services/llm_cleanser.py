import logging
import json
import re
import unicodedata
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """あなたは企業データクレンジングの専門家です。

## タスク
検索結果から**営業先になりうる民間企業**の情報のみを抽出・正規化してください。
**品質を最優先**にし、無効なデータは必ず除外してください。

## 処理ルール

### 1. 企業名の正規化（最重要）
**出力する企業名は正式な法人名のみにする。余計なものは全て削除。**

具体例：
- 「株式会社〇〇｜公式サイト」→「株式会社〇〇」（パイプ以降を削除）
- 「株式会社〇〇（東証上場企業）」→「株式会社〇〇」（カッコ内を削除）
- 「株式会社〇〇のホームページ」→「株式会社〇〇」（「のホームページ」を削除）
- 「株式会社LIG(リグ)」→「株式会社LIG」（読み仮名カッコを削除）
- 「Ｓ ｋ ｙ株式会社」→「Sky株式会社」（全角→半角、不要スペース削除）
- 「沿革：〇〇株式会社」→「〇〇株式会社」（接頭辞を削除）
- 「Idealogical Japan合同会社 | ITコンサルティング」→「Idealogical Japan合同会社」

### 2. 必ず除外するもの

**A. 法人格がないもの**
- 「テクノプロ」「ITコミュニケーションズ」「IT.ini」→ 法人格不明なので除外

**B. キャッチコピー・文章**
- 「上京を志す、就活生へ。ジョーカツ」→ キャッチコピーなので除外
- 「経営をITと財務の面から支援する合同会社」→ 文章なので除外
- 「WebマーケティングコンサルティングならWEB」→ キャッチコピーなので除外
- 法人名の前に修飾文がつく場合（「〇〇を支援する株式会社〇〇」）→ 除外

**C. 協会・団体・連盟**
- 一般社団法人、公益社団法人、協会、連盟、懇話会 → 全て除外

**D. メディア・教育**
- 「週刊〇〇」「〇〇講座」「〇〇養成」→ 除外

**E. その他**
- まとめ記事、比較サイト、求人サイト、SNS、Wikipedia → 除外
- 政府・自治体（.go.jp, .lg.jp）→ 除外

### 3. URL正規化
- サブページ → トップページに変換

### 4. 重複排除
- 同一ドメインは1つだけ残す

## 出力形式
必ず以下のJSON形式のみで出力（説明文不要）：
{
  "cleaned_companies": [
    {
      "company_name": "株式会社〇〇",
      "url": "https://example.co.jp/",
      "domain": "example.co.jp",
      "relevance_score": 0.95
    }
  ],
  "excluded_count": 5,
  "valid_count": 25
}"""


class LLMCleanser:
    """LLMを使用した企業データクレンジング v4"""

    API_URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o"
    MAX_RETRIES = 2

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def cleanse_companies(
        self,
        companies: list[dict],
        search_keyword: str,
        search_intent: dict = None,
        existing_domains: list[str] = None,
        batch_size: int = 50,
    ) -> list[dict]:
        if not self.api_key:
            logger.warning("OpenAI APIキーが設定されていません。クレンジングをスキップします。")
            return companies
        if not companies:
            return companies
        if existing_domains is None:
            existing_domains = []

        logger.info(f"LLMクレンジング開始: {len(companies)}件（キーワード: {search_keyword}）")

        all_cleansed = []
        failed_batches = 0

        for i in range(0, len(companies), batch_size):
            batch = companies[i:i + batch_size]
            batch_num = i // batch_size + 1

            cleansed_batch = await self._cleanse_batch_with_retry(
                batch, search_keyword, search_intent, existing_domains
            )
            if cleansed_batch is None:
                failed_batches += 1
                logger.error(f"バッチ {batch_num} 完全失敗。{len(batch)}件を破棄。")
            else:
                all_cleansed.extend(cleansed_batch)
                logger.info(f"バッチ {batch_num}: {len(batch)}件 → {len(cleansed_batch)}件")

        excluded = len(companies) - len(all_cleansed)
        logger.info(f"LLMクレンジング完了: {len(companies)}件 → {len(all_cleansed)}件（{excluded}件除外）")
        return all_cleansed

    async def _cleanse_batch_with_retry(self, batch, search_keyword, search_intent, existing_domains):
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._cleanse_batch(batch, search_keyword, search_intent, existing_domains)
            except Exception as e:
                logger.warning(f"試行 {attempt + 1}/{self.MAX_RETRIES + 1} 失敗: {e}")
                if attempt == self.MAX_RETRIES:
                    return None

    async def _cleanse_batch(self, batch, search_keyword, search_intent, existing_domains):
        input_data = []
        for i, c in enumerate(batch):
            input_data.append({
                "index": i + 1,
                "title": c.get("company_name", ""),
                "url": c.get("url", ""),
                "domain": c.get("domain", ""),
            })

        user_prompt = self._create_user_prompt(input_data, search_keyword, search_intent, existing_domains)

        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(self.API_URL, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        cleaned_companies = result.get("cleaned_companies", [])

        cleansed = []
        for cc in cleaned_companies:
            company_name = cc.get("company_name", "").strip()
            url = cc.get("url", "").strip()
            domain = cc.get("domain", "").strip()

            if not company_name or not url:
                continue

            # STEP 1: 後処理で正規化
            original_name = company_name
            company_name = self._normalize_company_name(company_name)
            if company_name != original_name:
                logger.debug(f"後処理で正規化: {original_name} → {company_name}")

            # STEP 2: セーフティネットで無効チェック
            if self._is_invalid_company_name(company_name):
                logger.info(f"セーフティネットで除外: {company_name}")
                continue

            cleansed.append({
                "company_name": company_name,
                "url": url,
                "domain": domain or self._extract_domain(url),
                "relevance_score": cc.get("relevance_score", 0.5),
            })

        logger.info(f"LLM出力: {len(cleaned_companies)}件 → 後処理後: {len(cleansed)}件")
        return cleansed

    # ====================================
    # 後処理: 企業名の正規化
    # ====================================
    def _normalize_company_name(self, name: str) -> str:
        """LLM出力の企業名を後処理で正規化する"""

        # 1. 全角英数字 → 半角（Ｓｋｙ → Sky、ＩＴ → IT）
        name = unicodedata.normalize('NFKC', name)

        # 2. パイプ以降を削除（「〇〇合同会社 | ITコンサル」→「〇〇合同会社」）
        name = re.split(r'\s*[|｜]\s*', name)[0].strip()

        # 3. カッコ内を削除（全角・半角両方）
        #    「株式会社LIG(リグ)」→「株式会社LIG」
        #    「合同会社シストリー（Cistree.llc）」→「合同会社シストリー」
        #    「公益社団法人企業情報化協会（IT協会）」→「公益社団法人企業情報化協会」
        name = re.sub(r'\s*[（(][^）)]*[）)]\s*', '', name)

        # 4. 残った孤立カッコを除去（「ITエンジニア養成講座）」→「ITエンジニア養成講座」）
        name = re.sub(r'[（()）]', '', name)

        # 5. 「のホームページ」「の公式サイト」等の接尾辞を除去
        name = re.sub(r'の(ホームページ|公式サイト|公式ホームページ|ウェブサイト|HP|Webサイト|WEBサイト|オフィシャルサイト)$', '', name)

        # 6. 「〇〇へようこそ」パターン
        name = re.sub(r'へようこそ$', '', name)

        # 7. 先頭の接頭辞を除去（「沿革：」「会社概要 - 」等）
        name = re.sub(r'^(沿革|会社概要|企業情報|会社案内|トップページ|HOME|ホーム)\s*[:：\-\|]\s*', '', name)

        # 7.5 「〇〇なら株式会社〇〇」パターンを除去
        name = re.sub(r'^.+なら(株式会社|有限会社|合同会社|合名会社|合資会社)', r'\1', name)
        # 8. 1文字ずつスペースで区切られたパターンを修正（「S k y」→「Sky」）
        #    アルファベットが1文字ずつスペース区切りになっているケース
        def fix_spaced_chars(m):
            return m.group(0).replace(' ', '')
        name = re.sub(r'\b[A-Za-z](?: [A-Za-z]){2,}\b', fix_spaced_chars, name)

        # 9. 全角スペース → 半角、連続スペース除去
        name = name.replace('\u3000', ' ')
        name = re.sub(r' +', ' ', name)

        # 10. 前後空白除去
        name = name.strip()

        return name

    # ====================================
    # セーフティネット: 無効な企業名の検出
    # ====================================
    def _is_invalid_company_name(self, name: str) -> bool:
        """Trueを返したら除外する"""

        # --- 基本チェック ---
        if len(name) > 40:
            return True
        if len(name) < 3:
            return True

        # --- タイトル区切り文字が残っている ---
        if '|' in name or '｜' in name:
            return True
        if '【' in name or '】' in name:
            return True

        # --- 途中で切れている ---
        if name.endswith('...') or name.endswith('…'):
            return True

        # --- 協会・団体・連盟・財団 ---
        if re.search(r'協会|連盟|懇話会|連合会|機構$|組合(?!せ)', name):
            return True
        if re.search(r'一般社団法人|公益社団法人|一般財団法人|公益財団法人', name):
            return True

        # --- メディア・出版 ---
        if re.search(r'^週刊|^日刊|^月刊|新聞社?$|ニュース$|メディア$', name):
            return True

        # --- 教育・講座 ---
        if re.search(r'講座|養成|スクール$|アカデミー$|塾$|学校$|学園$', name):
            return True

        # --- まとめ記事パターン ---
        if re.search(r'\d+選|厳選|比較|おすすめ|ランキング', name):
            return True

        # --- キャッチコピーパターン（拡張版） ---
        if re.search(r'なら.{0,5}$', name):  # 「ならWE」「ならWEB」等もキャッチ
            return True
        if re.search(r'をお探し|を志す|を支援する|を実現|をサポート|を提供する', name):
            return True
        if '！' in name or '!' in name:
            return True
        if '。' in name or '、' in name:  # 句読点が含まれる = 文章
            return True

        # --- 就活・求人パターン ---
        if re.search(r'就活|キャリア|新卒|転職|求人|採用', name):
            return True

        # --- 文章パターン（「〇〇する株式会社」「〇〇を△△する合同会社」） ---
        #    正常: 「株式会社〇〇」「〇〇株式会社」（法人格が先頭 or 末尾付近）
        #    異常: 「経営をITと財務の面から支援する合同会社」（法人格の前に長い文章）
        corporate_match = re.search(r'(株式会社|有限会社|合同会社|合名会社|合資会社)', name)
        if corporate_match:
            pos = corporate_match.start()
            before_corporate = name[:pos]
            # 法人格の前に10文字以上の文章がある場合は異常
            if len(before_corporate) > 10:
                return True
            # 法人格の前に動詞的な表現がある場合は異常
            if re.search(r'する$|から$|へ$|を$|の面から$', before_corporate):
                return True

        # --- 法人格チェック（最終防衛ライン） ---
        has_corporate = bool(re.search(
            r'株式会社|有限会社|合同会社|合名会社|合資会社|'
            r'Inc\.?|Corp\.?|Co\.?,?\s*Ltd\.?|LLC|LLP|Limited',
            name, re.IGNORECASE
        ))
        if not has_corporate:
            return True

        return False

    def _extract_domain(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    def _create_user_prompt(self, input_data, search_keyword, search_intent, existing_domains):
        data_json = json.dumps(input_data, ensure_ascii=False, indent=2)

        intent_section = ""
        if search_intent:
            intent_json = json.dumps(search_intent, ensure_ascii=False, indent=2)
            intent_section = f"""## 検索意図
{intent_json}

"""
        existing_section = ""
        if existing_domains:
            domains_json = json.dumps(existing_domains[:100], ensure_ascii=False)
            existing_section = f"""## 既存企業ドメイン（必ず除外）
{domains_json}

"""

        return f"""## 検索キーワード
{search_keyword}

{intent_section}{existing_section}## 検索結果データ（{len(input_data)}件）
{data_json}

上記の検索結果をクレンジングし、有効な企業リストをJSON形式で出力してください。
**品質重視**: 企業名が正しく抽出できないものは除外してください。
{f'**「既存企業ドメイン」に含まれるドメインは必ず除外してください。**' if existing_domains else ''}"""


async def cleanse_company_names(
    api_key: str,
    companies: list[dict],
    search_keyword: str = "",
    search_intent: dict = None,
    existing_domains: list[str] = None,
) -> list[dict]:
    if not api_key:
        return companies
    cleanser = LLMCleanser(api_key)
    return await cleanser.cleanse_companies(
        companies, search_keyword, search_intent, existing_domains
    )