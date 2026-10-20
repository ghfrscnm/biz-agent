/**
 * Приёмник заявок в Google-таблицу.
 *
 * 1. Создайте таблицу → Расширения → Apps Script → вставьте этот код.
 * 2. Развернуть → Новое развёртывание → Тип: Веб-приложение.
 *    Выполнять от имени: Я. Доступ: Все.
 * 3. Скопируйте URL веб-приложения в .env → SHEETS_WEBHOOK_URL.
 */
const HEADERS = ["Дата", "ID", "Имя", "Телефон", "Telegram", "Интерес", "Когда удобно", "Комментарий"];

function doPost(e) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (sheet.getLastRow() === 0) sheet.appendRow(HEADERS);

  const d = JSON.parse(e.postData.contents);
  sheet.appendRow([
    new Date(), d.lead_id, d.name, d.phone, d.telegram,
    d.interest, d.preferred_time || "", d.comment || "",
  ]);
  return ContentService.createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}
