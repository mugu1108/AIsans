/**
 * AI-Shine GAS Webhook
 *
 * Python APIからの呼び出しに対応
 *
 * アクション:
 * - get_domains: 既存のドメインリストを取得
 * - save_results: スクレイピング結果を保存
 * - append: 既存シートにデータを追加
 */

// 設定
const CONFIG = {
  // スプレッドシート保存先フォルダID（要変更）
  FOLDER_ID: PropertiesService.getScriptProperties().getProperty('FOLDER_ID') || '',
  // 既存リストのスプレッドシートID（get_domains用、要変更）
  EXISTING_LIST_SHEET_ID: PropertiesService.getScriptProperties().getProperty('EXISTING_LIST_SHEET_ID') || '',
};

/**
 * POSTリクエストハンドラ
 */
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const action = data.action;

    let result;

    switch (action) {
      case 'get_domains':
        result = getExistingDomains();
        break;
      case 'save_results':
        result = saveResults(data.companies, data.search_keyword);
        break;
      case 'append':
        result = appendToSheet(data.spreadsheet_id, data.companies);
        break;
      default:
        result = { status: 'error', message: `Unknown action: ${action}` };
    }

    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService
      .createTextOutput(JSON.stringify({
        status: 'error',
        message: error.toString()
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * 既存のドメインリストを取得
 */
function getExistingDomains() {
  try {
    if (!CONFIG.EXISTING_LIST_SHEET_ID) {
      return { status: 'success', domains: [] };
    }

    const ss = SpreadsheetApp.openById(CONFIG.EXISTING_LIST_SHEET_ID);
    const sheet = ss.getActiveSheet();
    const data = sheet.getDataRange().getValues();

    // ドメイン列を探す（ヘッダーから）
    const headers = data[0];
    const domainColIndex = headers.findIndex(h =>
      h.toString().toLowerCase().includes('domain') ||
      h.toString().includes('ドメイン')
    );

    if (domainColIndex === -1) {
      // ドメイン列が見つからない場合、URL列からドメインを抽出
      const urlColIndex = headers.findIndex(h =>
        h.toString().toLowerCase().includes('url') ||
        h.toString().includes('URL')
      );

      if (urlColIndex === -1) {
        return { status: 'success', domains: [] };
      }

      const domains = data.slice(1)
        .map(row => extractDomain(row[urlColIndex]))
        .filter(d => d);

      return { status: 'success', domains: [...new Set(domains)] };
    }

    const domains = data.slice(1)
      .map(row => row[domainColIndex])
      .filter(d => d);

    return { status: 'success', domains: [...new Set(domains)] };

  } catch (error) {
    console.error('getExistingDomains error:', error);
    return { status: 'error', message: error.toString(), domains: [] };
  }
}

/**
 * URLからドメインを抽出
 */
function extractDomain(url) {
  if (!url) return '';
  try {
    const match = url.toString().match(/^https?:\/\/([^\/]+)/);
    return match ? match[1] : '';
  } catch (e) {
    return '';
  }
}

/**
 * スクレイピング結果を保存
 */
function saveResults(companies, searchKeyword) {
  try {
    if (!companies || companies.length === 0) {
      return { status: 'error', message: 'No companies to save' };
    }

    // 新しいスプレッドシートを作成
    const timestamp = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyyMMdd_HHmmss');
    const title = `営業リスト_${searchKeyword}_${timestamp}`;

    const ss = SpreadsheetApp.create(title);
    const sheet = ss.getActiveSheet();

    // ヘッダー
    const headers = ['企業名', 'URL', 'お問い合わせURL', '電話番号', 'ドメイン'];
    sheet.appendRow(headers);

    // データ追加
    companies.forEach(company => {
      sheet.appendRow([
        company.company_name || '',
        company.base_url || '',
        company.contact_url || '',
        company.phone || '',
        company.domain || ''
      ]);
    });

    // フォルダに移動
    if (CONFIG.FOLDER_ID) {
      const file = DriveApp.getFileById(ss.getId());
      const folder = DriveApp.getFolderById(CONFIG.FOLDER_ID);
      folder.addFile(file);
      DriveApp.getRootFolder().removeFile(file);
    }

    // 列幅自動調整
    sheet.autoResizeColumns(1, headers.length);

    return {
      status: 'success',
      spreadsheet_id: ss.getId(),
      spreadsheet_url: ss.getUrl(),
      title: title,
      row_count: companies.length
    };

  } catch (error) {
    console.error('saveResults error:', error);
    return { status: 'error', message: error.toString() };
  }
}

/**
 * 既存シートにデータを追加
 */
function appendToSheet(spreadsheetId, companies) {
  try {
    if (!spreadsheetId || !companies || companies.length === 0) {
      return { status: 'error', message: 'Invalid parameters' };
    }

    const ss = SpreadsheetApp.openById(spreadsheetId);
    const sheet = ss.getActiveSheet();

    // データ追加
    companies.forEach(company => {
      sheet.appendRow([
        company.company_name || '',
        company.base_url || '',
        company.contact_url || '',
        company.phone || '',
        company.domain || ''
      ]);
    });

    return {
      status: 'success',
      spreadsheet_id: ss.getId(),
      spreadsheet_url: ss.getUrl(),
      added_count: companies.length
    };

  } catch (error) {
    console.error('appendToSheet error:', error);
    return { status: 'error', message: error.toString() };
  }
}

/**
 * GETリクエストハンドラ（ヘルスチェック用）
 */
function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({
      status: 'ok',
      message: 'AI-Shine GAS Webhook is running'
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * スクリプトプロパティ設定用ヘルパー
 * Apps Script エディタで実行
 */
function setupProperties() {
  const props = PropertiesService.getScriptProperties();

  // 以下を実際の値に変更してから実行
  props.setProperty('FOLDER_ID', 'YOUR_FOLDER_ID_HERE');
  props.setProperty('EXISTING_LIST_SHEET_ID', 'YOUR_SHEET_ID_HERE');

  console.log('Properties set successfully');
}
