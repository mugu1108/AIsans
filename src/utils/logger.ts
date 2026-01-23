/**
 * ログレベル
 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/**
 * ロガーインターフェース
 *
 * アプリケーション全体で使用する統一的なロギングインターフェース
 */
export interface Logger {
  /**
   * デバッグログを出力
   *
   * @param message - ログメッセージ
   * @param meta - メタデータ（任意）
   */
  debug(message: string, meta?: Record<string, unknown>): void;

  /**
   * 情報ログを出力
   *
   * @param message - ログメッセージ
   * @param meta - メタデータ（任意）
   */
  info(message: string, meta?: Record<string, unknown>): void;

  /**
   * 警告ログを出力
   *
   * @param message - ログメッセージ
   * @param meta - メタデータ（任意）
   */
  warn(message: string, meta?: Record<string, unknown>): void;

  /**
   * エラーログを出力
   *
   * @param message - ログメッセージ
   * @param error - エラーオブジェクト（任意）
   * @param meta - メタデータ（任意）
   */
  error(message: string, error?: Error, meta?: Record<string, unknown>): void;
}

/**
 * コンソールロガー実装
 *
 * 開発環境用のシンプルなコンソール出力ロガー
 */
export class ConsoleLogger implements Logger {
  constructor(private minLevel: LogLevel = 'info') {}

  debug(message: string, meta?: Record<string, unknown>): void {
    if (this.shouldLog('debug')) {
      console.debug(`[DEBUG] ${message}`, meta || '');
    }
  }

  info(message: string, meta?: Record<string, unknown>): void {
    if (this.shouldLog('info')) {
      console.info(`[INFO] ${message}`, meta || '');
    }
  }

  warn(message: string, meta?: Record<string, unknown>): void {
    if (this.shouldLog('warn')) {
      console.warn(`[WARN] ${message}`, meta || '');
    }
  }

  error(message: string, error?: Error, meta?: Record<string, unknown>): void {
    if (this.shouldLog('error')) {
      console.error(`[ERROR] ${message}`, error || '', meta || '');
    }
  }

  /**
   * ログレベルに基づいて出力すべきか判定
   *
   * @param level - ログレベル
   * @returns 出力すべきかどうか
   */
  private shouldLog(level: LogLevel): boolean {
    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error'];
    const minLevelIndex = levels.indexOf(this.minLevel);
    const currentLevelIndex = levels.indexOf(level);

    return currentLevelIndex >= minLevelIndex;
  }
}

/**
 * NoOpロガー実装
 *
 * テスト用の何もしないロガー
 */
export class NoOpLogger implements Logger {
  debug(_message: string, _meta?: Record<string, unknown>): void {
    // 何もしない
  }

  info(_message: string, _meta?: Record<string, unknown>): void {
    // 何もしない
  }

  warn(_message: string, _meta?: Record<string, unknown>): void {
    // 何もしない
  }

  error(_message: string, _error?: Error, _meta?: Record<string, unknown>): void {
    // 何もしない
  }
}

/**
 * デフォルトロガーインスタンスを作成
 *
 * @param level - 最小ログレベル
 * @returns ロガーインスタンス
 */
export function createLogger(level: LogLevel = 'info'): Logger {
  return new ConsoleLogger(level);
}
