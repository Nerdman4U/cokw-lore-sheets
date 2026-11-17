/** Schema-driven TMP regeneration. Audit actions never enter this module. */
class TmpRegenerationError extends Error {
  constructor(code) { super(code); this.name = 'TmpRegenerationError'; }
}
function tmpRequire_(condition, code) {
  if (!condition) throw new TmpRegenerationError(code || 'INVALID_TMP_SCHEMA');
}
function tmpHash_(value) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, JSON.stringify(value))
    .map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
}
function tmpCell_(value) {
  return value instanceof Date ? {date:value.toISOString()} : {value:value};
}
function tmpValue_(cell) { return 'date' in cell ? new Date(cell.date) : cell.value; }
function tmpPresent_(value) { return value !== '' && value != null; }
function tmpErrorValue_(value) {
  return typeof value === 'string' && /^#(?:REF!|ERROR!|N\/A|VALUE!|NAME\?|NUM!|DIV\/0!|LOADING|SPILL!)/i.test(value);
}
function tmpKey_(value) {
  tmpRequire_(!tmpErrorValue_(value), 'ROW_KEYS_NOT_READY');
  return JSON.stringify(tmpCell_(value));
}
function tmpColumn_(index) {
  let result = '';
  for (let n=index+1; n>0; n=Math.floor((n-1)/26)) result=String.fromCharCode(65+(n-1)%26)+result;
  return result;
}
function tmpHeaders_(values) {
  const result = {};
  values.forEach((value,index) => {
    const name = String(value).trim();
    if (!name) return;
    tmpRequire_(!Object.prototype.hasOwnProperty.call(result,name), 'DUPLICATE_HEADERS');
    result[name]=index;
  });
  return result;
}

class MetaSchemaRepository {
  constructor() {
    this.id=PropertiesService.getScriptProperties().getProperty('LORE_SHEETS_META_SCHEMA_ID');
    tmpRequire_(id_(this.id), 'META_SCHEMA_NOT_CONFIGURED');
  }
  table(book,name,required) {
    const sheet=book.getSheetByName(name);
    tmpRequire_(sheet, 'INVALID_TMP_SCHEMA');
    tmpRequire_(sheet.getLastRow() <= 5000 && sheet.getLastColumn() <= 50, 'SCHEMA_TOO_LARGE');
    const values=sheet.getDataRange().getValues();
    const headers=tmpHeaders_(values[0] || []);
    required.forEach(key => tmpRequire_(key in headers, 'INVALID_TMP_SCHEMA'));
    return values.slice(1).filter(row => row.some(tmpPresent_)).map(row => {
      const result={};
      Object.keys(headers).forEach(key => result[key]=row[headers[key]] == null ? '' : row[headers[key]]);
      return result;
    });
  }
  read() {
    const book=SpreadsheetApp.openById(this.id);
    const definitions=this.table(book,'Skeemat',['Nimi','Otsikko','Järjestys','LahdeVälilehti','Kaava','Kaavarivit','Riviavain','Format']);
    const models=this.table(book,'Mallit',['MalliID']);
    const files=this.table(book,'Tiedostot',['TiedostoID','MalliID']);
    const assignments=this.table(book,'TiedostojenSkeemat',['TiedostoID','Skeema']);
    const ids=models.map(row => String(row.MalliID).trim());
    tmpRequire_(ids.every(id_) && new Set(ids).size===ids.length);
    const fileIds=files.map(row => String(row.TiedostoID).trim());
    tmpRequire_(fileIds.every(id_) && new Set(fileIds).size===fileIds.length);
    files.forEach(row => tmpRequire_(ids.includes(String(row.MalliID).trim())));
    assignments.forEach(row => tmpRequire_(
      [...ids,...fileIds].includes(String(row.TiedostoID).trim()) &&
      /^TMP_.+/.test(String(row.Skeema).trim()) &&
      definitions.some(def => String(def.Nimi).trim()===String(row.Skeema).trim())));
    const data={definitions:definitions,models:models,files:files,assignments:assignments};
    return {revision:tmpHash_(data),data:data};
  }
}

class TmpFormulaCompiler {
  constructor(book,columns) { this.book=book; this.columns=columns; this.sources={}; }
  source(sheetName,header) {
    tmpRequire_(sheetName, 'MISSING_SOURCE_HEADER');
    if (!this.sources[sheetName]) {
      const sheet=this.book.getSheetByName(sheetName);
      tmpRequire_(sheet, 'MISSING_SOURCE_SHEET');
      this.sources[sheetName]=tmpHeaders_(sheet.getRange(1,1,1,Math.max(1,sheet.getLastColumn())).getDisplayValues()[0]);
    }
    const headers=this.sources[sheetName];
    tmpRequire_(header in headers, 'MISSING_SOURCE_HEADER');
    const column=tmpColumn_(headers[header]);
    return "'"+sheetName.replace(/'/g,"''")+"'!$"+column+'$2:$'+column;
  }
  formula(def,row) {
    let formula=String(def.Kaava).trim();
    formula=formula.replace(/\{SRC:([^{}]+)\}/g,(_,header) => this.source(String(def.LahdeVälilehti).trim(),header.trim()));
    formula=formula.replace(/\{COL_(\d+)\}/g,(_,order) => {
      const index=this.columns.findIndex(col => col.order===Number(order));
      tmpRequire_(index>=0, 'UNKNOWN_FORMULA_PLACEHOLDER');
      return tmpColumn_(index);
    });
    formula=formula.replace(/\{R(?:([+-])(\d+))?\}/g,(_,sign,offset) => {
      const result=row+(sign ? (sign==='-' ? -1 : 1)*Number(offset) : 0);
      tmpRequire_(result>=1, 'INVALID_FORMULA_ROW');
      return String(result);
    });
    tmpRequire_(!/\{(?:SRC:|COL_|R(?:[+-]\d+)?\})/.test(formula), 'UNKNOWN_FORMULA_PLACEHOLDER');
    // All other syntax, including array literals and any native function, belongs to Sheets.
    return formula.startsWith('=') ? formula : '='+formula;
  }
  rows(value,maxRows) {
    const match=/^(\d+)(?::(\d+|MAX))?$/.exec(String(value).trim());
    tmpRequire_(match, 'INVALID_FORMULA_ROWS');
    const start=Number(match[1]), end=match[2]==='MAX' ? maxRows : Number(match[2] || match[1]);
    tmpRequire_(start>=2 && end>=start && end<=maxRows, 'INVALID_FORMULA_ROWS');
    return {start:start,end:end};
  }
}

class TmpInputBackupRepository {
  constructor(book) { this.book=book; this.properties=PropertiesService.getScriptProperties(); this.key='TMP_REGEN_'+book.getId(); }
  pending() {
    const raw=this.properties.getProperty(this.key);
    if (!raw) return null;
    const reference=JSON.parse(raw);
    const sheet=this.book.getSheets().find(sheet => sheet.getSheetId()===reference.sheet_id);
    tmpRequire_(sheet, 'RECOVERY_BACKUP_MISSING');
    const rows=sheet.getDataRange().getValues();
    tmpRequire_(rows[0][0]==='cokw-tmp-backup-v1', 'RECOVERY_BACKUP_MISSING');
    const payload=JSON.parse(rows.slice(1).map(row => {
      tmpRequire_(String(row[0]).startsWith('#'),'RECOVERY_BACKUP_MISSING');
      return row[0].slice(1);
    }).join(''));
    tmpRequire_(tmpHash_(payload)===reference.sha256,'RECOVERY_BACKUP_CHANGED');
    return {sheet:sheet,payload:payload};
  }
  create(payload) {
    const chunks=[];
    const text=JSON.stringify(payload);
    for (let start=0; start<text.length;) {
      let end=Math.min(text.length,start+20000);
      if (end<text.length && /[\uD800-\uDBFF]/.test(text[end-1])) end--;
      // Prefix chunks so a boundary beginning with '=' cannot become a live formula.
      chunks.push(['#'+text.slice(start,end)]); start=end;
    }
    const name='TMP_BACKUP_'+Utilities.getUuid().replace(/-/g,'').slice(0,20);
    const sheet=this.book.insertSheet(name);
    if (sheet.getMaxRows()<chunks.length+1) sheet.insertRowsAfter(sheet.getMaxRows(),chunks.length+1-sheet.getMaxRows());
    sheet.getRange(1,1).setValue('cokw-tmp-backup-v1');
    sheet.getRange(2,1,chunks.length,1).setValues(chunks);
    SpreadsheetApp.flush();
    tmpRequire_(sheet.getRange(2,1,chunks.length,1).getValues().map(row=>String(row[0]).slice(1)).join('')===text,'BACKUP_READBACK_FAILED');
    sheet.hideSheet();
    // Persist before any target is cleared. A retry reuses this exact input snapshot.
    this.properties.setProperty(this.key,JSON.stringify({sheet_id:sheet.getSheetId(),sha256:tmpHash_(payload)}));
    return {sheet:sheet,payload:payload};
  }
  complete() { this.properties.deleteProperty(this.key); }
}

class TmpRegenerator {
  constructor() { this.repository=new MetaSchemaRepository(); }
  plan(request,schema) {
    tmpRequire_(id_(request.file_id), 'INVALID_REQUEST');
    tmpRequire_(request.file_id!==this.repository.id, 'TARGET_NOT_REGISTERED');
    const data=schema.data;
    tmpRequire_(data.files.some(row => row.TiedostoID===request.file_id) || data.models.some(row => row.MalliID===request.file_id), 'TARGET_NOT_REGISTERED');
    let names=[...new Set(data.assignments.filter(row => row.TiedostoID===request.file_id).map(row => String(row.Skeema).trim()))];
    if (request.sheet_name != null) {
      tmpRequire_(typeof request.sheet_name==='string' && names.includes(request.sheet_name), 'SCHEMA_NOT_ASSIGNED');
      names=[request.sheet_name];
    }
    tmpRequire_(names.length>0, 'SCHEMA_NOT_ASSIGNED');
    const book=SpreadsheetApp.openById(request.file_id);
    const sheets=names.map(name => {
      tmpRequire_(/^TMP_.+/.test(name) && !name.startsWith('TMP_BACKUP_'), 'INVALID_TMP_SCHEMA');
      const definitions=data.definitions.filter(row => String(row.Nimi).trim()===name);
      const columns=definitions.map(def => ({name:String(def.Otsikko).trim(),order:Number(def.Järjestys),def:def})).sort((a,b)=>a.order-b.order);
      tmpRequire_(columns.length>0 && columns.every(col => col.name && Number.isSafeInteger(col.order) && col.order>0));
      tmpRequire_(new Set(columns.map(col => col.name)).size===columns.length && new Set(columns.map(col => col.order)).size===columns.length);
      columns.forEach(col => tmpRequire_([true,false,'TRUE','FALSE'].includes(col.def.Riviavain)));
      const keys=columns.filter(col => col.def.Riviavain===true || col.def.Riviavain==='TRUE');
      tmpRequire_(keys.length===1, 'INVALID_ROW_KEY');
      const existing=book.getSheetByName(name), rows=existing ? existing.getMaxRows() : 1000;
      tmpRequire_(rows>=2 && rows*Math.max(columns.length,existing ? existing.getMaxColumns() : columns.length)<=250000, 'SCHEMA_TOO_LARGE');
      const compiler=new TmpFormulaCompiler(book,columns);
      const writes=columns.filter(col => String(col.def.Kaava).trim()).map(col => {
        const bounds=compiler.rows(col.def.Kaavarivit,rows);
        const formulas=[];
        for (let row=bounds.start;row<=bounds.end;row++) formulas.push([compiler.formula(col.def,row)]);
        return {column:columns.indexOf(col)+1,start:bounds.start,formulas:formulas};
      });
      return {name:name,columns:columns,key:keys[0].name,rows:rows,writes:writes,existing:existing};
    });
    return {book:book,sheets:sheets};
  }
  capture(plan) {
    if (!plan.existing) return {name:plan.name,key:plan.key,inputs:[],old:null};
    const range=plan.existing.getDataRange(), values=range.getValues(), formulas=range.getFormulas();
    const headers=tmpHeaders_(values[0] || []);
    const inputColumns=plan.columns.filter(col => !String(col.def.Kaava).trim());
    const records=[], seen=new Set();
    for (let i=1;i<values.length;i++) {
      const cells={};
      inputColumns.forEach(col => {
        if (!(col.name in headers)) return;
        const index=headers[col.name];
        const value=values[i][index], formula=(formulas[i] || [])[index] || '';
        if (tmpPresent_(value) || formula) cells[col.name]={cell:tmpCell_(value),formula:formula};
      });
      const value=values[i][headers[plan.key]];
      if (!tmpPresent_(value)) {
        tmpRequire_(!Object.keys(cells).length, 'INPUT_WITHOUT_ROW_KEY');
        continue;
      }
      const key=tmpKey_(value);
      tmpRequire_(!seen.has(key), 'DUPLICATE_ROW_KEY');seen.add(key);
      if (Object.keys(cells).length) records.push({key:key,row:i+1,value:tmpCell_(value),cells:cells});
    }
    return {name:plan.name,key:plan.key,inputs:records,old:{values:values.map(row=>row.map(tmpCell_)),formulas:formulas},fingerprint:tmpHash_({values:values.map(row=>row.map(tmpCell_)),formulas:formulas})};
  }
  describe(request) {
    const schema=this.repository.read(), plan=this.plan(request,schema);
    // Detect ambiguous existing keys before the client asks for a write.
    if (!new TmpInputBackupRepository(plan.book).pending()) plan.sheets.forEach(sheet => this.capture(sheet));
    return {schema_revision:schema.revision,file_id:request.file_id,sheets:plan.sheets.map(sheet => ({name:sheet.name,row_key:sheet.key,rows:sheet.rows,columns:sheet.columns.map(col=>({name:col.name,order:col.order,input:!String(col.def.Kaava).trim()}))}))};
  }
  write(book,plan) {
    const sheet=plan.existing || book.insertSheet(plan.name);
    if (sheet.getMaxColumns()<plan.columns.length) sheet.insertColumnsAfter(sheet.getMaxColumns(),plan.columns.length-sheet.getMaxColumns());
    sheet.getRange(1,1,sheet.getMaxRows(),sheet.getMaxColumns()).breakApart();
    sheet.clear();sheet.setConditionalFormatRules([]);
    sheet.getRange(1,1,1,plan.columns.length).setValues([plan.columns.map(col=>col.name)]);
    plan.columns.forEach((col,i) => {
      if (String(col.def.Format).trim()) sheet.getRange(2,i+1,plan.rows-1,1).setNumberFormat(String(col.def.Format));
    });
    plan.writes.forEach(write => sheet.getRange(write.start,write.column,write.formulas.length,1).setFormulas(write.formulas));
    sheet.setFrozenRows(1);
    return sheet;
  }
  keys(sheet,plan,original) {
    const column=plan.columns.findIndex(col=>col.name===plan.key)+1;
    const values=sheet.getRange(2,column,plan.rows-1,1).getValues();
    const keys={};
    for (let i=0;i<values.length;i++) {
      const value=values[i][0];
      if (tmpErrorValue_(value)) return null;
      if (!tmpPresent_(value)) continue;
      const key=tmpKey_(value);
      tmpRequire_(!(key in keys), 'DUPLICATE_ROW_KEY');keys[key]=i+2;
    }
    // A blank imported key column is not evidence of completion when inputs await mapping.
    return !Object.keys(keys).length && original.inputs.length ? null : keys;
  }
  restore(sheet,plan,original,keys) {
    const orphaned=[];let restored=0;
    original.inputs.forEach(record => {
      if (!(record.key in keys)) {orphaned.push({key:tmpValue_(record.value),columns:Object.keys(record.cells)});return;}
      Object.keys(record.cells).forEach(name => {
        const column=plan.columns.findIndex(col=>col.name===name && !String(col.def.Kaava).trim())+1;
        tmpRequire_(column>0, 'INPUT_COLUMN_CHANGED');
        const cell=record.cells[name],range=sheet.getRange(keys[record.key],column);
        if (cell.formula) range.setFormula(cell.formula);
        else if (typeof tmpValue_(cell.cell)==='string' && tmpValue_(cell.cell).startsWith('=')) range.setValue("'"+tmpValue_(cell.cell));
        else range.setValue(tmpValue_(cell.cell));
        restored++;
      });
    });
    SpreadsheetApp.flush();
    original.inputs.forEach(record => {
      if (!(record.key in keys)) return;
      Object.keys(record.cells).forEach(name => {
        const column=plan.columns.findIndex(col=>col.name===name)+1;
        const range=sheet.getRange(keys[record.key],column),cell=record.cells[name];
        if (cell.formula) tmpRequire_(range.getFormulas()[0][0]===cell.formula,'INPUT_READBACK_FAILED');
        else tmpRequire_(JSON.stringify(tmpCell_(range.getValues()[0][0]))===JSON.stringify(cell.cell),'INPUT_READBACK_FAILED');
      });
    });
    tmpRequire_(JSON.stringify(this.keys(sheet,plan,original))===JSON.stringify(keys),'ROW_KEYS_CHANGED');
    const calculationErrors=[];let errorCount=0;
    plan.writes.forEach(write=>sheet.getRange(write.start,write.column,write.formulas.length,1).getDisplayValues().forEach((row,i)=>{
      if (row.some(tmpErrorValue_)) {
        errorCount++;
        if (calculationErrors.length<20) calculationErrors.push({cell:tmpColumn_(write.column-1)+(write.start+i),error:row[0]});
      }
    }));
    return {name:plan.name,status:'regenerated',restored_cells:restored,orphaned_inputs:orphaned,calculation_error_count:errorCount,calculation_errors:calculationErrors,unmapped_columns:original.old ? original.old.values[0].map(tmpValue_).filter(name=>name && !plan.columns.some(col=>col.name===name)) : []};
  }
  run(request) {
    const lock=LockService.getScriptLock();
    tmpRequire_(lock.tryLock(1000), 'REGENERATION_BUSY');
    try {
      const schema=this.repository.read();
      tmpRequire_(request.schema_revision===schema.revision, 'SCHEMA_CHANGED');
      const plan=this.plan(request,schema), repository=new TmpInputBackupRepository(plan.book);
      let backup=repository.pending();
      if (backup) {
        tmpRequire_(backup.payload.revision===schema.revision && JSON.stringify(backup.payload.names)===JSON.stringify(plan.sheets.map(s=>s.name)), 'RECOVERY_PENDING');
      } else {
        const originals=plan.sheets.map(sheet=>this.capture(sheet));
        backup=repository.create({revision:schema.revision,names:plan.sheets.map(s=>s.name),sheets:originals,created_at:new Date().toISOString()});
        // Human edits do not obey ScriptLock. Check the input snapshot again before clearing.
        try {
          plan.sheets.forEach((sheet,i)=>tmpRequire_(this.capture(sheet).fingerprint===originals[i].fingerprint,'TARGET_CHANGED'));
          tmpRequire_(this.repository.read().revision===schema.revision,'SCHEMA_CHANGED');
        } catch (error) {repository.complete();throw error;}
      }
      const result={status:'pending',file_id:request.file_id,backup_sheet:backup.sheet.getName(),backup_sheet_id:backup.sheet.getSheetId(),sheets:[]};
      try {
        plan.sheets.forEach((sheet,i) => {
          const written=this.write(plan.book,sheet),original=backup.payload.sheets[i];
          if (!String(sheet.columns.find(col=>col.name===sheet.key).def.Kaava).trim()) {
            const column=sheet.columns.findIndex(col=>col.name===sheet.key)+1;
            original.inputs.forEach(record=>written.getRange(record.row,column).setValue(tmpValue_(record.value)));
          }
          let keys=null,previous=null;
          for (let attempt=0;attempt<10;attempt++) {
            SpreadsheetApp.flush();keys=this.keys(written,sheet,original);
            const current=keys===null ? null : JSON.stringify(keys);
            if (current!==null && current===previous) break;
            previous=current;
            if (attempt===9) keys=null;
            if (attempt<9) Utilities.sleep(1000);
          }
          if (keys===null) result.sheets.push({name:sheet.name,status:'keys_pending'});
          else result.sheets.push(this.restore(written,sheet,original,keys));
        });
        SpreadsheetApp.flush();
        if (result.sheets.every(sheet=>sheet.status==='regenerated')) {
          repository.complete();
          result.status=result.sheets.some(sheet=>sheet.calculation_error_count) ? 'regenerated_with_errors' :
            result.sheets.some(sheet=>sheet.orphaned_inputs.length || sheet.unmapped_columns.length) ? 'regenerated_with_warnings' : 'regenerated';
        }
      } catch (error) {
        result.status='recovery_required';
        result.error=error instanceof TmpRegenerationError ? error.message : 'REGENERATION_WRITE_FAILED';
      }
      return result;
    } finally {lock.releaseLock();}
  }
}

function tmpRegeneration_(request) {
  const regeneration=new TmpRegenerator();
  return request.action==='regenerationSchema' ? regeneration.describe(request) : regeneration.run(request);
}
