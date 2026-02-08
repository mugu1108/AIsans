"""
Google Apps Script クライアント
既存リストの取得とスプレッドシート保存
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class GASClient:
    """GAS Webhookクライアント"""

    def __init__(self, webhook_url: str, timeout: float = 300.0):
        """
        Args:
            webhook_url: GAS WebアプリのURL
            timeout: タイムアウト秒数
        """
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def get_existing_domains(self) -> set[str]:
        """
        GASから既存のドメインリストを取得

        Returns:
            既存ドメインのセット
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.post(
                    self.webhook_url,
                    json={"action": "get_domains"},
                )
                response.raise_for_status()
                data = response.json()

                domains = set(data.get("domains", []))
                logger.info(f"既存ドメイン取得: {len(domains)}件")
                return domains
        except Exception as e:
            logger.warning(f"既存ドメイン取得エラー（無視して続行）: {e}")
            return set()

    async def save_results(
        self,
        companies: list[dict],
        search_keyword: str,
    ) -> dict:
        """
        スクレイピング結果をGASに保存

        Args:
            companies: 企業データのリスト
            search_keyword: 検索キーワード（ファイル名用）

        Returns:
            GASからのレスポンス（spreadsheet_url等）
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "action": "save_results",
                        "search_keyword": search_keyword,
                        "companies": companies,
                    },
                )
                response.raise_for_status()
                data = response.json()

                logger.info(f"GAS保存完了: {data.get('spreadsheet_url', 'N/A')}")
                return data
        except httpx.HTTPStatusError as e:
            logger.error(f"GAS保存 HTTPエラー: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"GAS保存エラー: {e}")
            raise

    async def append_to_sheet(
        self,
        spreadsheet_id: str,
        companies: list[dict],
    ) -> dict:
        """
        既存のスプレッドシートにデータを追加

        Args:
            spreadsheet_id: スプレッドシートID
            companies: 企業データのリスト

        Returns:
            GASからのレスポンス
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "action": "append",
                        "spreadsheet_id": spreadsheet_id,
                        "companies": companies,
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"GAS追記エラー: {e}")
            raise
