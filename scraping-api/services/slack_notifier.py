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
        contact_count: Optional[int] = None,
    ) -> bool:
        """
        完了通知を送信

        Args:
            channel: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            search_keyword: 検索キーワード
            result_count: 結果件数
            spreadsheet_url: スプレッドシートURL
            contact_count: 連絡先ありの件数
        """
        # メッセージを構築
        if contact_count is not None and contact_count < result_count:
            message_lines = [
                f":white_check_mark: 完了しました！{result_count}社のリストを作成しました（連絡先あり: {contact_count}社）"
            ]
        else:
            message_lines = [
                f":white_check_mark: 完了しました！{result_count}社のリストを作成しました"
            ]

        if spreadsheet_url:
            message_lines.append("")
            message_lines.append(f":bar_chart: Googleスプレッドシートも作成しました！")
            message_lines.append(spreadsheet_url)

        text = "\n".join(message_lines)
        return await self.send_message(channel, text, thread_ts)

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
        Slackにファイルをアップロード（新API使用）

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
                # Step 1: アップロードURL取得
                get_url_response = await client.post(
                    "https://slack.com/api/files.getUploadURLExternal",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data={
                        "filename": filename,
                        "length": len(file_content),
                    },
                )
                get_url_result = get_url_response.json()

                if not get_url_result.get("ok"):
                    logger.error(f"Slack URL取得エラー: {get_url_result.get('error', 'unknown')}")
                    return False

                upload_url = get_url_result["upload_url"]
                file_id = get_url_result["file_id"]

                # Step 2: ファイルをアップロード
                upload_response = await client.post(
                    upload_url,
                    content=file_content,
                    headers={"Content-Type": "text/csv"},
                )

                if upload_response.status_code != 200:
                    logger.error(f"Slackファイルアップロードエラー: {upload_response.status_code}")
                    return False

                # Step 3: アップロード完了を通知
                complete_data = {
                    "files": [{"id": file_id, "title": title or filename}],
                    "channel_id": channel,
                }
                if thread_ts:
                    complete_data["thread_ts"] = thread_ts

                complete_response = await client.post(
                    "https://slack.com/api/files.completeUploadExternal",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=complete_data,
                )
                complete_result = complete_response.json()

                if not complete_result.get("ok"):
                    logger.error(f"Slackアップロード完了エラー: {complete_result.get('error', 'unknown')}")
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
