"""
設定管理モジュール
環境変数から設定を読み込む
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """アプリケーション設定"""

    # Serper API
    serper_api_key: str

    # Slack
    slack_bot_token: str

    # GAS Webhook
    gas_webhook_url: str

    # OpenAI API（企業名クレンジング用）
    openai_api_key: str

    # 検索設定
    max_target_count: int = 300
    serper_results_per_query: int = 100

    # スクレイピング設定
    scrape_concurrent: int = 10
    scrape_timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        """環境変数から設定を読み込む"""
        serper_api_key = os.environ.get("SERPER_API_KEY", "")
        slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
        gas_webhook_url = os.environ.get("GAS_WEBHOOK_URL", "")
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        return cls(
            serper_api_key=serper_api_key,
            slack_bot_token=slack_bot_token,
            gas_webhook_url=gas_webhook_url,
            openai_api_key=openai_api_key,
            max_target_count=int(os.environ.get("MAX_TARGET_COUNT", "300")),
            serper_results_per_query=int(os.environ.get("SERPER_RESULTS_PER_QUERY", "100")),
            scrape_concurrent=int(os.environ.get("SCRAPE_CONCURRENT", "10")),
            scrape_timeout=float(os.environ.get("SCRAPE_TIMEOUT", "10.0")),
        )

    def validate(self) -> list[str]:
        """設定の検証（足りない環境変数をリストで返す）"""
        missing = []
        if not self.serper_api_key:
            missing.append("SERPER_API_KEY")
        if not self.slack_bot_token:
            missing.append("SLACK_BOT_TOKEN")
        if not self.gas_webhook_url:
            missing.append("GAS_WEBHOOK_URL")
        return missing


# グローバル設定インスタンス
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """設定を取得（遅延初期化）"""
    global settings
    if settings is None:
        settings = Settings.from_env()
    return settings
