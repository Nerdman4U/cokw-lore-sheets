// Synthetic workbooks only; exercises real dispatcher, schema reader and write/recovery classes.
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict');
function fixture(){
  let serial=20,uid=0,clears=0,locked=false,failWrite=false,blocked=false,badFormula=false;
  let nextKeys=['adult','young','ancient'];
  class Range{
    constructor(sheet,row,col,rows=1,cols=1){Object.assign(this,{sheet,row,col,rows,cols});}
    matrix(source){return Array.from({length:this.rows},(_,r)=>Array.from({length:this.cols},(_,c)=>source[this.row+r-1]?.[this.col+c-1]??''));}
    getValues(){return this.matrix(this.sheet.values);}
    getFormulas(){return this.matrix(this.sheet.formulas);}
    getDisplayValues(){return this.getValues().map(row=>row.map(String));}
    put(source,matrix){matrix.forEach((row,r)=>row.forEach((value,c)=>{const index=this.row+r-1;source[index]??=[];source[index][this.col+c-1]=value;}));return this;}
    setValues(values){this.put(this.sheet.formulas,values.map(row=>row.map(()=>'')));return this.put(this.sheet.values,values);}
    setValue(value){if(typeof value==='string' && value.startsWith("'="))value=value.slice(1);return this.setValues([[value]]);}
    setFormulas(formulas){if(failWrite){failWrite=false;throw Error('injected failure');}return this.put(this.sheet.formulas,formulas);}
    setFormula(formula){return this.setFormulas([[formula]]);}
    setNumberFormat(){return this;}
    breakApart(){return this;}
  }
  class Sheet{
    constructor(name,values=[],rows=6,columns=5){Object.assign(this,{name,values,formulas:[],rows,columns,id:++serial});}
    getName(){return this.name;}getSheetId(){return this.id;}getMaxRows(){return this.rows;}getMaxColumns(){return this.columns;}
    getLastRow(){return Math.max(1,...[this.values,this.formulas].flatMap(source=>source.map((row,i)=>row?.some(v=>v!==''&&v!=null)?i+1:1)));}
    getLastColumn(){return Math.max(1,...[this.values,this.formulas].flatMap(source=>source.map(row=>row?.length||1)));}
    getDataRange(){return this.getRange(1,1,this.getLastRow(),this.getLastColumn());}
    getRange(...args){return new Range(this,...args);}
    insertRowsAfter(_,count){this.rows+=count;}insertColumnsAfter(_,count){this.columns+=count;}
    hideSheet(){this.hidden=true;}setFrozenRows(){}setConditionalFormatRules(){}
    clear(){clears++;this.values=[];this.formulas=[];}
  }
  class Book{
    constructor(id,sheets){this.id=id;this.sheets=sheets;}
    getId(){return this.id;}getSheets(){return this.sheets;}getSheetByName(name){return this.sheets.find(s=>s.name===name)||null;}
    insertSheet(name){const sheet=new Sheet(name,[],1000,26);this.sheets.push(sheet);return sheet;}
  }
  const header=['Nimi','Otsikko','Järjestys','LahdeVälilehti','LähdeOtsikko','Kaava','Kaavarivit','Riviavain','Format'];
  const definitions=[header,
    ['TMP_Test','Stage',10,'IMP_Source','Stage','FILTER({SRC:Stage}, {SRC:Taxon}="species")','2',true,'@'],
    ['TMP_Test','Species age',20,'IMP_Source','Species age','FILTER({SRC:Species age}, {SRC:Taxon}="species")','2',false,'0.00'],
    ['TMP_Test','Age',30,'','','','',false,'0.00'],
    ['TMP_Test','Delta',40,'','','IF({COL_30}{R}="", "", ({COL_30}{R}-N({COL_30}{R-1}))*365)','2:MAX',false,'0'],
    ['TMP_Test','OK',50,'IMP_Source','OK','FILTER({SRC:OK}, {SRC:Taxon}="species")','2',false,'0']];
  const meta=new Book('meta',[
    new Sheet('Skeemat',definitions),new Sheet('Mallit',[['MalliID'],['model']]),
    new Sheet('Tiedostot',[['TiedostoID','MalliID'],['file','model']]),
    new Sheet('TiedostojenSkeemat',[['TiedostoID','Skeema'],['file','TMP_Test']])]);
  const target=new Sheet('TMP_Test',[['Stage','Species age','Age','Delta','OK'],['young',1,5],['adult',10,20],['ancient',40,0]]);
  const source=new Sheet('IMP_Source',[['Taxon','OK','Species age','Stage']]);
  const protectedSheet=new Sheet('Perustiedot',[['never clear'],['original']]);
  const book=new Book('file',[target,source,protectedSheet]);
  const properties=new Map([['LORE_SHEETS_META_SCHEMA_ID','meta'],['LORE_SHEETS_API_KEY','secret']]);
  const prop={getProperty:key=>properties.get(key)||null,setProperty:(key,value)=>properties.set(key,value),deleteProperty:key=>properties.delete(key)};
  const ctx=vm.createContext({Date,console,
    PropertiesService:{getScriptProperties:()=>prop},
    ContentService:{MimeType:{JSON:'json'},createTextOutput:text=>({setMimeType:()=>JSON.parse(text)})},
    Utilities:{DigestAlgorithm:{SHA_256:'sha'},computeDigest:(_,text)=>Array.from(crypto.createHash('sha256').update(text).digest()),getUuid:()=>String(++uid).padStart(20,'0'),sleep:()=>{}},
    LockService:{getScriptLock:()=>({tryLock:()=>!locked,releaseLock:()=>{}})},
    SpreadsheetApp:{openById:id=>{if(id==='meta')return meta;if(id==='file')return book;throw Error('not registered');},flush:()=>{
      const sheet=book.getSheetByName('TMP_Test');
      if(sheet?.formulas[1]?.[0]?.startsWith('=FILTER(')){
        for(let row=1;row<sheet.rows;row++){sheet.values[row]??=[];sheet.values[row][0]='';}
        if(blocked)sheet.values[1][0]='#REF!';
        else nextKeys.forEach((key,i)=>{sheet.values[i+1]??=[];sheet.values[i+1][0]=key;});
      }
      if(badFormula && sheet?.formulas[1]?.[3])sheet.values[1][3]='#ERROR!';
    }}
  });
  vm.runInContext(fs.readFileSync('apps-script/Code.gs','utf8'),ctx);
  vm.runInContext(fs.readFileSync('apps-script/Regeneration.gs','utf8'),ctx);
  const call=(action,extra={})=>ctx.doPost({postData:{contents:JSON.stringify({api_key:'secret',action,file_id:'file',...extra})}});
  const plan=()=>{const r=call('regenerationSchema');assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
  const run=()=>call('regenerate',{schema_revision:plan().schema_revision});
  return {ctx,call,plan,run,definitions,meta,book,target,source,protectedSheet,properties,
    clearCount:()=>clears,block:flag=>blocked=flag,fail:()=>failWrite=true,formulaError:()=>badFormula=true,
    keys:value=>nextKeys=value,lock:()=>locked=true,Sheet};
}
let tests=0;function test(name,fn){fn();tests++;console.log('OK '+name);}
test('read plan does not clear sheets',()=>{const f=fixture();assert.equal(f.plan().sheets.length,1);assert.equal(f.clearCount(),0);});
test('preserve inputs by key after row reorder, zero and stable sheet ID',()=>{
  const f=fixture(),id=f.target.id,r=f.run();assert.equal(r.ok,true);assert.equal(r.data.status,'regenerated');
  assert.equal(f.target.id,id);assert.equal(f.target.values[1][2],20);assert.equal(f.target.values[2][2],5);assert.equal(f.target.values[3][2],0);
  assert.equal(f.target.formulas[1][0],`=FILTER('IMP_Source'!$D$2:$D, 'IMP_Source'!$A$2:$A="species")`);
  assert.equal(f.target.formulas[2][3],'=IF(C3="", "", (C3-N(C2))*365)');
  assert.equal(f.target.formulas[5][3],'=IF(C6="", "", (C6-N(C5))*365)');
  assert.equal(f.protectedSheet.values[1][0],'original');assert.equal(f.book.sheets.filter(s=>s.hidden).length,1);
});
test('map input columns by old header rather than position',()=>{
  const f=fixture();f.target.values=[['Age','Stage','Species age','Delta','OK'],[5,'young',1],[20,'adult',10]];
  assert.equal(f.run().data.status,'regenerated');assert.equal(f.target.values[1][2],20);assert.equal(f.target.values[2][2],5);
});
test('boolean false and dates survive backup and restore',()=>{
  const f=fixture(),date=new Date('2020-01-02T10:00:00Z');f.target.values[1][2]=false;f.target.values[2][2]=date;
  assert.equal(f.run().data.status,'regenerated');assert.equal(f.target.values[2][2],false);assert.equal(f.target.values[1][2].toISOString(),date.toISOString());
});
test('unknown file and source header refuse before writes',()=>{
  const f=fixture();assert.equal(f.call('regenerationSchema',{file_id:'other'}).error,'TARGET_NOT_REGISTERED');
  f.source.values[0][3]='Different';assert.equal(f.call('regenerationSchema').error,'MISSING_SOURCE_HEADER');assert.equal(f.clearCount(),0);
});
test('duplicate source header refuses before writes',()=>{
  const f=fixture();f.source.values[0][1]='Stage';assert.equal(f.call('regenerationSchema').error,'DUPLICATE_HEADERS');assert.equal(f.clearCount(),0);
});
test('duplicate old keys and unkeyed inputs refuse before writes',()=>{
  const f=fixture();f.target.values[2][0]='young';assert.equal(f.call('regenerationSchema').error,'DUPLICATE_ROW_KEY');assert.equal(f.clearCount(),0);
  f.target.values[2][0]='';assert.equal(f.call('regenerationSchema').error,'INPUT_WITHOUT_ROW_KEY');assert.equal(f.clearCount(),0);
});
test('old broken imported keys refuse before writes',()=>{const f=fixture();f.target.values[1][0]='#REF!';assert.equal(f.call('regenerationSchema').error,'ROW_KEYS_NOT_READY');assert.equal(f.clearCount(),0);});
test('invalid TMP assignment and nonassigned sheet refuse',()=>{
  const f=fixture();assert.equal(f.call('regenerationSchema',{sheet_name:'Perustiedot'}).error,'SCHEMA_NOT_ASSIGNED');
  f.meta.getSheetByName('TiedostojenSkeemat').values[1][1]='Other';assert.equal(f.call('regenerationSchema').error,'INVALID_TMP_SCHEMA');assert.equal(f.clearCount(),0);
});
test('changed schema revision and busy lock refuse before writes',()=>{
  const f=fixture(),revision=f.plan().schema_revision;f.definitions[1][8]='0';
  assert.equal(f.call('regenerate',{schema_revision:revision}).error,'SCHEMA_CHANGED');assert.equal(f.clearCount(),0);
  f.lock();assert.equal(f.call('regenerate',{schema_revision:revision}).error,'REGENERATION_BUSY');
});
test('pending imports keep persisted original inputs across retry',()=>{
  const f=fixture();f.block(true);const pending=f.run();assert.equal(pending.data.status,'pending');
  assert.equal(f.properties.has('TMP_REGEN_file'),true);f.block(false);const done=f.run();
  assert.equal(done.data.status,'regenerated');assert.equal(done.data.backup_sheet,pending.data.backup_sheet);
  assert.equal(f.target.values[1][2],20);assert.equal(f.properties.has('TMP_REGEN_file'),false);
});
test('mid-write failure is recoverable using original inputs',()=>{
  const f=fixture();f.fail();const failed=f.run();assert.equal(failed.data.status,'recovery_required');
  assert.equal(failed.data.error,'REGENERATION_WRITE_FAILED');assert.equal(f.run().data.status,'regenerated');assert.equal(f.target.values[1][2],20);
});
test('removed keys reported, retained literally in persistent backup',()=>{
  const f=fixture();f.keys(['adult']);const done=f.run();assert.equal(done.data.status,'regenerated_with_warnings');
  assert.equal(done.data.sheets[0].orphaned_inputs.length,2);
  const rows=f.book.getSheetByName(done.data.backup_sheet).values;
  const payload=JSON.parse(rows.slice(1).map(row=>row[0].slice(1)).join(''));assert.equal(payload.sheets[0].inputs[0].cells.Age.cell.value,5);
});
test('duplicate new keys never restore by guessing',()=>{
  const f=fixture();f.keys(['young','young']);const r=f.run();assert.equal(r.data.status,'recovery_required');assert.equal(r.data.error,'DUPLICATE_ROW_KEY');
});
test('native formula errors are not reported as success',()=>{
  const f=fixture();f.formulaError();const r=f.run();assert.equal(r.data.status,'regenerated_with_errors');
  assert.equal(r.data.sheets[0].calculation_error_count,1);assert.equal(f.target.values[1][2],20);assert.equal(f.properties.has('TMP_REGEN_file'),false);
});
test('pending operation blocks different metadata and retains backup',()=>{
  const f=fixture();f.block(true);f.run();f.definitions[1][8]='0';assert.equal(f.run().error,'RECOVERY_PENDING');assert.equal(f.properties.has('TMP_REGEN_file'),true);
});
test('all assigned schemas preflight before any sheet is cleared',()=>{
  const f=fixture();f.meta.getSheetByName('TiedostojenSkeemat').values.push(['file','TMP_Other']);
  f.definitions.push(['TMP_Other','Key',10,'Absent','','FILTER({SRC:Key},TRUE)','2',true,'@']);
  assert.equal(f.call('regenerationSchema').error,'MISSING_SOURCE_SHEET');assert.equal(f.clearCount(),0);
});
test('native array literal syntax remains untouched',()=>{
  const f=fixture();f.definitions[4][5]='IF(TRUE, {1,2;3,4}, "text")';f.definitions[4][6]='2';
  assert.equal(f.run().data.status,'regenerated');assert.equal(f.target.formulas[1][3],'=IF(TRUE, {1,2;3,4}, "text")');
});
test('input row key columns retain their original rows',()=>{
  const f=fixture();f.definitions[1][5]='';f.definitions[1][6]='';
  assert.equal(f.run().data.status,'regenerated');assert.equal(f.target.values[1][0],'young');assert.equal(f.target.values[1][2],5);
});
test('API key is required before any schema read/write',()=>{
  const f=fixture();assert.equal(f.call('regenerate',{api_key:'wrong'}).error,'UNAUTHORIZED');assert.equal(f.clearCount(),0);
});
test('tampered pending backup is rejected before another write',()=>{
  const f=fixture();f.block(true);const pending=f.run();const backup=f.book.getSheetByName(pending.data.backup_sheet);
  backup.values[1][0]=backup.values[1][0].replace('"value":20','"value":99');
  const clears=f.clearCount();assert.equal(f.call('regenerationSchema').error,'RECOVERY_BACKUP_CHANGED');assert.equal(f.clearCount(),clears);
});
test('literal equals-prefixed user input is not turned into a formula',()=>{
  const f=fixture();f.target.values[1][2]='=not a formula';assert.equal(f.run().data.status,'regenerated');
  assert.equal(f.target.values[2][2],'=not a formula');assert.equal(f.target.formulas[2][2],'');
});
console.log(`${tests} regeneration contract tests passed`);
