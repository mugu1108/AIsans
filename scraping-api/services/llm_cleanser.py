"""
LLM企業名クレンジングモジュール
OpenAI GPT-4o-miniを使用して検索結果のタイトルから正しい企業名を抽出
"""

import logging
import json
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class LLMCleanser:
    """
    LLMを使用した企業名クレンジング

    検索結果のタイトル（例: "株式会社〇〇｜公式サイト"）から
    正しい企業名（例: "株式会社〇〇"）を抽出する
    """

    API_URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o-mini"  # コスト効率重視

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def cleanse_company_names(
        self,
        companies: list[dict],
        batch_size: int = 20,
    ) -> list[dict]:
        """
        企業名をLLMでクレンジング

        Args:
            companies: [{"company_name": "...", "url": "...", ...}, ...]
            batch_size: 一度に処理する件数

        Returns:
            クレンジング済みの企業リスト
        """
        if not self.api_key:
            logger.warning("OpenAI APIキーが設定されていません。クレンジングをスキップします。")
            return companies

        if not companies:
            return companies

        logger.info(f"LLMクレンジング開始: {len(companies)}件")

        # バッチ処理
        cleansed_companies = []
        for i in range(0, len(companies), batch_size):
            batch = companies[i:i + batch_size]
            try:
                cleansed_batch = await self._cleanse_batch(batch)
                cleansed_companies.extend(cleansed_batch)
                logger.debug(f"バッチ {i // batch_size + 1} 完了: {len(cleansed_batch)}件")
            except Exception as e:
                logger.warning(f"バッチ {i // batch_size + 1} でエラー: {e}")
                # エラー時は元のデータをそのまま使用
                cleansed_companies.extend(batch)

        logger.info(f"LLMクレンジング完了: {len(cleansed_companies)}件")
        return cleansed_companies

    async def _cleanse_batch(self, batch: list[dict]) -> list[dict]:
        """
        バッチ単位でクレンジング
        """
        # プロンプト作成
        titles = [c.get("company_name", "") for c in batch]
        prompt = self._create_prompt(titles)

        # API呼び出し
        payload = {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "あなたは企業名抽出の専門家です。検索結果のタイトルから正確な企業名のみを抽出してください。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
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
        cleansed_names = result.get("companies", [])

        # 結果をマージ
        cleansed_batch = []
        for i, company in enumerate(batch):
            new_company = company.copy()
            if i < len(cleansed_names) and cleansed_names[i]:
                original = company.get("company_name", "")
                cleansed = cleansed_names[i]
                if cleansed != original:
                    logger.debug(f"企業名変換: {original} → {cleansed}")
                new_company["company_name"] = cleansed
            cleansed_batch.append(new_company)

        return cleansed_batch

    def _create_prompt(self, titles: list[str]) -> str:
        """
        クレンジング用プロンプトを作成
        """
        titles_text = "\n".join([f"{i+1}. {title}" for i, title in enumerate(titles)])

        return f"""以下の検索結果タイトルから、正確な企業名のみを抽出してください。

【ルール】
1. 「株式会社〇〇」「〇〇株式会社」「有限会社〇〇」「合同会社〇〇」の形式で抽出
2. 「｜公式サイト」「- 会社概要」などの余分な部分は除去
3. 「東京の」「おすすめ」などの修飾語は除去
4. 求人サイト・まとめサイトの場合は空文字を返す
5. 企業名が特定できない場合は空文字を返す

【入力タイトル】
{titles_text}

【出力形式】
JSON形式で、以下のように番号順に企業名を配列で返してください：
{{"companies": ["株式会社〇〇", "〇〇有限会社", "", ...]}}

空文字は企業名が抽出できなかった場合です。"""


async def cleanse_company_names(
    api_key: str,
    companies: list[dict],
) -> list[dict]:
    """
    企業名クレンジングのヘルパー関数

    Args:
        api_key: OpenAI APIキー
        companies: 企業リスト

    Returns:
        クレンジング済みの企業リスト
    """
    if not api_key:
        return companies

    cleanser = LLMCleanser(api_key)
    return await cleanser.cleanse_company_names(companies)
