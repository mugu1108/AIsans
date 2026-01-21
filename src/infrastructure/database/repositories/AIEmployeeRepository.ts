import { AIEmployee } from '../../../domain/entities/AIEmployee';
import { Platform } from '../../../domain/types';
import { prisma } from '../prisma';
import { Platform as PrismaPlatform } from '@prisma/client';

/**
 * AI社員リポジトリ
 *
 * AI社員エンティティのデータアクセスを担当
 */
export class AIEmployeeRepository {
  /**
   * メンション文字列でAI社員を検索
   *
   * @param mention - メンション文字列（例: "@営業AI"）
   * @returns AI社員エンティティ、見つからない場合はnull
   */
  async findByMention(mention: string): Promise<AIEmployee | null> {
    const employee = await prisma.aIEmployee.findFirst({
      where: {
        botMention: mention,
        isActive: true,
      },
    });

    return employee ? this.toDomainEntity(employee) : null;
  }

  /**
   * チャンネルIDでAI社員を検索
   *
   * @param channelId - チャンネルID
   * @returns AI社員エンティティの配列
   */
  async findByChannelId(channelId: string): Promise<AIEmployee[]> {
    const employees = await prisma.aIEmployee.findMany({
      where: {
        channelId,
        isActive: true,
      },
    });

    return employees.map((emp) => this.toDomainEntity(emp));
  }

  /**
   * 有効なAI社員を全て取得
   *
   * @returns 有効なAI社員エンティティの配列
   */
  async getActiveEmployees(): Promise<AIEmployee[]> {
    const employees = await prisma.aIEmployee.findMany({
      where: {
        isActive: true,
      },
    });

    return employees.map((emp) => this.toDomainEntity(emp));
  }

  /**
   * IDでAI社員を検索
   *
   * @param id - AI社員ID
   * @returns AI社員エンティティ、見つからない場合はnull
   */
  async findById(id: string): Promise<AIEmployee | null> {
    const employee = await prisma.aIEmployee.findUnique({
      where: { id },
    });

    return employee ? this.toDomainEntity(employee) : null;
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
      platform: this.toDomainPlatform(employee.platform),
      channelId: employee.channelId,
      difyWorkflowId: employee.difyWorkflowId,
      difyApiEndpoint: employee.difyApiEndpoint,
      isActive: employee.isActive,
      createdAt: employee.createdAt,
      updatedAt: employee.updatedAt,
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
}
