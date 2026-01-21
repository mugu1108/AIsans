import { CompanyData } from '../dify/DifyTypes';
import { CSVGenerationError } from '../../utils/errors';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * CSVジェネレーター
 *
 * 企業データをCSV形式に変換
 */
export class CSVGenerator {
  private logger: Logger;

  constructor(logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * 企業データをCSVに変換
   *
   * @param data - 企業データ配列
   * @returns UTF-8 BOM付きCSVバッファ
   * @throws CSVGenerationError データが空の場合
   */
  generate(data: CompanyData[]): Buffer {
    this.logger.debug('CSV生成を開始', { dataCount: data?.length || 0 });

    if (!data || data.length === 0) {
      const error = new CSVGenerationError('CSVデータが空です');
      this.logger.error('CSV生成エラー: データが空', error);
      throw error;
    }

    const headers = this.extractHeaders(data);
    this.logger.debug('CSVヘッダーを抽出', { headers });

    const csvLines = [
      headers.join(','),
      ...data.map((row) => this.convertRowToCSV(row, headers)),
    ];

    const csvContent = csvLines.join('\n');

    // UTF-8 BOM付きで返却（Excel対応）
    const buffer = Buffer.concat([
      Buffer.from('\uFEFF', 'utf8'),
      Buffer.from(csvContent, 'utf8'),
    ]);

    this.logger.info('CSV生成完了', {
      rowCount: data.length,
      bufferSize: buffer.length,
    });

    return buffer;
  }

  /**
   * データからヘッダーを抽出
   *
   * @param data - 企業データ配列
   * @returns ヘッダー配列
   */
  private extractHeaders(data: CompanyData[]): string[] {
    const headerSet = new Set<string>();

    // 全レコードからキーを収集
    data.forEach((row) => {
      Object.keys(row).forEach((key) => headerSet.add(key));
    });

    // 優先順位付きでソート
    const priorityHeaders = ['companyName', 'companyUrl', 'contactUrl'];
    const headers: string[] = [];

    // 優先ヘッダーを先に追加
    priorityHeaders.forEach((key) => {
      if (headerSet.has(key)) {
        headers.push(key);
        headerSet.delete(key);
      }
    });

    // 残りのヘッダーを追加
    headers.push(...Array.from(headerSet).sort());

    return headers;
  }

  /**
   * 1行のデータをCSV形式に変換
   *
   * @param row - 企業データ
   * @param headers - ヘッダー配列
   * @returns CSV行文字列
   */
  private convertRowToCSV(row: CompanyData, headers: string[]): string {
    return headers
      .map((header) => {
        const value = row[header];
        return this.escapeCSVValue(value);
      })
      .join(',');
  }

  /**
   * CSV値をエスケープ
   *
   * @param value - エスケープ対象の値
   * @returns エスケープ済み文字列
   */
  private escapeCSVValue(value: unknown): string {
    if (value === null || value === undefined) {
      return '""';
    }

    const stringValue = String(value);

    // カンマ、改行、ダブルクォートを含む場合はエスケープ
    if (
      stringValue.includes(',') ||
      stringValue.includes('\n') ||
      stringValue.includes('"')
    ) {
      // ダブルクォートを2つに変換
      const escaped = stringValue.replace(/"/g, '""');
      return `"${escaped}"`;
    }

    return `"${stringValue}"`;
  }
}
