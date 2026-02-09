"""
LLM企業名クレンジングモジュール v3

v2からの変更点:
- 協会・団体・連盟を除外ルールに追加
- メディア・講座パターンを除外
- 企業名の後処理を追加（カッコ除去、全角正規化、法人格チェック）
- セーフティネットを大幅強化
"""

import logging
import json
import re
import unicodedata
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ====================================
# システムプロンプト v3
# ====================================
SYSTEM_PROMPT = """あなたは企業データクレンジングの専門家です。

## タスク
検索結果から**営業先になりうる民間企業**の情報のみを抽出・正規化してください。
**品質を最優先**にし、無効なデータは必ず除外してください。

## 処理ルール

### 1. 企業名の正規化（最重要）
**出力する企業名は「株式会社〇〇」「〇〇株式会社」「合同会社〇〇」「有限会社〇〇」の形式のみ。**
余計な修飾語、カッコ書きの補足、キャッチコピーは全て削除すること。

titleから正しい企業名を抽出する例：
- 「株式会社〇〇｜公式サイト」→「株式会社〇〇」
- 「株式会社〇〇（東証上場企業）」→「株式会社〇〇」（カッコ内を削除）
- 「〇〇 | 会社案内」→「株式会社〇〇」（URLドメインから法人格を推測）
- 「Ｓ ｋ ｙ株式会社」→「Sky株式会社」（全角→半角、不要スペース削除）
- 「沿革：〇〇株式会社」→「〇〇株式会社」

### 2. 必ず除外するもの

**A. 法人格がないもの**
法人格（株式会社/有限会社/合同会社）を含まず、ドメインからも正式名称が推測できないもの。
- 「テクノプロ」→ 法人格不明なので除外
- 「ITコミュニケーションズ」→ 法人格不明なので除外
※ドメインが「technopro.com」のように明確な場合は「テクノプロ株式会社」と補完してもよい

**B. 協会・団体・連盟・財団**
営業先にならないため全て除外：
- 一般社団法人、公益社団法人、一般財団法人、公益財団法人
- 〇〇協会、〇〇連盟、〇〇懇話会、〇〇連合会、〇〇機構

**C. メディア・出版**
- 「週刊〇〇」「日刊〇〇」「月刊〇〇」→ メディアなので除外
- 「〇〇新聞」「〇〇ニュース」→ 除外

**D. 教育・講座・スクール**
- 「〇〇講座」「〇〇養成」「〇〇スクール」「〇〇アカデミー」→ 除外
※ 企業が運営するスクールのページが引っかかった場合は、運営企業名が特定できる場合のみ残す

**E. その他除外対象**
- まとめ記事（「〇〇社を厳選」「おすすめ10選」）
- キャッチコピー（「〇〇なら」「〇〇をお探しなら」）
- 途中で切れた名前（「...」で終わる）
- 比較・マッチングサイト
- 求人サイト、SNS、ニュースサイト、Wikipedia
- 政府・自治体（.go.jp, .lg.jp）

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
}

relevance_scoreは0.1〜1.0の範囲。高い順にソートすること。"""


class LLMCleanser:
    """LLMを使用した企業データクレンジング v3"""

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
                logger.error(f"バッチ {batch_num} のクレンジングに完全失敗。{len(batch)}件を破棄。")
            else:
                all_cleansed.extend(cleansed_batch)
                logger.info(f"バッチ {batch_num}: {len(batch)}件 → {len(cleansed_batch)}件")

        excluded_count = len(companies) - len(all_cleansed)
        logger.info(
            f"LLMクレンジング完了: {len(companies)}件 → {len(all_cleansed)}件"
            f"（{excluded_count}件除外、{failed_batches}バッチ失敗）"
        )

        return all_cleansed

    async def _cleanse_batch_with_retry(self, batch, search_keyword, search_intent, existing_domains):
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._cleanse_batch(batch, search_keyword, search_intent, existing_domains)
            except Exception as e:
                logger.warning(f"クレンジング試行 {attempt + 1}/{self.MAX_RETRIES + 1} 失敗: {e}")
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

            # --- 後処理: 企業名を正規化 ---
            company_name = self._normalize_company_name(company_name)

            # --- セーフティネット: 無効な企業名を除外 ---
            if self._is_invalid_company_name(company_name):
                logger.debug(f"セーフティネットで除外: {company_name}")
                continue

            cleansed.append({
                "company_name": company_name,
                "url": url,
                "domain": domain or self._extract_domain(url),
                "relevance_score": cc.get("relevance_score", 0.5),
            })

        return cleansed

    # ====================================
    # 後処理: 企業名の正規化
    # ====================================
    def _normalize_company_name(self, name: str) -> str:
        """
        LLMの出力を後処理で正規化する。
        LLMが残した余計な修飾やフォーマットのズレを修正。
        """
        # 1. 全角英数字 → 半角に変換（Ｓｋｙ → Sky）
        name = unicodedata.normalize('NFKC', name)

        # 2. 不要なスペースを削除（S k y → Sky）
        #    ただし「株式会社 〇〇」のようなスペースは許容
        #    1文字ずつスペースで区切られているパターンを検出して詰める
        name = re.sub(r'(?<=\w) (?=\w(?:\b|$))', '', name)
        #    連続する1文字+スペースのパターン: "S k y" → "Sky"
        name = re.sub(r'\b(\w) (\w) (\w)\b', lambda m: m.group(1) + m.group(2) + m.group(3), name)

        # 3. カッコ内の修飾語を削除
        #    「株式会社〇〇（東証上場企業）」→「株式会社〇〇」
        #    「公益社団法人企業情報化協会（IT協会）」→「公益社団法人企業情報化協会」
        name = re.sub(r'[（(][^）)]*[）)]', '', name)

        # 4. 先頭/末尾の閉じカッコ・開きカッコを削除
        #    「ITエンジニア養成講座）」→「ITエンジニア養成講座」
        name = re.sub(r'^[）)]+|[（(]+$', '', name)
        name = re.sub(r'^[）)]+|[）)]+$', '', name)

        # 5. 全角スペース → 半角スペース → 連続スペース除去
        name = name.replace('\u3000', ' ')
        name = re.sub(r' +', ' ', name)

        # 6. 前後の空白を除去
        name = name.strip()

        return name

    # ====================================
    # セーフティネット: 無効な企業名の検出
    # ====================================
    def _is_invalid_company_name(self, name: str) -> bool:
        """
        LLMが見逃した無効な企業名をコードで検出。
        Trueを返したら除外する。
        """
        # --- 長さチェック ---
        if len(name) > 50:
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
        if re.search(r'協会|連盟|懇話会|連合会|機構|組合(?!せ)', name):
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
        if re.search(r'TOP\d+|トップ\d+', name, re.IGNORECASE):
            return True

        # --- キャッチコピーパターン ---
        if re.search(r'なら$|をお探し', name):
            return True
        if '！' in name or '!' in name:
            return True

        # --- 就活・求人パターン ---
        if re.search(r'就活|キャリア|新卒|転職|求人|採用', name):
            return True
        if re.search(r'向け$', name):
            return True

        # --- 法人格チェック ---
        # 株式会社/有限会社/合同会社/合名会社/合資会社のいずれも含まない場合は除外
        has_corporate_type = bool(re.search(
            r'株式会社|有限会社|合同会社|合名会社|合資会社|'
            r'Inc\.|Corp\.|Co\.,?\s*Ltd\.|LLC|LLP',
            name, re.IGNORECASE
        ))
        if not has_corporate_type:
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


# ====================================
# ヘルパー関数（後方互換）
# ====================================
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