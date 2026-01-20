import { Platform, ExecutionStatus } from '../types';

/**
 * 実行ログエンティティ
 *
 * AI社員の実行履歴を記録
 */
export interface ExecutionLog {
  /**
   * ログの一意識別子
   */
  id: string;

  /**
   * AI社員ID（外部キー）
   */
  aiEmployeeId: string;

  /**
   * 実行したユーザーのID
   */
  userId: string;

  /**
   * 実行したユーザーの表示名
   */
  userName: string;

  /**
   * プラットフォーム種別
   */
  platform: Platform;

  /**
   * チャンネルID
   */
  channelId: string;

  /**
   * 入力されたキーワード
   */
  inputKeyword: string;

  /**
   * 実行ステータス
   */
  status: ExecutionStatus;

  /**
   * 結果件数（成功時のみ）
   */
  resultCount?: number;

  /**
   * 処理時間（秒）
   */
  processingTimeSeconds?: number;

  /**
   * エラーメッセージ（エラー時のみ）
   */
  errorMessage?: string;

  /**
   * 作成日時
   */
  createdAt: Date;
}
