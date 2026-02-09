"""
LLM企業名クレンジングモジュール
Difyワークフロー仕様に完全準拠

OpenAI GPT-4o-miniを使用して:
1. 検索結果から有効な企業情報を抽出・正規化
2. 企業HPではないサイト（比較サイト、イベント、協会等）を除外
3. 関連性スコアリング
"""

import logging
import json
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# Dify仕様のシステムプロンプト（テンプレート）
SYSTEM_PROMPT_TEMPLATE = """あなたは企業データクレンジングの専門家です。

## タスク
検索結果から有効な企業情報を抽出・正規化してください。

## ★重要★
**できるだけ多くの有効な企業を出力してください（目標: {target_count}件）。**
入力データに{target_count}件以上の候補がある場合、出力が{target_count}件未満になることは許されません。
{target_count}件に満たない場合は基準を緩和し、企業名が不完全でもドメインから推測できるなら残してください。

## 処理ルール

### 1. 企業名の正規化
検索結果のtitleから正しい企業名を抽出：
- 「株式会社〇〇｜公式サイト」→「株式会社〇〇」
- 「〇〇 | 会社案内」→「株式会社〇〇」または「〇〇株式会社」
- 「はじめまして、〇〇のブログ」→ 企業名が不明なら除外
- 「横浜工場」のような施設名のみは除外
- 「沿革：〇〇株式会社」→「〇〇株式会社」（余分な接頭辞を削除）
- 「カンパニー」「継手 バルブ 製造・販売」などの不完全な名前は除外

### 2. URL正規化
- ブログ記事URL → トップページURLに変換
  例: https://example.co.jp/blog/123 → https://example.co.jp/
- 部門ページURL → トップページURLに変換
  例: https://example.co.jp/about/history → https://example.co.jp/

### 3. 除外対象（これらのみ除外、迷ったら残す）
以下は必ず除外：
- 求人サイト（indeed, mynavi, rikunabi, doda, en-japan, baitoru等）
- SNS（twitter, facebook, instagram, youtube, tiktok等）
- ニュースサイト（yahoo, nikkei, asahi, yomiuri等）
- Wikipedia
- 企業紹介サイト（baseconnect, wantedly, openwork, vorkers等）
- 政府・自治体サイト（.go.jp, .lg.jp）
- 比較・マッチングサイト（〇〇幹事、比較ビズ、一括見積もり等）
- 企業名が全く抽出できずドメインからも推測不可能なもの
**上記に該当しないものは必ず残してください。迷ったら残す。**

### 4. 重複排除
- 同一ドメインの企業は1つだけ残す"""


class LLMCleanser:
    """
    LLMを使用した企業データクレンジング（Dify仕様準拠）

    - 企業名の正規化
    - 非企業サイトの除外（比較サイト、イベント、協会等）
    - 関連性スコアリング
    """

    API_URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o-mini"

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
        batch_size: int = 30,
    ) -> list[dict]:
        """
        企業リストをLLMでクレンジング（Dify仕様準拠）

        Args:
            companies: [{"company_name": "...", "url": "...", "domain": "..."}, ...]
            search_keyword: 検索キーワード（関連性判定に使用）
            batch_size: 一度に処理する件数

        Returns:
            クレンジング済みの企業リスト（無効な企業は除外済み）
        """
        if not self.api_key:
            logger.warning("OpenAI APIキーが設定されていません。クレンジングをスキップします。")
            return companies

        if not companies:
            return companies

        logger.info(f"LLMクレンジング開始: {len(companies)}件（キーワード: {search_keyword}）")

        # バッチ処理
        all_cleansed = []
        for i in range(0, len(companies), batch_size):
            batch = companies[i:i + batch_size]
            try:
                cleansed_batch = await self._cleanse_batch(batch, search_keyword)
                all_cleansed.extend(cleansed_batch)
                logger.debug(f"バッチ {i // batch_size + 1} 完了: {len(batch)}件 → {len(cleansed_batch)}件")
            except Exception as e:
                logger.warning(f"バッチ {i // batch_size + 1} でエラー: {e}")
                # エラー時は元のデータをそのまま使用（安全側に倒す）
                all_cleansed.extend(batch)

        # 除外された件数をログ
        excluded_count = len(companies) - len(all_cleansed)
        logger.info(f"LLMクレンジング完了: {len(companies)}件 → {len(all_cleansed)}件（{excluded_count}件除外）")

        return all_cleansed

    async def _cleanse_batch(
        self,
        batch: list[dict],
        search_keyword: str,
    ) -> list[dict]:
        """
        バッチ単位でクレンジング
        """
        target_count = len(batch)  # バッチサイズを目標件数とする

        # システムプロンプトにtarget_countを埋め込む
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(target_count=target_count)

        # 入力データを整形
        input_data = []
        for i, c in enumerate(batch):
            input_data.append({
                "index": i + 1,
                "title": c.get("company_name", ""),
                "url": c.get("url", ""),
                "domain": c.get("domain", ""),
            })

        user_prompt = self._create_user_prompt(input_data, search_keyword, target_count)

        # API呼び出し
        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.API_URL,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # レスポンス解析
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)

        # Dify仕様: cleaned_companies を使用
        cleaned_companies = result.get("cleaned_companies", [])

        # 結果をマージ（有効な企業のみ返す）
        cleansed = []
        for cc in cleaned_companies:
            # company_name, url, domain を直接取得（Dify仕様）
            company_name = cc.get("company_name", "")
            url = cc.get("url", "")
            domain = cc.get("domain", "")

            if company_name and url:
                cleansed.append({
                    "company_name": company_name,
                    "url": url,
                    "domain": domain or self._extract_domain(url),
                })

        return cleansed

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
        target_count: int,
    ) -> str:
        """
        ユーザープロンプトを作成（Dify仕様準拠）
        """
        data_json = json.dumps(input_data, ensure_ascii=False, indent=2)

        return f"""## 検索キーワード
{search_keyword}

## 目標件数
{target_count}件

## 検索結果データ
{data_json}

## 指示
上記の検索結果から有効な企業情報を抽出・正規化してください。
目標は{target_count}件です。迷ったら残す方向で判断してください。

## 出力形式（JSON）
必ず以下の形式のみで出力（説明文不要）：
{{
  "cleaned_companies": [
    {{
      "company_name": "株式会社〇〇",
      "url": "https://example.co.jp/",
      "domain": "example.co.jp",
      "relevance_score": 0.95
    }}
  ],
  "excluded_count": 5,
  "valid_count": 25
}}

relevance_scoreは0.1〜1.0の範囲で設定。
relevance_scoreが高い順にソートしてください。"""


# 後方互換性のための旧インターフェース
async def cleanse_company_names(
    api_key: str,
    companies: list[dict],
    search_keyword: str = "",
) -> list[dict]:
    """
    企業名クレンジングのヘルパー関数（後方互換性用）

    Args:
        api_key: OpenAI APIキー
        companies: 企業リスト
        search_keyword: 検索キーワード

    Returns:
        クレンジング済みの企業リスト
    """
    if not api_key:
        return companies

    cleanser = LLMCleanser(api_key)
    return await cleanser.cleanse_companies(companies, search_keyword)
