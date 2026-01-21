import { ExecutionLog } from '../../../domain/entities/ExecutionLog';
import { Platform, ExecutionStatus } from '../../../domain/types';
import { prisma } from '../prisma';
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
  /**
   * 実行ログを作成
   *
   * @param log - 実行ログデータ（idとcreatedAtを除く）
   * @returns 作成された実行ログエンティティ
   */
  async create(
    log: Omit<ExecutionLog, 'id' | 'createdAt'>
  ): Promise<ExecutionLog> {
    const createdLog = await prisma.executionLog.create({
      data: {
        aiEmployeeId: log.aiEmployeeId,
        userId: log.userId,
        userName: log.userName,
        platform: this.toPrismaPlatform(log.platform),
        channelId: log.channelId,
        inputKeyword: log.inputKeyword,
        status: this.toPrismaExecutionStatus(log.status),
        resultCount: log.resultCount,
        processingTimeSeconds: log.processingTimeSeconds,
        errorMessage: log.errorMessage,
      },
    });

    return this.toDomainEntity(createdLog);
  }

  /**
   * AI社員IDで実行ログを検索
   *
   * @param aiEmployeeId - AI社員ID
   * @param limit - 取得件数の上限（デフォルト: 50）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async findByAIEmployee(
    aiEmployeeId: string,
    limit: number = 50
  ): Promise<ExecutionLog[]> {
    const logs = await prisma.executionLog.findMany({
      where: { aiEmployeeId },
      orderBy: { createdAt: 'desc' },
      take: limit,
    });

    return logs.map((log) => this.toDomainEntity(log));
  }

  /**
   * 最近の実行ログを取得
   *
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async findRecent(limit: number = 100): Promise<ExecutionLog[]> {
    const logs = await prisma.executionLog.findMany({
      orderBy: { createdAt: 'desc' },
      take: limit,
    });

    return logs.map((log) => this.toDomainEntity(log));
  }

  /**
   * ステータス別に実行ログを取得
   *
   * @param status - 実行ステータス
   * @param limit - 取得件数の上限（デフォルト: 100）
   * @returns 実行ログエンティティの配列（作成日時の降順）
   */
  async findByStatus(
    status: ExecutionStatus,
    limit: number = 100
  ): Promise<ExecutionLog[]> {
    const logs = await prisma.executionLog.findMany({
      where: { status: this.toPrismaExecutionStatus(status) },
      orderBy: { createdAt: 'desc' },
      take: limit,
    });

    return logs.map((log) => this.toDomainEntity(log));
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
      platform: this.toDomainPlatform(log.platform),
      channelId: log.channelId,
      inputKeyword: log.inputKeyword,
      status: this.toDomainExecutionStatus(log.status),
      resultCount: log.resultCount ?? undefined,
      processingTimeSeconds: log.processingTimeSeconds ?? undefined,
      errorMessage: log.errorMessage ?? undefined,
      createdAt: log.createdAt,
    };
  }

  /**
   * Prisma Platform enumをDomain Platform typeに変換
   *
   * @param platform - Prisma Platform enum
   * @returns Domain Platform type
   */
  private toDomainPlatform(platform: PrismaPlatform): Platform {
    return platform.toLowerCase() as Platform;
  }

  /**
   * Domain Platform typeをPrisma Platform enumに変換
   *
   * @param platform - Domain Platform type
   * @returns Prisma Platform enum
   */
  private toPrismaPlatform(platform: Platform): PrismaPlatform {
    return platform.toUpperCase() as PrismaPlatform;
  }

  /**
   * Prisma ExecutionStatus enumをDomain ExecutionStatus typeに変換
   *
   * @param status - Prisma ExecutionStatus enum
   * @returns Domain ExecutionStatus type
   */
  private toDomainExecutionStatus(
    status: PrismaExecutionStatus
  ): ExecutionStatus {
    return status.toLowerCase() as ExecutionStatus;
  }

  /**
   * Domain ExecutionStatus typeをPrisma ExecutionStatus enumに変換
   *
   * @param status - Domain ExecutionStatus type
   * @returns Prisma ExecutionStatus enum
   */
  private toPrismaExecutionStatus(
    status: ExecutionStatus
  ): PrismaExecutionStatus {
    return status.toUpperCase() as PrismaExecutionStatus;
  }
}
