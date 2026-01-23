import { LogRepository } from '../../infrastructure/database/repositories/LogRepository';
import { ExecutionLog } from '../entities/ExecutionLog';
import { ExecutionStatus } from '../types';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * ログサービス
 *
 * 実行ログに関するビジネスロジックを担当
 */
export class LogService {
  private logger: Logger;

  constructor(
    private repository: LogRepository,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * 実行ログを記録
   *
   * @param log - 実行ログデータ（idとcreatedAtを除く）
   * @returns 作成された実行ログエンティティ
   */
  async recordExecution(
    log: Omit<ExecutionLog, 'id' | 'createdAt'>
  ): Promise<ExecutionLog> {
    this.logger.info('実行ログを記録', {
      aiEmployeeId: log.aiEmployeeId,
      status: log.status,
      userId: log.userId,
    });

    try {
      const createdLog = await this.repository.create(log);

      this.logger.info('実行ログの記録完了', {
        logId: createdLog.id,
        status: createdLog.status,
      });

      return createdLog;
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      this.logger.error('実行ログの記録に失敗', error, {
        aiEmployeeId: log.aiEmployeeId,
      });
      throw error;
    }
  }

  /**
   * AI社員の実行履歴を取得
   *
   * @param aiEmployeeId - AI社員ID
   * @param limit - 取得件数の上限（デフォルト: 50）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async getExecutionHistory(
    aiEmployeeId: string,
    limit: number = 50
  ): Promise<ExecutionLog[]> {
    this.logger.debug('実行履歴を取得', { aiEmployeeId, limit });

    const logs = await this.repository.findByAIEmployee(aiEmployeeId, limit);

    this.logger.info('実行履歴を取得しました', {
      aiEmployeeId,
      count: logs.length,
    });

    return logs;
  }

  /**
   * 最近の実行ログを取得
   *
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async getRecentLogs(limit: number = 100): Promise<ExecutionLog[]> {
    this.logger.debug('最近の実行ログを取得', { limit });

    const logs = await this.repository.findRecent(limit);

    this.logger.info('最近の実行ログを取得しました', {
      count: logs.length,
    });

    return logs;
  }

  /**
   * ステータス別に実行ログを取得
   *
   * @param status - 実行ステータス
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async getLogsByStatus(
    status: ExecutionStatus,
    limit: number = 100
  ): Promise<ExecutionLog[]> {
    this.logger.debug('ステータス別に実行ログを取得', { status, limit });

    const logs = await this.repository.findByStatus(status, limit);

    this.logger.info('ステータス別に実行ログを取得しました', {
      status,
      count: logs.length,
    });

    return logs;
  }

  /**
   * 実行ログの統計情報を取得
   *
   * @param aiEmployeeId - AI社員ID（オプション）
   * @param limit - 対象とするログの件数（デフォルト: 100）
   * @returns 統計情報
   */
  async getStatistics(
    aiEmployeeId?: string,
    limit: number = 100
  ): Promise<{
    total: number;
    successCount: number;
    errorCount: number;
    timeoutCount: number;
    successRate: number;
    averageProcessingTime?: number;
  }> {
    this.logger.debug('統計情報を取得', { aiEmployeeId, limit });

    const logs = aiEmployeeId
      ? await this.repository.findByAIEmployee(aiEmployeeId, limit)
      : await this.repository.findRecent(limit);

    const total = logs.length;
    const successCount = logs.filter((log) => log.status === 'success').length;
    const errorCount = logs.filter((log) => log.status === 'error').length;
    const timeoutCount = logs.filter((log) => log.status === 'timeout').length;
    const successRate = total > 0 ? (successCount / total) * 100 : 0;

    // 処理時間の平均を計算（処理時間が記録されているログのみ）
    const logsWithProcessingTime = logs.filter(
      (log) => log.processingTimeSeconds !== undefined
    );
    const averageProcessingTime =
      logsWithProcessingTime.length > 0
        ? logsWithProcessingTime.reduce(
            (sum, log) => sum + (log.processingTimeSeconds || 0),
            0
          ) / logsWithProcessingTime.length
        : undefined;

    const statistics = {
      total,
      successCount,
      errorCount,
      timeoutCount,
      successRate: Math.round(successRate * 100) / 100,
      averageProcessingTime: averageProcessingTime
        ? Math.round(averageProcessingTime * 100) / 100
        : undefined,
    };

    this.logger.info('統計情報を取得しました', statistics);

    return statistics;
  }
}
