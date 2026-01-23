/**
 * AI-Shine基底エラークラス
 */
export class AIShineError extends Error {
  constructor(
    message: string,
    public code: string,
    public retryable: boolean = false
  ) {
    super(message);
    this.name = 'AIShineError';
    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * ネットワークエラー（リトライ可能）
 */
export class NetworkError extends AIShineError {
  constructor(message: string) {
    super(message, 'NETWORK_ERROR', true);
    this.name = 'NetworkError';
  }
}

/**
 * タイムアウトエラー（リトライ可能）
 */
export class TimeoutError extends AIShineError {
  constructor(message: string) {
    super(message, 'TIMEOUT_ERROR', true);
    this.name = 'TimeoutError';
  }
}

/**
 * バリデーションエラー（リトライ不可）
 */
export class ValidationError extends AIShineError {
  constructor(message: string) {
    super(message, 'VALIDATION_ERROR', false);
    this.name = 'ValidationError';
  }
}

/**
 * Dify APIエラー
 * 5xxエラーの場合はリトライ可能
 */
export class DifyAPIError extends AIShineError {
  constructor(message: string, public statusCode: number) {
    super(message, 'DIFY_API_ERROR', statusCode >= 500);
    this.name = 'DifyAPIError';
  }
}

/**
 * データベースエラー（リトライ可能）
 */
export class DatabaseError extends AIShineError {
  constructor(message: string) {
    super(message, 'DATABASE_ERROR', true);
    this.name = 'DatabaseError';
  }
}

/**
 * AI社員が見つからないエラー（リトライ不可）
 */
export class AIEmployeeNotFoundError extends AIShineError {
  constructor(mention: string) {
    super(`AI社員が見つかりません: ${mention}`, 'AI_EMPLOYEE_NOT_FOUND', false);
    this.name = 'AIEmployeeNotFoundError';
  }
}

/**
 * CSV生成エラー（リトライ不可）
 */
export class CSVGenerationError extends AIShineError {
  constructor(message: string) {
    super(message, 'CSV_GENERATION_ERROR', false);
    this.name = 'CSVGenerationError';
  }
}
