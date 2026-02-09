"""
LLM企業名クレンジングモジュール v2
Difyワークフロー仕様に完全準拠

OpenAI GPT-4oを使用して:
1. 検索結果から有効な企業情報を抽出・正規化
2. 企業HPではないサイト（比較サイト、イベント、協会等）を除外
3. 関連性スコアリング
"""

import logging
import json
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ====================================
# システムプロンプト（品質重視版）
# ====================================
SYSTEM_PROMPT = """あなたは企業データクレンジングの専門家です。

## タスク
検索結果から有効な企業情報を抽出・正規化してください。
**品質を最優先**にし、無効なデータは必ず除外してください。

## 処理ルール

### 1. 企業名の正規化（最重要）
**出力する企業名は正式な法人名のみにする。**

titleから正しい企業名を抽出する例：
- 「株式会社〇〇｜公式サイト」→「株式会社〇〇」
- 「〇〇 | 会社案内」→「株式会社〇〇」（URLドメインから法人格を推測）
- 「〇〇 - 東京都渋谷区のIT企業」→「株式会社〇〇」（法人格を補完）
- 「idealogical Japan合同会社 | IT コンサルティン」→「idealogical Japan合同会社」
- 「沿革：〇〇株式会社」→「〇〇株式会社」（接頭辞を削除）

**以下は必ず除外：**
- 企業名が抽出できないもの（「ホームページ制作」「Webサイト制作・CMS開発」等のサービス名のみ）
- キャッチコピー（「〇〇なら」「〇〇をお探しなら」「現場と経営に強い〜」）
- まとめ記事（「〇〇社を厳選」「おすすめ10選」「〇〇 比較」）
- 途中で切れている不完全な名前（「...」で終わるなど）
- 法人格（株式会社/有限会社/合同会社/一般社団法人）を含まず、かつドメインからも推測不可能なもの
- 「学生が独自性を持って学業に取り組めるようにサポート」のような文章

### 2. URL正規化
- サブページURL → トップページURLに変換
  例: https://example.co.jp/blog/123 → https://example.co.jp/
  例: https://example.co.jp/about/history → https://example.co.jp/
- ただしトップページが存在しない場合はそのまま残す

### 3. 除外対象
以下のドメインは必ず除外：
- 求人サイト（indeed, mynavi, rikunabi, doda, en-japan, baitoru等）
- SNS（twitter, facebook, instagram, youtube, tiktok等）
- ニュースサイト（yahoo, nikkei, asahi, yomiuri等）
- Wikipedia
- 企業紹介・口コミサイト（baseconnect, wantedly, openwork, vorkers等）
- 政府・自治体サイト（.go.jp, .lg.jp）
- 比較・マッチングサイト（〇〇幹事、比較ビズ、一括見積もり、発注ナビ等）
- まとめ・ランキングサイト（企業リストを紹介しているだけのページ）

### 4. 重複排除
- 同一ドメインの企業は1つだけ残す

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
    """
    LLMを使用した企業データクレンジング v2

    変更点:
    - gpt-4o-mini → gpt-4o
    - target_count強制を削除（品質重視）
    - search_intent, existing_domainsを追加
    - エラー時に元データを返さない
    - リトライ機能追加
    """

    API_URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o"  # gpt-4o-mini から変更
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
        """
        企業リストをLLMでクレンジング

        Args:
            companies: [{"company_name": "...", "url": "...", "domain": "..."}, ...]
            search_keyword: 検索キーワード
            search_intent: 検索意図（LLMクエリ生成で作成された構造化データ）
            existing_domains: マスターシートの既存ドメイン（除外用）
            batch_size: 一度に処理する件数（gpt-4oなら50件でも安定）

        Returns:
            クレンジング済みの企業リスト（無効な企業は除外済み）
        """
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
                # リトライ全失敗 → このバッチは破棄（元データを入れない）
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

    async def _cleanse_batch_with_retry(
        self,
        batch: list[dict],
        search_keyword: str,
        search_intent: dict,
        existing_domains: list[str],
    ) -> Optional[list[dict]]:
        """リトライ付きバッチクレンジング"""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._cleanse_batch(
                    batch, search_keyword, search_intent, existing_domains
                )
            except Exception as e:
                logger.warning(f"クレンジング試行 {attempt + 1}/{self.MAX_RETRIES + 1} 失敗: {e}")
                if attempt == self.MAX_RETRIES:
                    return None  # 全リトライ失敗 → Noneを返す（元データは返さない）

    async def _cleanse_batch(
        self,
        batch: list[dict],
        search_keyword: str,
        search_intent: dict,
        existing_domains: list[str],
    ) -> list[dict]:
        """バッチ単位でクレンジング"""

        # 入力データを整形
        input_data = []
        for i, c in enumerate(batch):
            input_data.append({
                "index": i + 1,
                "title": c.get("company_name", ""),
                "url": c.get("url", ""),
                "domain": c.get("domain", ""),
            })

        user_prompt = self._create_user_prompt(
            input_data, search_keyword, search_intent, existing_domains
        )

        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,  # 0.2から下げて安定性向上
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                self.API_URL,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)

        cleaned_companies = result.get("cleaned_companies", [])

        # 結果をマージ
        cleansed = []
        for cc in cleaned_companies:
            company_name = cc.get("company_name", "").strip()
            url = cc.get("url", "").strip()
            domain = cc.get("domain", "").strip()

            if not company_name or not url:
                continue

            # 追加の品質チェック（LLMが見逃した場合のセーフティネット）
            if self._is_invalid_company_name(company_name):
                logger.debug(f"品質チェックで除外: {company_name}")
                continue

            cleansed.append({
                "company_name": company_name,
                "url": url,
                "domain": domain or self._extract_domain(url),
                "relevance_score": cc.get("relevance_score", 0.5),
            })

        return cleansed

    def _is_invalid_company_name(self, name: str) -> bool:
        """
        LLMが見逃した無効な企業名を検出（セーフティネット）
        """
        # 明らかに長すぎる（ページタイトルがそのまま入っている）
        if len(name) > 50:
            return True

        # 「|」「｜」が残っている（タイトル区切りが除去されていない）
        if '|' in name or '｜' in name:
            return True

        # 【】が含まれている（まとめ記事のタイトル）
        if '【' in name or '】' in name:
            return True

        # 「...」「…」で終わる（途中で切れている）
        if name.endswith('...') or name.endswith('…'):
            return True

        # 「〇〇なら」「〇〇をお探し」パターン
        if re.search(r'なら$|をお探し', name):
            return True

        # 「〇〇選」「厳選」「比較」「おすすめ」「ランキング」（まとめ記事）
        if re.search(r'\d+選|厳選|比較|おすすめ|ランキング', name):
            return True

        # TOP〇〇（ランキング記事）
        if re.search(r'TOP\d+|トップ\d+', name, re.IGNORECASE):
            return True

        # 就活・キャリア系サイト名
        if re.search(r'就活|キャリア|新卒|転職|求人|採用', name):
            return True

        # 「〇〇向け」パターン（「就活生向け」「エンジニア向け」等）
        if re.search(r'向け', name):
            return True

        # 「！」が含まれている（キャッチコピー的なタイトル）
        if '！' in name or '!' in name:
            return True

        return False

    def _extract_domain(self, url: str) -> str:
        """URLからドメインを抽出"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    def _create_user_prompt(
        self,
        input_data: list[dict],
        search_keyword: str,
        search_intent: dict,
        existing_domains: list[str],
    ) -> str:
        """ユーザープロンプトを作成"""
        data_json = json.dumps(input_data, ensure_ascii=False, indent=2)

        # 検索意図セクション
        intent_section = ""
        if search_intent:
            intent_json = json.dumps(search_intent, ensure_ascii=False, indent=2)
            intent_section = f"""## 検索意図
{intent_json}

"""

        # 既存ドメインセクション
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
    """後方互換用ヘルパー"""
    if not api_key:
        return companies
    cleanser = LLMCleanser(api_key)
    return await cleanser.cleanse_companies(
        companies, search_keyword, search_intent, existing_domains
    )
