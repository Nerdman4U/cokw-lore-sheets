// node tests/webapp-script.test.cjs -- no Google access
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
let count=0, modified='2026-01-01T00:00:00.000Z';
function iterator(items){let i=0;return {hasNext:()=>i<items.length,next:()=>items[i++],getContinuationToken:()=> 'next'};}
const file={getId:()=> 'file',getName:()=> 'Test',getParents:()=>iterator([{getId:()=> 'folder'}]),
 getOwner:()=>({getEmail:()=> 'owner@example.invalid'}),getLastUpdated:()=>new Date(modified),
 isTrashed:()=>false,getMimeType:()=> 'application/vnd.google-apps.spreadsheet'};
const range={getFormulas:()=> [['=1+1','','','']],getValues:()=> [[2,false,0,'#REF!']]};
const sheet={getType:()=> 'GRID',getMaxRows:()=> 10,getMaxColumns:()=> 4,getSheetId:()=> 7,
 getName:()=> 'Sheet',getIndex:()=> 1,getFrozenRows:()=> 0,getFrozenColumns:()=> 0,
 hasHiddenGridlines:()=>false,getDataRange:()=>range};
const book={getSpreadsheetTimeZone:()=> 'Etc/UTC',getSheets:()=>[sheet],getNamedRanges:()=> [],
 getId:()=> 'file',getName:()=> 'Test',getSpreadsheetLocale:()=> 'en_US',getRecalculationInterval:()=> 'ON_CHANGE'};
const ctx=vm.createContext({Date,console,
 ContentService:{MimeType:{JSON:'json'},createTextOutput:s=>({setMimeType:()=>JSON.parse(s)})},
 PropertiesService:{getScriptProperties:()=>({getProperty:()=> 'secret'})},
 Session:{getEffectiveUser:()=>({getEmail:()=> 'owner@example.invalid'})},
 Utilities:{DigestAlgorithm:{SHA_256:'sha'},computeDigest:()=>[1,-1],formatDate:()=> '2026-01-01T00:00:00.000'},
 DriveApp:{searchFiles:()=>{count++;return iterator([file]);},continueFileIterator:()=>iterator([]),
 getFileById:()=>file,getFilesByType:()=>iterator([file]),
 getFolderById:()=>({isTrashed:()=>false,getFolders:()=>iterator([{getId:()=> 'child',isTrashed:()=>false},{getId:()=> 'deleted',isTrashed:()=>true}])}),
 continueFolderIterator:()=>iterator([])},
 MimeType:{GOOGLE_SHEETS:'application/vnd.google-apps.spreadsheet'},
 SpreadsheetApp:{openById:()=>book}
});
vm.runInContext(fs.readFileSync('apps-script/Code.gs','utf8'),ctx);
const run=p=>ctx.doPost({postData:{contents:JSON.stringify(p)}});
assert.equal(run({action:'list'}).error,'UNAUTHORIZED');assert.equal(count,0);
assert.equal(run({api_key:'secret',action:'about'}).data.account_id,'builtin-values-v1:01ff');
assert.equal(run({api_key:'secret',action:'list',selection:{owned_only:true,folder_ids:['folder']}}).data.files.length,1);
assert.equal(run({api_key:'secret',action:'list',selection:{owned_only:true,folder_ids:['other']}}).data.files.length,0);
const request={api_key:'secret',action:'fetch',file_id:'file',include_results:true,max_cells_per_sheet:100};
let data=run(request).data;
const cells=data.spreadsheet.sheets[0].data[0].rowData[0].values;
assert.equal(cells[0].userEnteredValue.formulaValue,'=1+1');
assert.equal(cells[0].effectiveValue.numberValue,2);
assert.equal(cells[1].userEnteredValue.boolValue,false);
assert.equal(cells[2].userEnteredValue.numberValue,0);
assert.equal(cells[3].effectiveValue.stringValue,'#REF!');
assert.equal(run({...request,max_cells_per_sheet:1}).error,'SHEET_TOO_LARGE');
assert.equal(run({...request,file_id:'../other'}).error,'INVALID_REQUEST');
assert.equal(run({...request,include_results:false}).data.spreadsheet.sheets[0].data[0].rowData[0].values[0].effectiveValue,undefined);
file.getLastUpdated=()=> new Date(Date.UTC(2026,0,1,0,0,count++));
assert.equal(run(request).error,'UNSTABLE_READ');
file.getLastUpdated=()=>new Date(modified);
sheet.getType=()=> 'OBJECT';assert.equal(run(request).error,'UNSUPPORTED_SHEET');
assert.equal(ctx.scalar_(new Date('2026-01-01T00:00:00Z'),'Etc/UTC').numberValue,46023);
assert.equal(run({api_key:'secret',action:'folders',parent_id:'root'}).data.folders.join(','),'child');
assert.equal(run({api_key:'secret',action:'folders',parent_id:'../bad'}).error,'INVALID_REQUEST');
ctx.authorize();
console.log('Built-in service contract tests passed');
