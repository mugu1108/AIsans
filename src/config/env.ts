/**
 * 環境変数管理モジュール
 *
 * 型安全な環境変数アクセスとバリデーション
 */

/**
 * Node環境の型定義
 */
export type NodeEnvironment = 'development' | 'production' | 'test';

/**
 * 環境変数の型定義
 */
export interface EnvironmentVariables {
  // Node環境
  NODE_ENV: NodeEnvironment;

  // データベース
  DATABASE_URL: string;
  DIRECT_URL: string;

  // Slack
  SLACK_BOT_TOKEN: string;
  SLACK_SIGNING_SECRET: string;
  SLACK_APP_TOKEN?: string; // Socket Mode用（任意）

  // Dify Workflow API
  DIFY_API_URL: string;
  DIFY_API_KEY: string;

  // Google API（任意）
  GOOGLE_SERVICE_ACCOUNT_KEY_PATH?: string;
  GOOGLE_DRIVE_FOLDER_ID?: string;

  // サーバー
  PORT: number;
}

/**
 * 環境変数バリデーションエラー
 */
export class EnvironmentValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EnvironmentValidationError';
  }
}

/**
 * 必須環境変数のリスト
 */
const REQUIRED_ENV_VARS = [
  'DATABASE_URL',
  'DIRECT_URL',
  'SLACK_BOT_TOKEN',
  'SLACK_SIGNING_SECRET',
  'DIFY_API_URL',
  'DIFY_API_KEY',
] as const;

/**
 * 環境変数が設定されているかチェック
 *
 * @param key - チェックする環境変数名
 * @throws EnvironmentValidationError 環境変数が未設定の場合
 */
function requireEnv(key: string): string {
  const value = process.env[key];

  if (!value || value.trim() === '') {
    throw new EnvironmentValidationError(
      `環境変数 ${key} が設定されていません。.envファイルを確認してください。`
    );
  }

  return value;
}

/**
 * 任意の環境変数を取得
 *
 * @param key - 環境変数名
 * @param defaultValue - デフォルト値
 * @returns 環境変数の値またはデフォルト値
 */
function getEnv(key: string, defaultValue?: string): string | undefined {
  const value = process.env[key];
  return value && value.trim() !== '' ? value : defaultValue;
}

/**
 * NODE_ENVを取得・検証
 *
 * @returns NODE_ENV値
 */
function getNodeEnv(): NodeEnvironment {
  const env = getEnv('NODE_ENV', 'development');

  const validEnvs: NodeEnvironment[] = ['development', 'production', 'test'];

  if (!validEnvs.includes(env as NodeEnvironment)) {
    console.warn(
      `警告: NODE_ENV="${env}" は無効な値です。developmentとして扱います。`
    );
    return 'development';
  }

  return env as NodeEnvironment;
}

/**
 * ポート番号を取得・検証
 *
 * @returns ポート番号
 */
function getPort(): number {
  const portStr = getEnv('PORT', '3000');
  const port = parseInt(portStr!, 10);

  if (isNaN(port) || port < 1 || port > 65535) {
    throw new EnvironmentValidationError(
      `無効なPORT番号です: ${portStr}。1-65535の範囲で指定してください。`
    );
  }

  return port;
}

/**
 * 環境変数をロード・検証
 *
 * @returns 検証済み環境変数オブジェクト
 * @throws EnvironmentValidationError 必須環境変数が未設定の場合
 */
function loadEnvironmentVariables(): EnvironmentVariables {
  // 必須環境変数のチェック
  const missingVars = REQUIRED_ENV_VARS.filter(
    key => !process.env[key] || process.env[key]!.trim() === ''
  );

  if (missingVars.length > 0) {
    throw new EnvironmentValidationError(
      `以下の必須環境変数が設定されていません:\n${missingVars.map(v => `  - ${v}`).join('\n')}\n\n.envファイルを確認してください。`
    );
  }

  // 環境変数オブジェクトを構築
  const env: EnvironmentVariables = {
    NODE_ENV: getNodeEnv(),
    DATABASE_URL: requireEnv('DATABASE_URL'),
    DIRECT_URL: requireEnv('DIRECT_URL'),
    SLACK_BOT_TOKEN: requireEnv('SLACK_BOT_TOKEN'),
    SLACK_SIGNING_SECRET: requireEnv('SLACK_SIGNING_SECRET'),
    SLACK_APP_TOKEN: getEnv('SLACK_APP_TOKEN'),
    DIFY_API_URL: requireEnv('DIFY_API_URL'),
    DIFY_API_KEY: requireEnv('DIFY_API_KEY'),
    GOOGLE_SERVICE_ACCOUNT_KEY_PATH: getEnv('GOOGLE_SERVICE_ACCOUNT_KEY_PATH'),
    GOOGLE_DRIVE_FOLDER_ID: getEnv('GOOGLE_DRIVE_FOLDER_ID'),
    PORT: getPort(),
  };

  return env;
}

/**
 * 環境変数の検証と読み込み
 *
 * アプリケーション起動時に一度だけ実行
 */
let cachedEnv: EnvironmentVariables | null = null;

/**
 * 検証済み環境変数を取得
 *
 * @returns 環境変数オブジェクト
 * @throws EnvironmentValidationError バリデーションエラー
 */
export function getEnvConfig(): EnvironmentVariables {
  if (!cachedEnv) {
    cachedEnv = loadEnvironmentVariables();
  }
  return cachedEnv;
}

/**
 * 環境変数設定のサマリーをログ出力（機密情報はマスク）
 */
export function logEnvironmentSummary(): void {
  const env = getEnvConfig();

  console.log('========================================');
  console.log('環境変数設定');
  console.log('========================================');
  console.log(`NODE_ENV:                           ${env.NODE_ENV}`);
  console.log(`PORT:                               ${env.PORT}`);
  console.log(`DATABASE_URL:                       ${maskConnectionString(env.DATABASE_URL)}`);
  console.log(`DIRECT_URL:                         ${maskConnectionString(env.DIRECT_URL)}`);
  console.log(`SLACK_BOT_TOKEN:                    ${maskToken(env.SLACK_BOT_TOKEN)}`);
  console.log(`SLACK_SIGNING_SECRET:               ${maskToken(env.SLACK_SIGNING_SECRET)}`);
  console.log(`SLACK_APP_TOKEN:                    ${env.SLACK_APP_TOKEN ? maskToken(env.SLACK_APP_TOKEN) : '(未設定)'}`);
  console.log(`DIFY_API_URL:                       ${env.DIFY_API_URL}`);
  console.log(`DIFY_API_KEY:                       ${maskToken(env.DIFY_API_KEY)}`);
  console.log(`GOOGLE_SERVICE_ACCOUNT_KEY_PATH:    ${env.GOOGLE_SERVICE_ACCOUNT_KEY_PATH || '(未設定)'}`);
  console.log(`GOOGLE_DRIVE_FOLDER_ID:             ${env.GOOGLE_DRIVE_FOLDER_ID || '(未設定)'}`);
  console.log('========================================');
}

/**
 * 接続文字列をマスク
 *
 * @param connectionString - データベース接続文字列
 * @returns マスクされた文字列
 */
function maskConnectionString(connectionString: string): string {
  try {
    const url = new URL(connectionString);
    return `${url.protocol}//${url.username}:****@${url.host}${url.pathname}`;
  } catch {
    return '****';
  }
}

/**
 * トークンをマスク
 *
 * @param token - トークン文字列
 * @returns マスクされたトークン
 */
function maskToken(token: string): string {
  if (token.length <= 8) {
    return '****';
  }

  const visibleStart = token.substring(0, 4);
  const visibleEnd = token.substring(token.length - 4);

  return `${visibleStart}****${visibleEnd}`;
}

// デフォルトエクスポート
export default getEnvConfig;
