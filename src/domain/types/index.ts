/**
 * プラットフォーム種別
 */
export type Platform = 'slack' | 'line' | 'teams';

/**
 * 実行ステータス
 */
export type ExecutionStatus = 'success' | 'error' | 'timeout';

/**
 * 共通型定義
 */
export interface BaseEntity {
  id: string;
  createdAt: Date;
}
