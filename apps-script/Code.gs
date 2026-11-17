/** Built-in Apps Script services only. Audit operations are read-only; TMP regeneration is an explicit separate action. */
function reply_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
function id_(v) { return typeof v === 'string' && /^[A-Za-z0-9_-]+$/.test(v); }
function identity_() {
  const email = Session.getEffectiveUser().getEmail();
  if (!email) throw new Error('ACCOUNT_UNAVAILABLE');
  // Different capture profile: built-in values are not exact API userEnteredValue data.
  const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, email.toLowerCase());
  return 'builtin-values-v1:'+digest.map(b => ('0'+((b+256)%256).toString(16)).slice(-2)).join('');
}
function metadata_(file) {
  const parents = [], iterator = file.getParents();
  while (iterator.hasNext()) parents.push(iterator.next().getId());
  const owner = file.getOwner();
  return {id:file.getId(),name:file.getName(),parents:parents.sort(),
    ownedByMe:!!owner && owner.getEmail() === Session.getEffectiveUser().getEmail(),
    modifiedTime:file.getLastUpdated().toISOString()};
}
function doPost(e) {
  try {
    const request = JSON.parse(e.postData.contents);
    const key = PropertiesService.getScriptProperties().getProperty('LORE_SHEETS_API_KEY');
    if (!key || request.api_key !== key) return reply_({ok:false,error:'UNAUTHORIZED'});
    let data;
    if (request.action === 'about') data = {account_id:identity_(),capture_profile:'builtin-values-v1'};
    else if (request.action === 'list') data = list_(request);
    else if (request.action === 'regenerationSchema' || request.action === 'regenerate') data = tmpRegeneration_(request);
    else if (request.action === 'folders') data = folders_(request);
    else if (request.action === 'fetch') {
      if (!id_(request.file_id) || typeof request.include_results !== 'boolean'
          || !Number.isSafeInteger(request.max_cells_per_sheet) || request.max_cells_per_sheet < 1)
        throw new Error('INVALID_REQUEST');
      data = fetch_(request);
    } else throw new Error('INVALID_REQUEST');
    return reply_({ok:true,data:data});
  } catch (error) {
    if (typeof TmpRegenerationError !== 'undefined' && error instanceof TmpRegenerationError) return reply_({ok:false,error:error.message});
    const allowed = ['INVALID_REQUEST','UNSTABLE_READ','SHEET_TOO_LARGE','ACCOUNT_UNAVAILABLE','UNSUPPORTED_SHEET'];
    return reply_({ok:false,error:allowed.includes(error.message) ? error.message : 'GOOGLE_READ_FAILED'});
  }
}
function list_(request) {
  const s = request.selection;
  if (!s || typeof s.owned_only !== 'boolean' || !Array.isArray(s.folder_ids) || !s.folder_ids.every(id_)
      || (request.page_token != null && typeof request.page_token !== 'string')) throw new Error('INVALID_REQUEST');
  const iterator = request.page_token ? DriveApp.continueFileIterator(request.page_token)
    : DriveApp.searchFiles("mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false");
  const files = [];
  // Bound work per call even if every file is filtered out.
  for (let n=0; n<100 && iterator.hasNext(); n++) {
    const file = metadata_(iterator.next());
    if ((!s.owned_only || file.ownedByMe) && (!s.folder_ids.length || s.folder_ids.some(id => file.parents.includes(id))))
      files.push(file);
  }
  return {files:files,nextPageToken:iterator.hasNext() ? iterator.getContinuationToken() : undefined};
}
function folders_(request) {
  if (!id_(request.parent_id) || (request.page_token != null && typeof request.page_token !== 'string'))
    throw new Error('INVALID_REQUEST');
  const parent = DriveApp.getFolderById(request.parent_id);
  if (parent.isTrashed()) throw new Error('INVALID_REQUEST');
  const iterator = request.page_token ? DriveApp.continueFolderIterator(request.page_token) : parent.getFolders();
  const folders = [];
  for (let n=0;n<100 && iterator.hasNext();n++) {
    const child = iterator.next();
    if (!child.isTrashed()) folders.push(child.getId());
  }
  return {folders:folders,nextPageToken:iterator.hasNext() ? iterator.getContinuationToken() : undefined};
}
function scalar_(value, timeZone) {
  if (value instanceof Date) {
    // Preserve the spreadsheet's wall-clock date/time as a Sheets serial, not an ISO string.
    const wall = Utilities.formatDate(value,timeZone,"yyyy-MM-dd'T'HH:mm:ss.SSS");
    return {numberValue:(Date.parse(wall+'Z')-Date.UTC(1899,11,30))/86400000};
  }
  if (typeof value === 'number') return {numberValue:value};
  if (typeof value === 'boolean') return {boolValue:value};
  return value === '' ? {} : {stringValue:String(value)};
}
function book_(book, request) {
  const timeZone = book.getSpreadsheetTimeZone();
  const sheets = book.getSheets().map(sheet => {
    if (String(sheet.getType()) !== 'GRID') throw new Error('UNSUPPORTED_SHEET');
    const rows=sheet.getMaxRows(), columns=sheet.getMaxColumns();
    if (rows*columns>request.max_cells_per_sheet) throw new Error('SHEET_TOO_LARGE');
    const props={sheetId:sheet.getSheetId(),title:sheet.getName(),index:sheet.getIndex()-1,sheetType:'GRID',
      gridProperties:{rowCount:rows,columnCount:columns,frozenRowCount:sheet.getFrozenRows(),
        frozenColumnCount:sheet.getFrozenColumns(),hideGridlines:sheet.hasHiddenGridlines()}};
    const range=sheet.getDataRange(), formulas=range.getFormulas(), values=range.getValues();
    const rowData=values.map((row,ri) => ({values:row.map((value,ci) => {
      const scalar=scalar_(value,timeZone), formula=formulas[ri][ci];
      const cell={userEnteredValue:formula ? {formulaValue:formula} : scalar};
      if (request.include_results) cell.effectiveValue=scalar;
      return cell;
    })}));
    return {properties:props,data:[{startRow:0,startColumn:0,rowData:rowData}]};
  });
  const namedRanges=book.getNamedRanges().map(named => {
    const range=named.getRange();
    return {namedRangeId:named.getName(),name:named.getName(),range:{sheetId:range.getSheet().getSheetId(),
      startRowIndex:range.getRow()-1,endRowIndex:range.getLastRow(),
      startColumnIndex:range.getColumn()-1,endColumnIndex:range.getLastColumn()}};
  });
  return {spreadsheetId:book.getId(),properties:{title:book.getName(),locale:book.getSpreadsheetLocale(),
    timeZone:timeZone,autoRecalc:String(book.getRecalculationInterval())},namedRanges:namedRanges,sheets:sheets};
}
function fetch_(request) {
  for (let attempt=0;attempt<3;attempt++) {
    const file=DriveApp.getFileById(request.file_id);
    if (file.isTrashed() || file.getMimeType() !== 'application/vnd.google-apps.spreadsheet') throw new Error('INVALID_REQUEST');
    const before=metadata_(file);
    const spreadsheet=book_(SpreadsheetApp.openById(request.file_id),request);
    const after=metadata_(DriveApp.getFileById(request.file_id));
    if (JSON.stringify(before) === JSON.stringify(after)) return {metadata:after,spreadsheet:spreadsheet};
  }
  throw new Error('UNSTABLE_READ');
}
/** Run in the editor once after changing scopes; approve the Google permission prompt. */
function authorize() {
  identity_();
  const files=DriveApp.getFilesByType(MimeType.GOOGLE_SHEETS);
  if (files.hasNext()) SpreadsheetApp.openById(files.next().getId()).getName();
  console.log('Built-in Drive and Spreadsheet services authorized.');
}
