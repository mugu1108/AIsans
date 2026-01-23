import { ExecutionLog } from '../../../domain/entities/ExecutionLog';
import { ExecutionStatus } from '../../../domain/types';
import { prisma } from '../prisma';
import {
  toDomainPlatform,
  toDomainExecutionStatus,
  toPrismaPlatform,
  toPrismaExecutionStatus,
} from '../converters';
import { DatabaseError } from '../../../utils/errors';
import { Logger, ConsoleLogger } from '../../../utils/logger';
import {
  Platform as PrismaPlatform,
  ExecutionStatus as PrismaExecutionStatus,
} from '@prisma/client';

/**
 * 実行ログリポジトリ
 *
 * 実行ログエンティティのデータアクセスを担当
 */
export class LogRepository {
  private logger: Logger;

  constructor(logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
  }
  /**
   * 実行ログを作成
   *
   * @param log - 実行ログデータ（idとcreatedAtを除く）
   * @returns 作成された実行ログエンティティ
   * @throws DatabaseError データベースエラー発生時
   */
  async create(
    log: Omit<ExecutionLog, 'id' | 'createdAt'>
  ): Promise<ExecutionLog> {
    try {
      this.logger.debug(
        `実行ログを作成中: aiEmployeeId=${log.aiEmployeeId}, status=${log.status}`
      );

      const createdLog = await prisma.executionLog.create({
        data: {
          aiEmployeeId: log.aiEmployeeId,
          userId: log.userId,
          userName: log.userName,
          platform: toPrismaPlatform(log.platform),
          channelId: log.channelId,
          inputKeyword: log.inputKeyword,
          status: toPrismaExecutionStatus(log.status),
          resultCount: log.resultCount,
          processingTimeSeconds: log.processingTimeSeconds,
          errorMessage: log.errorMessage,
        },
      });

      this.logger.info(`実行ログを作成: id=${createdLog.id}`);

      return this.toDomainEntity(createdLog);
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('実行ログ作成エラー', err);
      throw new DatabaseError(`実行ログの作成に失敗しました: ${err.message}`);
    }
  }

  /**
   * AI社員IDで実行ログを検索
   *
   * @param aiEmployeeId - AI社員ID
   * @param limit - 取得件数の上限（デフォルト: 50）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   * @throws DatabaseError データベースエラー発生時
   */
  async findByAIEmployee(
    aiEmployeeId: string,
    limit: number = 50
  ): Promise<ExecutionLog[]> {
    try {
      this.logger.debug(`実行ログを検索中: aiEmployeeId=${aiEmployeeId}, limit=${limit}`);

      const logs = await prisma.executionLog.findMany({
        where: { aiEmployeeId },
        orderBy: { createdAt: 'desc' },
        take: limit,
      });

      this.logger.info(`実行ログを${logs.length}件取得: aiEmployeeId=${aiEmployeeId}`);

      return logs.map((log) => this.toDomainEntity(log));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error(`実行ログ検索エラー: aiEmployeeId=${aiEmployeeId}`, err);
      throw new DatabaseError(`実行ログの検索に失敗しました: ${err.message}`);
    }
  }

  /**
   * 最近の実行ログを取得
   *
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   * @throws DatabaseError データベースエラー発生時
   */
  async findRecent(limit: number = 100): Promise<ExecutionLog[]> {
    try {
      this.logger.debug(`最近の実行ログを取得中: limit=${limit}`);

      const logs = await prisma.executionLog.findMany({
        orderBy: { createdAt: 'desc' },
        take: limit,
      });

      this.logger.info(`最近の実行ログを${logs.length}件取得しました`);

      return logs.map((log) => this.toDomainEntity(log));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('実行ログ取得エラー', err);
      throw new DatabaseError(`実行ログの取得に失敗しました: ${err.message}`);
    }
  }

  /**
   * ステータス別に実行ログを取得
   *
   * @param status - 実行ステータス
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   * @throws DatabaseError データベースエラー発生時
   */
  async findByStatus(
    status: ExecutionStatus,
    limit: number = 100
  ): Promise<ExecutionLog[]> {
    try {
      this.logger.debug(`実行ログを検索中: status=${status}, limit=${limit}`);

      const logs = await prisma.executionLog.findMany({
        where: { status: toPrismaExecutionStatus(status) },
        orderBy: { createdAt: 'desc' },
        take: limit,
      });

      this.logger.info(`実行ログを${logs.length}件取得: status=${status}`);

      return logs.map((log) => this.toDomainEntity(log));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error(`実行ログ検索エラー: status=${status}`, err);
      throw new DatabaseError(`実行ログの検索に失敗しました: ${err.message}`);
    }
  }

  /**
   * PrismaモデルをDomainエンティティに変換
   *
   * @param log - Prisma ExecutionLogモデル
   * @returns Domain ExecutionLogエンティティ
   */
  private toDomainEntity(log: {
    id: string;
    aiEmployeeId: string;
    userId: string;
    userName: string;
    platform: PrismaPlatform;
    channelId: string;
    inputKeyword: string;
    status: PrismaExecutionStatus;
    resultCount: number | null;
    processingTimeSeconds: number | null;
    errorMessage: string | null;
    createdAt: Date;
  }): ExecutionLog {
    return {
      id: log.id,
      aiEmployeeId: log.aiEmployeeId,
      userId: log.userId,
      userName: log.userName,
      platform: toDomainPlatform(log.platform),
      channelId: log.channelId,
      inputKeyword: log.inputKeyword,
      status: toDomainExecutionStatus(log.status),
      resultCount: log.resultCount ?? undefined,
      processingTimeSeconds: log.processingTimeSeconds ?? undefined,
      errorMessage: log.errorMessage ?? undefined,
      createdAt: log.createdAt,
    };
  }
}
