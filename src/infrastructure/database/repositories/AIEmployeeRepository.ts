import { AIEmployee } from '../../../domain/entities/AIEmployee';
import { prisma } from '../prisma';
import { toDomainPlatform } from '../converters';
import { DatabaseError } from '../../../utils/errors';
import { Logger, ConsoleLogger } from '../../../utils/logger';
import { Platform as PrismaPlatform } from '@prisma/client';

/**
 * AI社員リポジトリ
 *
 * AI社員エンティティのデータアクセスを担当
 */
export class AIEmployeeRepository {
  private logger: Logger;

  constructor(logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
  }
  /**
   * メンション文字列でAI社員を検索
   *
   * @param mention - メンション文字列（例: "@営業AI"）
   * @returns AI社員エンティティ、見つからない場合はnull
   * @throws DatabaseError データベースエラー発生時
   */
  async findByMention(mention: string): Promise<AIEmployee | null> {
    try {
      this.logger.debug(`AI社員を検索中: mention=${mention}`);

      const employee = await prisma.aIEmployee.findFirst({
        where: {
          botMention: mention,
          isActive: true,
        },
      });

      if (employee) {
        this.logger.info(`AI社員を発見: id=${employee.id}, name=${employee.name}`);
      } else {
        this.logger.debug(`AI社員が見つかりません: mention=${mention}`);
      }

      return employee ? this.toDomainEntity(employee) : null;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error(`AI社員検索エラー: mention=${mention}`, err);
      throw new DatabaseError(`AI社員の検索に失敗しました: ${err.message}`);
    }
  }

  /**
   * チャンネルIDでAI社員を検索
   *
   * @param channelId - チャンネルID
   * @returns AI社員エンティティの配列
   * @throws DatabaseError データベースエラー発生時
   */
  async findByChannelId(channelId: string): Promise<AIEmployee[]> {
    try {
      this.logger.debug(`チャンネルのAI社員を検索中: channelId=${channelId}`);

      const employees = await prisma.aIEmployee.findMany({
        where: {
          channelId,
          isActive: true,
        },
      });

      this.logger.info(`AI社員を${employees.length}件発見: channelId=${channelId}`);

      return employees.map((emp) => this.toDomainEntity(emp));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error(`AI社員検索エラー: channelId=${channelId}`, err);
      throw new DatabaseError(`AI社員の検索に失敗しました: ${err.message}`);
    }
  }

  /**
   * 有効なAI社員を全て取得
   *
   * @returns 有効なAI社員エンティティの配列
   * @throws DatabaseError データベースエラー発生時
   */
  async getActiveEmployees(): Promise<AIEmployee[]> {
    try {
      this.logger.debug('有効なAI社員を全て取得中');

      const employees = await prisma.aIEmployee.findMany({
        where: {
          isActive: true,
        },
      });

      this.logger.info(`有効なAI社員を${employees.length}件取得しました`);

      return employees.map((emp) => this.toDomainEntity(emp));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('AI社員取得エラー', err);
      throw new DatabaseError(`AI社員の取得に失敗しました: ${err.message}`);
    }
  }

  /**
   * IDでAI社員を検索
   *
   * @param id - AI社員ID
   * @returns AI社員エンティティ、見つからない場合はnull
   * @throws DatabaseError データベースエラー発生時
   */
  async findById(id: string): Promise<AIEmployee | null> {
    try {
      this.logger.debug(`AI社員を検索中: id=${id}`);

      const employee = await prisma.aIEmployee.findUnique({
        where: { id },
      });

      if (employee) {
        this.logger.info(`AI社員を発見: id=${employee.id}, name=${employee.name}`);
      } else {
        this.logger.debug(`AI社員が見つかりません: id=${id}`);
      }

      return employee ? this.toDomainEntity(employee) : null;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error(`AI社員検索エラー: id=${id}`, err);
      throw new DatabaseError(`AI社員の検索に失敗しました: ${err.message}`);
    }
  }

  /**
   * PrismaモデルをDomainエンティティに変換
   *
   * @param employee - Prisma AIEmployeeモデル
   * @returns Domain AIEmployeeエンティティ
   */
  private toDomainEntity(employee: {
    id: string;
    name: string;
    botMention: string;
    platform: PrismaPlatform;
    channelId: string;
    difyWorkflowId: string;
    difyApiEndpoint: string;
    isActive: boolean;
    createdAt: Date;
    updatedAt: Date;
  }): AIEmployee {
    return {
      id: employee.id,
      name: employee.name,
      botMention: employee.botMention,
      platform: toDomainPlatform(employee.platform),
      channelId: employee.channelId,
      difyWorkflowId: employee.difyWorkflowId,
      difyApiEndpoint: employee.difyApiEndpoint,
      isActive: employee.isActive,
      createdAt: employee.createdAt,
      updatedAt: employee.updatedAt,
    };
  }
}
