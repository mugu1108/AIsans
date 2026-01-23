/**
 * プラットフォーム種別
 */
export type Platform = 'slack' | 'line' | 'teams';

/**
 * 実行ステータス
 */
export type ExecutionStatus = 'success' | 'error' | 'timeout';

/**
 * 共通エンティティ基底インターフェース
 */
export interface BaseEntity {
  /**
   * エンティティの一意識別子
   */
  id: string;

  /**
   * 作成日時
   */
  createdAt: Date;
}

/**
 * 更新可能エンティティ基底インターフェース
 */
export interface UpdatableEntity extends BaseEntity {
  /**
   * 更新日時
   */
  updatedAt: Date;
}
