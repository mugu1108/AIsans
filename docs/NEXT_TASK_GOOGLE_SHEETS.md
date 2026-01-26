# Google Sheets連携機能の実装タスク

**作成日**: 2026-01-27
**ステータス**: 準備完了（環境設定待ち）
**優先度**: 高

---

## 📋 実装状況

### ✅ 完了済み
- [x] スレッド返信機能の実装（2026-01-27完了）
  - リスト作成結果を元のメッセージのスレッド内に表示
  - 通知数を削減し、チャンネルの見やすさを改善
- [x] Google APIライブラリのインストール（googleapis）
- [x] GoogleSheetsClientクラスの実装
  - CSVからスプレッドシート作成機能
  - 指定フォルダへの移動機能
- [x] 環境変数設定の準備
  - `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`（任意）
  - `GOOGLE_DRIVE_FOLDER_ID`（任意）
- [x] index.tsでの統合（環境変数設定時のみ有効化）

### 🔄 次に実装するタスク
Google Cloud Platformの設定とスプレッドシート機能の有効化

---

## 🎯 実装目標

営業リスト作成完了後、以下を自動実行：
1. CSVファイルをSlackのスレッド内に送信
2. Googleスプレッドシートを作成
3. 指定の共有ドライブフォルダにアップロード
4. スプレッドシートのURLをSlackのスレッド内に通知

**対象フォルダ**: `sai X aid` 共有ドライブ
**フォルダID**: `1GmLdANjWb3_cpWHay6a5ICfS0I-2_dPT`
**URL**: https://drive.google.com/drive/folders/1GmLdANjWb3_cpWHay6a5ICfS0I-2_dPT

---

## 📝 実装手順

### Step 1: Google Cloud Platformの設定

#### 1.1 Google Cloud Projectの作成
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 新しいプロジェクトを作成（既存プロジェクトがあればスキップ）
   - プロジェクト名: `ai-shine` (推奨)
   - プロジェクトID: 自動生成 or 任意

#### 1.2 必要なAPIの有効化
以下の2つのAPIを有効にする必要があります：

1. **Google Sheets API**
   - [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
   - 「有効にする」をクリック

2. **Google Drive API**
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   - 「有効にする」をクリック

#### 1.3 サービスアカウントの作成

1. [サービスアカウント](https://console.cloud.google.com/iam-admin/serviceaccounts)ページに移動
2. 「サービスアカウントを作成」をクリック
3. 以下の情報を入力：
   - **サービスアカウント名**: `ai-shine-sheets` (推奨)
   - **サービスアカウントID**: 自動生成（例: `ai-shine-sheets@project-id.iam.gserviceaccount.com`）
   - **説明**: `AI-Shine用のスプレッドシート作成サービス`
4. 「作成して続行」をクリック
5. **ロールの選択**: スキップ（共有ドライブの権限で制御するため）
6. 「完了」をクリック

#### 1.4 サービスアカウントのJSONキーを作成

1. 作成したサービスアカウントをクリック
2. 「キー」タブに移動
3. 「鍵を追加」→「新しい鍵を作成」をクリック
4. **キーのタイプ**: `JSON`を選択
5. 「作成」をクリック
6. JSONファイルが自動ダウンロードされます

#### 1.5 JSONキーファイルの配置

ダウンロードしたJSONファイルをプロジェクトルートに配置：

```bash
# プロジェクトルートに移動
cd /Users/seiji/Desktop/dev/ai-shain

# JSONファイルをコピー（ダウンロードフォルダから）
cp ~/Downloads/ai-shine-sheets-xxx.json ./google-service-account.json

# 権限を設定（セキュリティのため）
chmod 600 ./google-service-account.json
```

**重要**: このファイルは`.gitignore`に既に含まれているため、Gitにコミットされません。

---

### Step 2: Google Driveの権限設定

#### 2.1 サービスアカウントのメールアドレスを確認

JSONファイルの`client_email`フィールドを確認：
```json
{
  "client_email": "ai-shine-sheets@project-id.iam.gserviceaccount.com"
}
```

#### 2.2 共有ドライブフォルダに権限を付与

1. [Google Drive](https://drive.google.com/)を開く
2. 共有ドライブ「sai X aid」を開く
3. 対象フォルダ（ID: `1GmLdANjWb3_cpWHay6a5ICfS0I-2_dPT`）を右クリック
4. 「共有」をクリック
5. サービスアカウントのメールアドレスを入力
   - 例: `ai-shine-sheets@project-id.iam.gserviceaccount.com`
6. 権限を「編集者」に設定
7. 「送信」をクリック

**注意**: 共有ドライブの場合、通知メールは送信されません。

---

### Step 3: 環境変数の設定

`.env`ファイルに以下を追加：

```bash
# Google API設定
GOOGLE_SERVICE_ACCOUNT_KEY_PATH=./google-service-account.json
GOOGLE_DRIVE_FOLDER_ID=1GmLdANjWb3_cpWHay6a5ICfS0I-2_dPT
```

---

### Step 4: 動作確認

#### 4.1 アプリケーションの再起動

```bash
# 開発サーバーを停止（Ctrl+C）
# 再起動
npm run dev
```

起動時に以下のログが表示されることを確認：
```
Google Sheets機能を有効化しました
```

#### 4.2 Slackでテスト

Slackで営業リスト作成AIにメンション：
```
@Alex 東京 IT企業
```

期待される動作：
1. 「了解しました！営業リスト作成を開始します...⏳」（スレッド開始）
2. 「✅ 完了しました！30社のリストを作成しました（処理時間: XX秒）」（スレッド内）
3. `sales_list_YYYYMMDDTHHMMSS.csv`（スレッド内）
4. 「📊 Googleスプレッドシートも作成しました！」+ URL（スレッド内）

#### 4.3 Google Driveで確認

1. 指定フォルダを開く
2. `営業リスト_YYYYMMDDTHHMMSS`という名前のスプレッドシートが作成されていることを確認
3. スプレッドシートを開き、CSVと同じデータが表示されることを確認

---

## 🔧 実装済みコード

### GoogleSheetsClient（`src/infrastructure/google/GoogleSheetsClient.ts`）

**主な機能**:
- `createSpreadsheetFromCSV()`: CSVバッファからスプレッドシートを作成
- `moveToFolder()`: スプレッドシートを指定フォルダに移動
- `parseCSVLine()`: CSV行をパース

**使用ライブラリ**:
- `googleapis`: Google APIs Node.jsクライアント
- `google-auth-library`: JWT認証

### index.ts統合コード

```typescript
// Google Sheets機能（環境変数が設定されている場合のみ）
let googleSheetsClient: GoogleSheetsClient | null = null;
if (env.GOOGLE_SERVICE_ACCOUNT_KEY_PATH && env.GOOGLE_DRIVE_FOLDER_ID) {
  googleSheetsClient = new GoogleSheetsClient(
    env.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
    env.GOOGLE_DRIVE_FOLDER_ID,
    logger
  );
  logger.info('Google Sheets機能を有効化しました');
} else {
  logger.info('Google Sheets機能は無効です（環境変数未設定）');
}
```

成功時の処理:
```typescript
// Googleスプレッドシート作成（有効な場合のみ）
if (googleSheetsClient) {
  try {
    const spreadsheetTitle = `営業リスト_${timestamp}`;
    const spreadsheetResult = await googleSheetsClient.createSpreadsheetFromCSV(
      result.csvBuffer!,
      spreadsheetTitle
    );

    // スプレッドシートURLをスレッドで通知
    await slackAdapter.sendMessage(
      event.channelId,
      `📊 Googleスプレッドシートも作成しました！\n${spreadsheetResult.spreadsheetUrl}`,
      threadTs
    );
  } catch (sheetsError) {
    logger.error('Googleスプレッドシート作成エラー', sheetsError as Error);
    // エラーは無視してCSVのみで完了
  }
}
```

---

## ⚠️ トラブルシューティング

### エラー1: 認証エラー
```
Error: invalid_grant: Invalid JWT Signature
```

**原因**: JSONキーファイルが正しくない、またはパスが間違っている

**解決方法**:
1. JSONファイルのパスを確認
2. ファイルの内容が正しいJSON形式か確認
3. 新しいキーを作成して再試行

### エラー2: 権限エラー
```
Error: Insufficient Permission
```

**原因**: サービスアカウントに共有ドライブフォルダへの権限がない

**解決方法**:
1. Google Driveで共有設定を確認
2. サービスアカウントのメールアドレスが正しく追加されているか確認
3. 権限が「編集者」に設定されているか確認

### エラー3: APIが有効化されていない
```
Error: Google Sheets API has not been used in project
```

**解決方法**:
1. Google Cloud Consoleで該当プロジェクトを開く
2. Google Sheets APIとGoogle Drive APIを有効化
3. 数分待ってから再試行

### エラー4: フォルダが見つからない
```
Error: File not found
```

**原因**: フォルダIDが間違っている

**解決方法**:
1. Google DriveでフォルダのURLを確認
2. URLの最後の部分がフォルダID: `https://drive.google.com/drive/folders/[フォルダID]`
3. `.env`のフォルダIDを修正

---

## 📊 実装チェックリスト

### Google Cloud Platform設定
- [ ] Google Cloud Projectを作成
- [ ] Google Sheets APIを有効化
- [ ] Google Drive APIを有効化
- [ ] サービスアカウントを作成
- [ ] サービスアカウントのJSONキーをダウンロード
- [ ] JSONキーファイルをプロジェクトルートに配置（`google-service-account.json`）

### Google Drive設定
- [ ] サービスアカウントのメールアドレスを確認
- [ ] 共有ドライブフォルダにサービスアカウントを追加
- [ ] 権限を「編集者」に設定

### 環境変数設定
- [ ] `.env`に`GOOGLE_SERVICE_ACCOUNT_KEY_PATH`を追加
- [ ] `.env`に`GOOGLE_DRIVE_FOLDER_ID`を追加

### 動作確認
- [ ] アプリケーションを再起動
- [ ] 起動時に「Google Sheets機能を有効化しました」と表示される
- [ ] Slackでテスト実行
- [ ] スレッド内にCSVとスプレッドシートURLが表示される
- [ ] Google Driveでスプレッドシートが作成されていることを確認
- [ ] スプレッドシートの内容がCSVと一致することを確認

---

## 🚀 デプロイ時の注意事項

### 本番環境（Railway）への設定

Railwayの環境変数に以下を追加：

1. **GOOGLE_SERVICE_ACCOUNT_KEY_PATH**
   - 値: `./google-service-account.json`

2. **GOOGLE_DRIVE_FOLDER_ID**
   - 値: `1GmLdANjWb3_cpWHay6a5ICfS0I-2_dPT`

3. **JSONキーファイルの内容**
   - Railway Dashboardで環境変数として設定するか
   - シークレットファイルとして追加
   - 推奨: Railwayのシークレット機能を使用

**セキュリティ**: JSONキーファイルは機密情報なので、Gitにコミットしないこと（`.gitignore`に含まれています）

---

## 📖 参考リンク

- [Google Sheets API Documentation](https://developers.google.com/sheets/api)
- [Google Drive API Documentation](https://developers.google.com/drive/api)
- [googleapis Node.js Client](https://github.com/googleapis/google-api-nodejs-client)
- [Service Account Authentication](https://cloud.google.com/iam/docs/service-accounts)

---

## 📝 実装完了後の次のステップ

Google Sheets連携が完了したら、以下の機能拡張を検討：

1. **スプレッドシートのフォーマット改善**
   - ヘッダー行に背景色を追加
   - 列幅の自動調整
   - データバリデーションの追加

2. **複数フォーマット対応**
   - Excel形式（.xlsx）での出力
   - PDF形式での出力

3. **通知の改善**
   - スプレッドシート作成中の進捗通知
   - エラー時の詳細なエラーメッセージ

4. **権限管理**
   - スプレッドシートの共有設定
   - 閲覧専用リンクの生成
