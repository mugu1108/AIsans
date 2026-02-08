# Python API 改修依頼書

## 背景

Difyワークフローで営業リスト自動作成システムを運用中。
現在、検索（Serper API）とクレンジング（LLM）をDify内で実行しているが、**件数を増やすとDifyがタイムアウトする**ため、検索処理をPython API側に移行したい。

## 現在のシステム構成

```
Dify（重い・61ノード）           Python API（Railway）      旧GAS（v6）
─────────────────              ──────────────────        ─────────
LLMでクエリ生成（GPT-4o）
Serper検索 ×25〜30クエリ
結果統合・フィルタリング
LLMでクレンジング（GPT-4o）
リトライ最大3回
  → GAS基本保存                                          → handleSaveBasic
  → スクレイピング依頼            → POST /scrape
  ← 結果受信                    ←
  → GASシート更新                                        → handleUpdateScraped
最終整形・CSV出力
```

**問題**: Difyで検索・LLM処理・リトライを全部やっているため、件数が多いとタイムアウトする。

## 目標の構成

```
Dify（軽い・6ノード）       Python API（Railway）           新GAS（AI-Shine）
─────────────            ──────────────────            ──────────────
入力パース          →     POST /search_sync
                          ├ 既存ドメイン取得             → action: get_domains
                          ├ Serper検索（大量OK）
                          ├ スクレイピング
                          └ 結果保存                    → action: save_results
結果表示            ←     レスポンス返却
```

## Python API に必要な変更

### やること: `/search_sync` エンドポイントを `main.py` に追加

既存の `/search`（非同期ジョブ版）はそのまま残し、Difyから呼びやすい**同期版**を追加する。
処理内容は `search_workflow.py` の `SearchWorkflow.execute()` とほぼ同じだが、以下が異なる：

- Slack通知は不要（Dify側で結果表示する）
- ジョブ管理不要（同期で待つので）
- レスポンスで結果データを直接返す

### 追加するコード

```python
# --- main.py に追加するリクエスト/レスポンスモデル ---

class SearchSyncRequest(BaseModel):
    """同期検索リクエスト"""
    search_keyword: str
    target_count: int = 30
    queries: Optional[list[str]] = None


class SearchSyncResponse(BaseModel):
    """同期検索レスポンス"""
    status: str
    search_keyword: str
    target_count: int
    result_count: int
    search_count: int
    scrape_count: int
    success_count: int
    spreadsheet_url: str
    results: list[dict]
    message: str


# --- main.py に追加するエンドポイント ---

@app.post("/search_sync", response_model=SearchSyncResponse)
async def search_sync(request: SearchSyncRequest):
    """
    同期版の検索エンドポイント（Difyワークフロー用）

    検索→スクレイピング→GAS保存を一括で実行し、
    完了後に結果を返す。
    """
    settings = get_settings()

    if not settings.serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY が未設定です")
    if not settings.gas_webhook_url:
        raise HTTPException(status_code=500, detail="GAS_WEBHOOK_URL が未設定です")

    max_count = getattr(settings, 'max_target_count', 200)
    if request.target_count > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"target_count は {max_count} 以下にしてください"
        )

    logger.info(f"=== 同期検索開始: {request.search_keyword} ({request.target_count}件) ===")

    serper_client = SerperClient(settings.serper_api_key)
    gas_client = GASClient(settings.gas_webhook_url)

    # STEP 1: 既存ドメイン取得
    existing_domains = await gas_client.get_existing_domains()
    logger.info(f"既存ドメイン: {len(existing_domains)}件")

    # STEP 2: 検索クエリ生成
    queries = request.queries or generate_search_queries(request.search_keyword)
    logger.info(f"検索クエリ {len(queries)}件")

    # STEP 3: Serper検索
    companies = await serper_client.search_companies(
        queries=queries,
        target_count=request.target_count,
        existing_domains=existing_domains,
    )
    logger.info(f"検索結果: {len(companies)}件")

    if not companies:
        return SearchSyncResponse(
            status="success",
            search_keyword=request.search_keyword,
            target_count=request.target_count,
            result_count=0, search_count=0, scrape_count=0, success_count=0,
            spreadsheet_url="", results=[],
            message="検索結果が0件でした。キーワードを変更してお試しください。",
        )

    # STEP 4: スクレイピング
    companies_for_scrape = [
        {"company_name": c.company_name, "url": c.url}
        for c in companies
    ]
    scraped_results = await scrape_companies(companies_for_scrape)
    successful_results = [r for r in scraped_results if r.contact_url or r.phone]
    logger.info(f"スクレイピング完了: {len(scraped_results)}件中 {len(successful_results)}件成功")

    # STEP 5: GAS保存
    companies_to_save = [
        {
            "company_name": r.company_name,
            "base_url": r.base_url,
            "contact_url": r.contact_url,
            "phone": r.phone,
            "domain": r.domain,
        }
        for r in successful_results
    ]

    spreadsheet_url = ""
    if companies_to_save:
        try:
            gas_response = await gas_client.save_results(
                companies=companies_to_save,
                search_keyword=request.search_keyword,
            )
            spreadsheet_url = gas_response.get("spreadsheet_url", "")
        except Exception as e:
            logger.error(f"GAS保存エラー（結果は返却）: {e}")

    message = f"検索完了: {len(successful_results)}件の企業情報を取得しました。"
    if spreadsheet_url:
        message += f"\nスプレッドシート: {spreadsheet_url}"

    return SearchSyncResponse(
        status="success",
        search_keyword=request.search_keyword,
        target_count=request.target_count,
        result_count=len(successful_results),
        search_count=len(companies),
        scrape_count=len(scraped_results),
        success_count=len(successful_results),
        spreadsheet_url=spreadsheet_url,
        results=companies_to_save,
        message=message,
    )
```

### 追加するインポート（main.pyの冒頭で不足しているもの）

```python
from services.serper import SerperClient, generate_search_queries
from services.gas_client import GASClient
```

## 既存コードとの関係

上記の `/search_sync` は、以下の既存モジュールをそのまま使う：

- `services/serper.py` → `SerperClient`, `generate_search_queries`
- `services/gas_client.py` → `GASClient`
- `scraper.py` → `scrape_companies`

**既存の `/scrape` と `/search` エンドポイントはそのまま残してOK。**

## Dify側の呼び出し方（参考情報）

Difyは以下のようにこのエンドポイントを呼ぶ：

```
POST https://{RAILWAY_URL}/search_sync
Content-Type: application/json

{
    "search_keyword": "東京 IT企業",
    "target_count": 50
}
```

HTTPタイムアウトは read: 600秒 に設定するので、処理時間は最大10分程度まで許容される。

## GAS側の変更（別担当）

GASは旧v6から新GAS（AI-Shine版）に切り替える。
Python APIの `GAS_WEBHOOK_URL` 環境変数を新GASのデプロイURLに変更する必要がある。
**ただしGASClient のコード自体は変更不要**（新GASのアクション名と完全に互換性がある）。

## テスト方法

デプロイ後、以下で動作確認：

```bash
# ヘルスチェック
curl https://{RAILWAY_URL}/health

# 少ない件数でテスト
curl -X POST https://{RAILWAY_URL}/search_sync \
  -H "Content-Type: application/json" \
  -d '{"search_keyword": "東京 IT企業", "target_count": 5}'
```

## 補足: 現在の `/scrape` の500エラーについて

現在、Difyから `/scrape` を呼ぶと500エラーが返っている。
原因は未調査だが、以下の可能性がある：
- `lxml` パーサーの未インストール（`requirements.txt` に `lxml` があるか確認）
- Railway上のメモリ不足
- 依存パッケージの不整合

`/search_sync` の追加とは別に、`/scrape` の500エラーも確認・修正してほしい。