"""
Slack通知モジュール
処理の進捗と結果をSlackに通知
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Slack通知クライアント"""

    API_URL = "https://slack.com/api/chat.postMessage"

    def __init__(self, bot_token: str):
        """
        Args:
            bot_token: Slack Bot Token (xoxb-...)
        """
        self.bot_token = bot_token
        self.headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        blocks: Optional[list] = None,
    ) -> bool:
        """
        Slackにメッセージを送信

        Args:
            channel: チャンネルID
            text: メッセージテキスト
            thread_ts: スレッドのタイムスタンプ（スレッド返信用）
            blocks: Block Kit のブロック（オプション）

        Returns:
            送信成功したかどうか
        """
        payload = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if blocks:
            payload["blocks"] = blocks

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.API_URL,
                    headers=self.headers,
                    json=payload,
                )
                data = response.json()

                if not data.get("ok"):
                    logger.error(f"Slack送信エラー: {data.get('error', 'unknown')}")
                    return False

                logger.debug(f"Slack送信成功: {channel}")
                return True
        except Exception as e:
            logger.error(f"Slack送信例外: {e}")
            return False

    async def notify_progress(
        self,
        channel: str,
        thread_ts: str,
        status: str,
        progress: int,
        message: str,
    ) -> bool:
        """
        進捗状況を通知

        Args:
            channel: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            status: ステータス文字列
            progress: 進捗率（0-100）
            message: メッセージ
        """
        emoji = self._get_status_emoji(status)
        text = f"{emoji} [{status}] {message} ({progress}%)"
        return await self.send_message(channel, text, thread_ts)

    async def notify_completion(
        self,
        channel: str,
        thread_ts: str,
        search_keyword: str,
        result_count: int,
        spreadsheet_url: Optional[str] = None,
    ) -> bool:
        """
        完了通知を送信

        Args:
            channel: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            search_keyword: 検索キーワード
            result_count: 結果件数
            spreadsheet_url: スプレッドシートURL
        """
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: *営業リスト作成完了*\n\n"
                            f"*検索キーワード:* {search_keyword}\n"
                            f"*取得件数:* {result_count}件"
                }
            }
        ]

        if spreadsheet_url:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":spreadsheet: <{spreadsheet_url}|スプレッドシートを開く>"
                }
            })

        text = f"営業リスト作成完了: {search_keyword} ({result_count}件)"
        return await self.send_message(channel, text, thread_ts, blocks)

    async def notify_error(
        self,
        channel: str,
        thread_ts: str,
        error_message: str,
    ) -> bool:
        """
        エラー通知を送信

        Args:
            channel: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            error_message: エラーメッセージ
        """
        text = f":x: *エラーが発生しました*\n```{error_message}```"
        return await self.send_message(channel, text, thread_ts)

    async def upload_file(
        self,
        channel: str,
        file_content: bytes,
        filename: str,
        title: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> bool:
        """
        Slackにファイルをアップロード

        Args:
            channel: チャンネルID
            file_content: ファイルの内容（バイト）
            filename: ファイル名
            title: ファイルのタイトル
            thread_ts: スレッドのタイムスタンプ

        Returns:
            アップロード成功したかどうか
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # files.uploadV2 API を使用
                data = {
                    "channels": channel,
                    "filename": filename,
                    "title": title or filename,
                }
                if thread_ts:
                    data["thread_ts"] = thread_ts

                files = {
                    "file": (filename, file_content, "text/csv"),
                }

                response = await client.post(
                    "https://slack.com/api/files.upload",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data=data,
                    files=files,
                )
                result = response.json()

                if not result.get("ok"):
                    logger.error(f"Slackファイルアップロードエラー: {result.get('error', 'unknown')}")
                    return False

                logger.info(f"Slackファイルアップロード成功: {filename}")
                return True
        except Exception as e:
            logger.error(f"Slackファイルアップロード例外: {e}")
            return False

    def _get_status_emoji(self, status: str) -> str:
        """ステータスに応じた絵文字を取得"""
        emoji_map = {
            "pending": ":hourglass:",
            "searching": ":mag:",
            "scraping": ":spider_web:",
            "saving": ":floppy_disk:",
            "completed": ":white_check_mark:",
            "failed": ":x:",
        }
        return emoji_map.get(status, ":information_source:")
