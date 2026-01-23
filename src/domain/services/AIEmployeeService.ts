import { AIEmployeeRepository } from '../../infrastructure/database/repositories/AIEmployeeRepository';
import { AIEmployee } from '../entities/AIEmployee';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * AI社員サービス
 *
 * AI社員に関するビジネスロジックを担当
 */
export class AIEmployeeService {
  private logger: Logger;

  constructor(
    private repository: AIEmployeeRepository,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * メンション文字列でAI社員を検索
   *
   * @param mention - メンション文字列（例: "@営業AI" または "営業AI"）
   * @returns AI社員エンティティ、見つからない場合はnull
   */
  async findByMention(mention: string): Promise<AIEmployee | null> {
    // メンション文字列の正規化
    const normalizedMention = this.normalizeMention(mention);

    this.logger.debug('AI社員をメンションで検索', {
      originalMention: mention,
      normalizedMention,
    });

    const employee = await this.repository.findByMention(normalizedMention);

    if (employee) {
      this.logger.info('AI社員が見つかりました', {
        id: employee.id,
        name: employee.name,
      });
    } else {
      this.logger.warn('AI社員が見つかりませんでした', {
        mention: normalizedMention,
      });
    }

    return employee;
  }

  /**
   * 有効なAI社員を全て取得
   *
   * @returns 有効なAI社員エンティティの配列
   */
  async getActiveEmployees(): Promise<AIEmployee[]> {
    this.logger.debug('有効なAI社員を全取得');

    const employees = await this.repository.getActiveEmployees();

    this.logger.info('有効なAI社員を取得しました', {
      count: employees.length,
    });

    return employees;
  }

  /**
   * IDでAI社員を検索
   *
   * @param id - AI社員ID
   * @returns AI社員エンティティ、見つからない場合はnull
   */
  async findById(id: string): Promise<AIEmployee | null> {
    this.logger.debug('AI社員をIDで検索', { id });

    const employee = await this.repository.findById(id);

    if (employee) {
      this.logger.info('AI社員が見つかりました', {
        id: employee.id,
        name: employee.name,
      });
    } else {
      this.logger.warn('AI社員が見つかりませんでした', { id });
    }

    return employee;
  }

  /**
   * チャンネルIDでAI社員を検索
   *
   * @param channelId - チャンネルID
   * @returns AI社員エンティティの配列
   */
  async findByChannelId(channelId: string): Promise<AIEmployee[]> {
    this.logger.debug('AI社員をチャンネルIDで検索', { channelId });

    const employees = await this.repository.findByChannelId(channelId);

    this.logger.info('AI社員を取得しました', {
      channelId,
      count: employees.length,
    });

    return employees;
  }

  /**
   * メンション文字列を正規化
   *
   * @param mention - メンション文字列
   * @returns 正規化されたメンション文字列（@付き）
   * @private
   */
  private normalizeMention(mention: string): string {
    const trimmed = mention.trim();

    // 既に@で始まっている場合はそのまま返す
    if (trimmed.startsWith('@')) {
      return trimmed;
    }

    // @が無い場合は追加
    return `@${trimmed}`;
  }
}
