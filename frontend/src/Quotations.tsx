import { useEffect, useState } from 'react';
import { api, QuotationRow, SheetCell, WorkbookDocument, WorkbookResult } from './api';

const emptyCell = (): SheetCell => ({value:null,formula:null,format:'General'});
const letters = (column:number): string => column < 26 ? String.fromCharCode(65+column) : letters(Math.floor(column/26)-1)+String.fromCharCode(65+column%26);
const currency = (value:string | number) => Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
function cellDisplay(cell:SheetCell):string {
  if(cell.error) return '#REVISAR';
  if(typeof cell.value === 'number') {
    if(cell.format.includes('%')) return `${(cell.value*100).toLocaleString('pt-BR',{maximumFractionDigits:2})}%`;
    return cell.value.toLocaleString('pt-BR',{maximumFractionDigits:6});
  }
  return String(cell.value ?? '');
}

export default function Quotations({ refresh }: { refresh: () => Promise<void> }) {
  const [url,setUrl] = useState('https://docs.google.com/spreadsheets/d/1kqfc0fzW6U-VV89_T62a-XUp1ys0rAvl/edit');
  const [document,setDocument] = useState<WorkbookDocument | null>(null);
  const [documents,setDocuments] = useState<{id:string;title:string;version:number}[]>([]);
  const [tab,setTab] = useState(0);
  const [busy,setBusy] = useState(false);
  const [dirty,setDirty] = useState(false);
  const [message,setMessage] = useState('');
  const [warnings,setWarnings] = useState<string[]>([]);
  const [summaries,setSummaries] = useState<QuotationRow[]>([]);
  const [selected,setSelected] = useState<Set<string>>(new Set());
  const [updatePrices,setUpdatePrices] = useState(false);
  const [active,setActive] = useState<[number,number] | null>(null);
  const [search,setSearch] = useState('');
  const loadList = async () => setDocuments(await api.workbookList());
  useEffect(() => { void loadList().catch(error => setMessage((error as Error).message)); },[]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if(dirty) { event.preventDefault(); event.returnValue=''; } };
    window.addEventListener('beforeunload',warn);
    return () => window.removeEventListener('beforeunload',warn);
  },[dirty]);
  const run = async (operation:()=>Promise<void>) => {
    setBusy(true);setMessage('');
    try { await operation(); } catch(error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  };
  const replaceAllowed = () => !dirty || confirm('Há alterações não salvas. Deseja substituir a planilha aberta?');
  const calculated = (result:WorkbookResult, current:WorkbookDocument) => {
    setDocument({...current,book:result.book});setSummaries(result.rows);setWarnings(result.warnings);
  };
  const imported = (book:WorkbookDocument['book'], source:string|null) => {
    setDocument({id:document?.id,version:document?.version ?? 0,title:document?.title ?? 'Cotações Petit Pedaço',
      source_url:source,book,bindings:Object.fromEntries(Object.entries(document?.bindings ?? {}).filter(([name])=>book.sheets.some(sheet=>sheet.name===name)))});
    setTab(0);setActive(null);setDirty(true);setSummaries([]);setWarnings([]);setSelected(new Set());
    setMessage('Planilha lida. Revise as abas, recalcule e salve no banco.');
  };
  const sheet = document?.book.sheets[tab];
  const columns = Math.max(1,...(sheet?.rows.map(row=>row.length) ?? [10]));
  const currentSummary = summaries.find(row=>row.sheet===sheet?.name);
  const changeCell = (row:number,column:number,text:string) => {
    if(!document || !sheet) return;
    const normalized = text.trim().replace(',','.');
    const value = /^-?\d+(\.\d+)?%$/.test(normalized) ? Number(normalized.slice(0,-1))/100 : /^-?\d+(\.\d+)?$/.test(normalized) ? Number(normalized) : text || null;
    const next = document.book.sheets.map((s,index)=>index!==tab?s:{...s,rows:s.rows.map((r,ri)=>ri!==row?r:Array.from({length:columns},(_,ci)=>ci!==column?r[ci] ?? emptyCell():{...r[ci] ?? emptyCell(),formula:text.startsWith('=')?text:null,value:text.startsWith('=')?r[ci]?.value ?? null:value,error:null}))});
    setDocument({...document,book:{sheets:next}});setDirty(true);setSummaries([]);
  };
  const activeCell = active && sheet?.rows[active[0]]?.[active[1]];
  return <div className="quotation-page">
    <section className="card quotation-tools">
      <div className="card-title"><h2>Cotação de produtos</h2><span>{dirty?'Alterações não salvas':'Banco de dados'}</span></div>
      <div className="form-grid"><label>Planilhas salvas<select disabled={busy} value={document?.id ?? ''} onChange={e=> {
        const id=e.target.value;if(!id || !replaceAllowed()) return;
        void run(async()=>{const loaded=await api.workbookGet(id);setDocument(loaded);setUrl(loaded.source_url ?? url);setTab(0);setActive(null);setDirty(false);setSummaries([]);setWarnings([]);setSelected(new Set(Object.keys(loaded.bindings)));});
      }}><option value="">Selecione uma cotação</option>{documents.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label>Link público Google Sheets<input disabled={busy} value={url} onChange={e=>setUrl(e.target.value)}/></label></div>
      <div className="quotation-actions">
        <button className="primary" disabled={busy} onClick={()=>{if(replaceAllowed()) void run(async()=>imported((await api.workbookGoogle(url)).book,url));}}>Ler planilha do Google</button>
        <label className="upload-label">Enviar Excel<input disabled={busy} type="file" accept=".xlsx" onChange={e=>{const file=e.target.files?.[0];if(file && replaceAllowed()) void run(async()=>imported((await api.workbookExcel(file)).book,null));e.target.value='';}}/></label>
        <button disabled={busy} onClick={()=>{if(replaceAllowed()){setDocument({version:0,title:'Nova cotação',source_url:null,book:{sheets:[{name:'Nova ficha',rows:Array.from({length:12},()=>Array.from({length:10},emptyCell))}]},bindings:{}});setTab(0);setDirty(true);setSummaries([]);setSelected(new Set());setActive(null);}}}>Nova cotação</button>
        <button disabled={busy || !document} onClick={()=>void run(async()=>{if(document){calculated(await api.workbookCalculate(document.book),document);setDirty(true);}})}>Recalcular custos</button>
        <button className="primary" disabled={busy || !document} onClick={()=>void run(async()=> {
          if(!document) return;
          const result=await api.workbookSave(document,Array.from(selected),updatePrices);
          calculated(result,{...document,id:result.id,version:result.version,bindings:result.bindings});setDirty(false);setSelected(new Set(Object.keys(result.bindings)));
          await loadList();await refresh();setMessage(`Salvo no banco. ${result.created} produtos criados; ${result.updated} atualizados.`);
        })}>Salvar atualizações no banco</button>
      </div>
      {busy && <p role="status">Processando a planilha…</p>}{message && <p role="status">{message}</p>}
      {document && <label>Título da cotação<input value={document.title} maxLength={160} disabled={busy} onChange={e=>{setDocument({...document,title:e.target.value});setDirty(true);}}/></label>}
      {warnings.length>0 && <details><summary>{warnings.length} avisos de cálculo / fichas para revisar</summary>{warnings.map((warning,index)=><p key={index}>{warning}</p>)}</details>}
      {selected.size>0 && <details><summary>{selected.size} produtos atualizarão custos ao salvar</summary>{Array.from(selected).map(name=><label key={name}><input type="checkbox" style={{display:'inline',width:'auto'}} checked onChange={()=>setSelected(current=>{const next=new Set(current);next.delete(name);return next;})}/> {name}</label>)}</details>}
    </section>
    {sheet && document && <section className="card quotation-editor">
      <div className="quotation-tabs"><input placeholder="Buscar aba…" value={search} onChange={e=>setSearch(e.target.value)}/><select value={tab} onChange={e=>{setTab(Number(e.target.value));setActive(null);}}>{document.book.sheets.map((s,index)=>s.name.toLowerCase().includes(search.toLowerCase())?<option key={s.name} value={index}>{s.name}</option>:null)}</select><span>{sheet.rows.length} linhas · {columns} colunas</span></div>
      <div className="formula-bar"><b>{active?`${letters(active[1])}${active[0]+1}`:'Célula'}</b><input disabled={busy || !active} aria-label="Valor ou fórmula da célula" placeholder="Selecione uma célula para editar seu valor ou fórmula" value={activeCell ? activeCell.formula ?? String(activeCell.value ?? '') : ''} onChange={e=>active && changeCell(active[0],active[1],e.target.value)}/></div>
      <div className="sheet-scroll"><table className="sheet-grid"><thead><tr><th></th>{Array.from({length:columns},(_,index)=><th key={index}>{letters(index)}</th>)}</tr></thead><tbody>{sheet.rows.map((row,rowIndex)=><tr key={rowIndex}><th>{rowIndex+1}</th>{Array.from({length:columns},(_,columnIndex)=>{const cell=row[columnIndex] ?? emptyCell();return <td key={columnIndex} className={`${cell.formula?'computed':''} ${cell.error?'cell-error':''} ${active?.[0]===rowIndex && active?.[1]===columnIndex?'cell-active':''}`} title={cell.error || cell.formula || ''}><button disabled={busy} onClick={()=>setActive([rowIndex,columnIndex])}>{cellDisplay(cell)}</button></td>;})}</tr>)}</tbody></table></div>
      <div className="quotation-actions"><button disabled={busy || sheet.rows.length>=2000} onClick={()=>{setDocument({...document,book:{sheets:document.book.sheets.map((s,i)=>i===tab?{...s,rows:[...s.rows,Array.from({length:columns},emptyCell)]}:s)}});setDirty(true);}}>+ Linha</button>
      <button disabled={busy || columns>=100} onClick={()=>{setDocument({...document,book:{sheets:document.book.sheets.map((s,i)=>i===tab?{...s,rows:s.rows.map(r=>[...r,...Array.from({length:columns-r.length+1},emptyCell)])}:s)}});setDirty(true);}}>+ Coluna</button>
      <button disabled={busy} onClick={()=>{const name=prompt('Nome da nova aba');if(name && !document.book.sheets.some(s=>s.name===name)){setDocument({...document,book:{sheets:[...document.book.sheets,{name,rows:Array.from({length:12},()=>Array.from({length:10},emptyCell))}]}});setTab(document.book.sheets.length);setDirty(true);setActive(null);}}}>+ Aba</button></div>
      <p>Selecione uma célula e edite na barra acima. Fórmulas e valores são recalculados ao salvar. Alterações ficam no sistema; a planilha do Google permanece como fonte de importação.</p>
      {currentSummary && <div className="quotation-summary"><p>Matéria-prima: <b>{currency(currentSummary.cost_price)}</b> · Custos adicionais: <b>{currency(currentSummary.additional_cost)}</b> · Preço sugerido: <b>{currency(currentSummary.sale_price)}</b></p>
        <label>SKU do produto vinculado<input disabled={busy} value={document.bindings[sheet.name] ?? currentSummary.sku} maxLength={64} onChange={e=>{setDocument({...document,bindings:{...document.bindings,[sheet.name]:e.target.value}});setDirty(true);}}/></label>
        <label><input style={{display:'inline',width:'auto'}} type="checkbox" checked={selected.has(sheet.name)} onChange={()=>setSelected(current=>{const next=new Set(current);next.has(sheet.name)?next.delete(sheet.name):next.add(sheet.name);return next;})}/> Atualizar o custo deste produto ao salvar</label>
      </div>}
      <label><input style={{display:'inline',width:'auto'}} type="checkbox" checked={updatePrices} onChange={e=>setUpdatePrices(e.target.checked)}/> Atualizar também o preço de venda dos produtos selecionados</label>
      <p>{selected.size} produtos selecionados para atualização. Use “Recalcular custos” para identificar as fichas de produto.</p>
    </section>}
  </div>;
}
