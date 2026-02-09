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


# Dify仕様のシステムプロンプト
SYSTEM_PROMPT = """あなたは企業データクレンジングの専門家です。

## タスク
検索結果から「企業の公式HP」のみを抽出・正規化してください。
企業HPではないサイトは必ず除外してください。

## 処理ルール

### 1. 企業名の正規化
検索結果のtitleから正しい企業名を抽出：
- 「株式会社〇〇｜公式サイト」→「株式会社〇〇」
- 「〇〇 | 会社案内」→「株式会社〇〇」または「〇〇株式会社」
- 「沿革：〇〇株式会社」→「〇〇株式会社」（余分な接頭辞を削除）

### 2. 必ず除外するもの（企業HPではない）
以下は**絶対に含めないでください**：

**比較・マッチングサイト**
- 「〇〇比較」「比較ビズ」「一括見積もり」などの比較サイト
- 企業紹介・マッチングサービス

**イベント・展示会サイト**
- 「〇〇展」「〇〇EXPO」「CEATEC」などのイベントサイト
- 展示会・カンファレンスのサイト

**リスト・名簿販売サイト**
- 「企業リスト」「法人名簿」「リストマーケット」などのリスト販売

**業界団体・協会**
- 「〇〇協会」「〇〇連盟」「〇〇連合会」「〇〇工業会」
- 商工会議所、業界団体

**施設・地名**
- 「〇〇工場」のみの施設名
- 地名のみ（「横山町・馬喰町」など）
- 「〇〇センター」などの施設名

**その他除外**
- 求人サイト（indeed, mynavi, rikunabi, doda等）
- SNS（twitter, facebook, instagram, youtube等）
- ニュースサイト（yahoo, nikkei, asahi等）
- Wikipedia
- 企業情報サイト（baseconnect, wantedly, openwork等）
- 政府・自治体サイト（.go.jp, .lg.jp）
- ブログ記事、個人サイト
- 企業名が全く抽出できないもの
- キャッチフレーズのみ（「地域とともに」など）
- 不完全な名前（「カンパニー」「継手 バルブ 製造・販売」など）

### 3. 含めるもの（企業HP）
以下のみを含めてください：
- 株式会社〇〇、〇〇株式会社
- 有限会社〇〇、〇〇有限会社
- 合同会社〇〇
- 〇〇Inc.、〇〇Corp.などの企業

### 4. 関連性判定
検索キーワードに対して関連性が低い企業も除外：
- 検索キーワードの業種・地域と明らかに無関係な企業"""


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
        # 入力データを整形
        input_data = []
        for i, c in enumerate(batch):
            input_data.append({
                "index": i + 1,
                "title": c.get("company_name", ""),
                "url": c.get("url", ""),
                "domain": c.get("domain", ""),
            })

        user_prompt = self._create_user_prompt(input_data, search_keyword)

        # API呼び出し
        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
        valid_companies = result.get("valid_companies", [])

        # 結果をマージ（有効な企業のみ返す）
        cleansed = []
        for vc in valid_companies:
            idx = vc.get("index", 0) - 1
            if 0 <= idx < len(batch):
                original = batch[idx]
                new_company = original.copy()
                # 正規化された企業名を使用
                new_name = vc.get("company_name", "")
                if new_name:
                    if new_name != original.get("company_name", ""):
                        logger.debug(f"企業名正規化: {original.get('company_name', '')} → {new_name}")
                    new_company["company_name"] = new_name
                    cleansed.append(new_company)

        return cleansed

    def _create_user_prompt(
        self,
        input_data: list[dict],
        search_keyword: str,
    ) -> str:
        """
        ユーザープロンプトを作成
        """
        data_json = json.dumps(input_data, ensure_ascii=False, indent=2)

        return f"""## 検索キーワード
{search_keyword}

## 検索結果データ
{data_json}

## 指示
上記の検索結果から、「企業の公式HP」のみを抽出してください。
企業HPではないサイト（比較サイト、イベント、協会、リスト販売等）は除外してください。

## 出力形式（JSON）
{{
  "valid_companies": [
    {{
      "index": 1,
      "company_name": "株式会社〇〇",
      "reason": "製造業の企業HP"
    }},
    ...
  ],
  "excluded": [
    {{
      "index": 2,
      "reason": "比較サイトのため除外"
    }},
    ...
  ],
  "summary": {{
    "input_count": {len(input_data)},
    "valid_count": 5,
    "excluded_count": 3
  }}
}}

valid_companiesには企業HPのみを含めてください。
indexは入力データの番号と一致させてください。"""


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
