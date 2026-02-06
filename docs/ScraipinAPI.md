# スクレイピングAPI仕様書（Python / FastAPI / Railway）

## 概要

営業リスト自動作成システムのスクレイピング処理を、GASからPython APIに移行する。
GASの6分タイムアウト制約を解消し、30件以上のスクレイピングを可能にすることが目的。

---

## 現在のシステム構成

```
Slackbot → Dify API → GAS（検索＋スクレイピング＋スプレッドシート保存）
```

## 移行後の構成

```
Slackbot → Dify API → GAS（基本情報保存のみ）
                     → Python API（スクレイピング）★今回作るもの
                     → GAS（スクレイピング結果でシート更新）
```

DifyワークフローからHTTP POSTで呼び出される。GASはスプレッドシートの保存・更新のみ担当し、スクレイピングはPython APIが担当する。

---

## 技術スタック

- **言語:** Python 3.11+
- **フレームワーク:** FastAPI
- **HTTPクライアント:** httpx（非同期対応）
- **HTMLパース:** BeautifulSoup4
- **デプロイ先:** Railway（既存のSlack-Dify連携基盤と同じ）

---

## APIエンドポイント

### POST `/scrape`

企業リストを受け取り、各企業のお問い合わせURL・電話番号をスクレイピングして返す。

#### リクエスト

```json
{
  "companies": [
    {
      "company_name": "株式会社ABC",
      "url": "https://www.abc.co.jp/"
    },
    {
      "company_name": "DEF合同会社",
      "url": "https://def.jp/"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `companies` | array | 企業リスト（必須） |
| `companies[].company_name` | string | 企業名 |
| `companies[].url` | string | 企業のURL（トップページ） |

#### レスポンス

```json
{
  "status": "success",
  "results": [
    {
      "company_name": "株式会社ABC",
      "base_url": "https://www.abc.co.jp/",
      "contact_url": "https://www.abc.co.jp/contact/",
      "phone": "03-1234-5678",
      "domain": "www.abc.co.jp",
      "error": ""
    },
    {
      "company_name": "DEF合同会社",
      "base_url": "https://def.jp/",
      "contact_url": "",
      "phone": "",
      "domain": "def.jp",
      "error": "company_mismatch"
    }
  ],
  "total": 2,
  "scraped": 2,
  "success_count": 1
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `status` | string | `"success"` or `"error"` |
| `results` | array | 各企業のスクレイピング結果 |
| `results[].company_name` | string | 企業名 |
| `results[].base_url` | string | トップページURL（正規化済み） |
| `results[].contact_url` | string | お問い合わせページのURL（見つからなければ空文字） |
| `results[].phone` | string | 電話番号（見つからなければ空文字） |
| `results[].domain` | string | ドメイン |
| `results[].error` | string | エラー種別（正常時は空文字） |
| `total` | int | 入力企業数 |
| `scraped` | int | スクレイピング実行数 |
| `success_count` | int | contact_urlまたはphoneが取れた件数 |

#### エラー種別（`error`フィールドの値）

| 値 | 意味 |
|-----|------|
| `""` | 正常（エラーなし） |
| `"top_page_failed"` | トップページの取得に失敗 |
| `"company_mismatch"` | 企業名とページ内容が一致しない（後述） |

---

## スクレイピング処理の詳細

各企業に対して以下の順序で処理を行う。

### STEP 1: URL正規化

入力URLをトップページに正規化する。

```
入力: https://www.abc.co.jp/products/item1.html
出力: https://www.abc.co.jp/
```

`https://ドメイン/` の形にする。

### STEP 2: トップページ取得

正規化したURLにHTTP GETリクエストを送る。

- **User-Agent:** 一般的なブラウザのUAを設定（bot扱いされないため）
- **タイムアウト:** 10秒
- **リダイレクト:** 追従する
- **リトライ:** 1回まで（失敗→300ms待機→再試行）
- **SSL検証:** 無効（自己署名証明書のサイトにも対応）

取得失敗した場合は `error: "top_page_failed"` で即return（contact_url, phoneは空）。

### STEP 3: 企業名一致チェック ★重要

取得したHTMLから以下を抽出し、企業名と一致するかチェックする。

**抽出対象:**
- `<title>` タグのテキスト
- `<meta property="og:site_name" content="...">` の値

**企業名の正規化処理:**

比較前に、企業名・タイトル・og:site_nameすべてに以下の正規化を行う。

1. 小文字化
2. 以下の法人格・敬称を除去:
   - 株式会社, (株), （株）
   - 有限会社, (有), （有）
   - 合同会社, 合資会社, 合名会社
   - 一般社団法人, 一般財団法人, 公益社団法人, 公益財団法人
   - 特定非営利活動法人, NPO法人
   - Inc., Co.,Ltd., Ltd., Corp., LLC, LLP, Corporation, Company, Co.
3. 空白・記号を除去（スペース、全角スペース、中黒、ハイフン、括弧など）

**一致判定ロジック:**

正規化した企業名を `name`、正規化したtitleを `title`、正規化したog:site_nameを `og` とする。

以下のいずれかを満たせば **一致（OK）**:
- `name` が `title` に含まれている
- `name` が `og` に含まれている
- `title`（2文字以上）が `name` に含まれている
- `og`（2文字以上）が `name` に含まれている

いずれも満たさなければ **不一致** → `error: "company_mismatch"` で即return（contact_url, phoneは空）。

**例外:** 正規化後の企業名が2文字未満の場合、チェック自体をスキップする（誤判定防止）。

**背景:**
Serper検索→LLMクレンジングの段階で、企業名とURLの紐付けがズレて別企業のページが混入するケースがある。この機能はそれを検出して弾くためのもの。

### STEP 4: お問い合わせURL抽出

トップページのHTMLから `<a>` タグを解析し、お問い合わせページへのリンクを探す。

**検索キーワード（hrefとリンクテキストの両方を対象）:**
```
contact, inquiry, enquiry, toiawase, otoiawase,
お問い合わせ, お問合せ, お問合わせ, おといあわせ,
form, mail, support
```

**フィルタリングルール:**
- `mailto:`, `javascript:`, `tel:` で始まるリンクは除外
- `#` で始まるリンクは `#contact` のみ許可
- 外部ドメインへのリンクは除外（同一ドメインのみ）

**スコアリング:**
候補が複数見つかった場合、以下のスコアで最も高いものを採用する。

| 条件 | スコア |
|------|--------|
| hrefに `contact` を含む | +10 |
| hrefに `inquiry` を含む | +10 |
| hrefに `toiawase` を含む | +10 |
| テキストに `お問い合わせ` を含む | +8 |
| テキストに `お問合せ` を含む | +8 |
| hrefに `form` を含む | +5 |
| パスの深さが浅い | +（5 - 深さ）|

**HTMLにリンクが見つからない場合：**

以下のよくあるURLパターンを順に試す（GETしてステータス200かつ、`<form>`, `お問い合わせ`, `contact` のいずれかがHTMLに含まれればヒット）。

```
{base_url}contact/
{base_url}contact
{base_url}inquiry/
{base_url}contact.html
{base_url}toiawase/
```

### STEP 5: 電話番号抽出

以下の優先順で電話番号を探す。最初にマッチしたものを採用。

**パターン1（最優先）: tel:リンク**
```html
<a href="tel:03-1234-5678">
```

**パターン2: ラベル付き電話番号**
```
TEL: 03-1234-5678
電話番号：03-1234-5678
☎ 03-1234-5678
代表 03-1234-5678
```

**パターン3（最後）: 数字パターンのみ**
```
03-1234-5678
0120-123-456
090-1234-5678
```

**バリデーション:**
- 数字のみにして10桁or11桁であること
- 先頭が `0` であること
- `0000` を含まないこと（ダミー番号除外）

**フォーマット:**
- 03始まり10桁 → `03-XXXX-XXXX`
- 0120始まり10桁 → `0120-XXX-XXX`
- 090/080/070始まり11桁 → `0X0-XXXX-XXXX`
- その他10桁 → `XXX-XXX-XXXX`
- その他11桁 → `XXX-XXXX-XXXX`

**電話番号の探索順序:**
1. トップページ
2. お問い合わせページ（`#` アンカーの場合はスキップ）
3. `{base_url}company/`
4. `{base_url}about/`

### STEP 6: 各企業間のインターバル

200msの間隔を空ける（サーバーへの負荷軽減）。

---

## 並列処理（オプション・推奨）

GASでは直列処理しかできなかったが、Pythonでは非同期処理が可能。httpxのAsyncClientを使って、同時に5〜10件程度を並列スクレイピングすれば大幅に高速化できる。

ただし、並列数が多すぎると相手サーバーへの負荷やIP制限のリスクがあるので、同時接続数は最大10程度に抑えること。

---

## HTTPリクエスト設定

全てのHTTPリクエストに共通:

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3"
}
timeout = 10  # 秒
follow_redirects = True
verify_ssl = False
max_retries = 1
```

---

## Railway デプロイ

### 必要ファイル

```
scraping-api/
├── main.py          # FastAPIアプリ本体
├── scraper.py       # スクレイピングロジック
├── requirements.txt # 依存パッケージ
├── Procfile         # Railway用起動コマンド
└── railway.toml     # Railway設定（オプション）
```

### requirements.txt

```
fastapi
uvicorn[standard]
httpx
beautifulsoup4
```

### Procfile

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 環境変数

特に必要なし（スプレッドシートへのアクセスはGASが担当するため）。

---

## Difyワークフローの変更

現在のHTTPノード（GAS POST呼び出し）の後に、以下の2ノードを追加する。

### ノード1: Python APIでスクレイピング

```
HTTPリクエスト:
  URL: https://{RailwayのURL}/scrape
  メソッド: POST
  ヘッダー: Content-Type: application/json
  ボディ:
    {
      "companies": [GASの保存結果から企業リスト]
    }
  タイムアウト:
    connect: 10秒
    read: 600秒（100件でも余裕を持たせる）
    write: 10秒
  リトライ: 無効（retry: {}）
```

※リトライ無効は重要。リトライするとスクレイピングが重複実行される。

### ノード2: GASにスクレイピング結果を送って更新

GASに新しいエンドポイント（またはactionパラメータ）を追加して、スクレイピング結果を受け取りシートのC列・D列を更新する処理を作る。

---

## GAS側の変更

現在のGAS（v4）から以下を変更する。

### 削除するもの
- `scrapeCompany` 関数
- `scrapeWithTimeBudget` 関数
- `fetchWithRetry` 関数
- `tryCommonContactUrls` 関数
- `extractContactFromHtml` 関数
- `extractPhoneFromHtml` 関数
- `calculateContactScore` 関数
- `isValidPhoneNumber` 関数
- `formatPhoneNumber` 関数
- `isSameDomain` 関数
- `SCRAPING_TIME_LIMIT_MS` 定数
- doPost内のSTEP3（スクレイピング）の呼び出し

### 残すもの
- doGet（既存企業リスト取得）
- doPost内のSTEP1（重複チェック）、STEP2（基本情報保存）、STEP5（個別リスト作成）
- STEP4（シート更新）→ 別途、Python APIの結果を受け取って更新する新エンドポイントとして整理

### 追加するもの
- スクレイピング結果を受け取ってシートを更新するためのaction（例: `action: "update_scraped"`）

---

## 注意事項

- `herp.careers/careers` は除外ドメインとして誤りがある。正しくは `herp.careers`（パスを含めるとマッチしないため）。EXCLUDE_DOMAINSを使う場合はドメイン部分のみにすること。
- Difyの HTTPリクエストノードでリトライは必ず無効にすること。リトライが有効だと並行実行されて重複データが発生する（v7→v8で経験済みの致命的バグ）。
- DifyからPython APIへのHTTPタイムアウト（read）は長めに設定すること。件数が多い場合、スクレイピングに数分〜10分以上かかる可能性がある。