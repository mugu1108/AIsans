# AI-Shine 開発ガイドライン

AI-Shine開発時にClaude Codeが従うべき絶対的なルールを定義します。

---

## プロジェクト概要

**AI-Shine**: マルチプラットフォーム対応のAI社員システム
- **Phase 1**: Slack + 営業リスト作成AI（Dify連携）
- **アーキテクチャ**: レイヤード構造（Interface/Application/Domain/Infrastructure）
- **DB**: PostgreSQL (Supabase) + Prisma ORM
- **言語**: TypeScript

---

## 📁 ディレクトリ構造（厳守）

```
src/
├── interfaces/      # プラットフォーム固有（Slack等）
├── application/     # オーケストレーション
├── domain/          # ビジネスロジック
│   ├── entities/
│   ├── services/
│   └── types/
└── infrastructure/  # 外部連携（DB、Dify、CSV）
    ├── database/repositories/
    ├── dify/
    └── csv/
```

**レイヤー依存ルール**: Interface → Application → Domain → Infrastructure
**禁止**: 上位レイヤーへの依存、プラットフォーム固有ロジックのInterface層外配置

---

## 🎯 絶対ルール

### 1. DB変更は事前確認必須
- `prisma/schema.prisma`を勝手に変更しない
- 変更必要時は必ずユーザー確認

### 2. 型安全性
- `any`禁止（やむを得ない場合のみ`unknown`）
- 全関数に戻り値型注釈必須
- Prisma生成型を活用

### 3. エラーハンドリング
- `src/utils/errors.ts`のカスタムエラークラス使用
- リトライ可能性判断（`retryable`フラグ）

### 4. セキュリティ
- 環境変数のハードコード禁止
- 機密情報のログ出力禁止

---

## 🛠️ コーディング規約

### 命名
- クラス: `PascalCase`
- 関数/変数: `camelCase`
- 定数: `UPPER_SNAKE_CASE`
- ファイル: `PascalCase.ts` (クラス) / `camelCase.ts` (ユーティリティ)

### インポート順序
1. 外部ライブラリ
2. 内部モジュール
3. 型定義

### 非同期
- `async/await`使用（`.then()`禁止）

---

## 📝 コミット規約（厳守）

```
<type>: <subject>

<body>

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**Type**: `feat`, `fix`, `refactor`, `docs`, `test`

---

## 🔀 ブランチ戦略

- `feature/[機能名]`: 新機能
- `fix/[修正内容]`: バグ修正
- `develop`から分岐 → PR作成

---

## ⚠️ 禁止事項

1. **環境変数ハードコード**
   ```typescript
   ❌ const apiKey = "app-123";
   ✅ const apiKey = process.env.DIFY_API_KEY!;
   ```

2. **機密情報ログ出力**
   ```typescript
   ❌ console.log('API Key:', apiKey);
   ✅ console.log('API call started');
   ```

3. **DB直接操作**
   ```typescript
   ❌ await db.query('SELECT * FROM ...');
   ✅ await prisma.aIEmployee.findMany();
   ```

4. **マイグレーション忘れ**
   ```bash
   # schema.prisma変更後必須
   npx prisma migrate dev --name [変更内容]
   npx prisma generate
   ```

5. **未テストでのプッシュ**

---

## 🧪 開発ワークフロー

### 実装前
1. `IMPLEMENTATION_PLAN.md`でタスク確認
2. `ARCHITECTURE.md`で設計確認
3. 依存関係確認

### 実装中
1. 小単位で実装（1ステップ30分以内）
2. すぐに動作確認
3. 問題なければコミット

### コミット前チェック
- [ ] ビルドエラーなし（`npm run build`）
- [ ] 動作確認済み
- [ ] 不要なログ削除
- [ ] コミット形式準拠

---

## 📚 参照ドキュメント

**必読**:
- `IMPLEMENTATION_PLAN.md`: タスク詳細
- `ARCHITECTURE.md`: 設計仕様
- `prisma/schema.prisma`: DBスキーマ（真実の源）

**参考**:
- `REQUIREMENTS.md`: 全体要件
- `.env.example`: 環境変数

**コマンド**:
```bash
npx prisma migrate dev --name [name]  # マイグレーション
npx prisma generate                    # クライアント生成
npx prisma studio                      # データ閲覧
npm run dev                            # 開発起動
npm run build                          # ビルド
```

---

## 🆘 エラー対応

1. エラーメッセージ完読 → スタックトレースで原因特定 → 関連ドキュメント確認 → ユーザー報告
2. **よくあるエラー**: Prisma（`DATABASE_URL`確認）、型（`npx prisma generate`）、インポート（パス確認）

---

## 💬 報告形式

```
✅ [完了/進行中/エラー] Task A Step 3
実施: 〇〇を作成
結果: 検証完了
次: Step 4実行
```

---

## 重要事項

- **不明点は推測せず、ユーザー確認**
- **小さく実装、頻繁に確認、すぐコミット**
- **セキュリティ・型安全性最優先**
