import { useEffect, useRef, useState } from 'react';
import { api, QuotationBook, QuotationRow, WorkbookDocument, WorkbookResult } from './api';

const SOURCE='https://docs.google.com/spreadsheets/d/1kqfc0fzW6U-VV89_T62a-XUp1ys0rAvl/edit';

export default function Quotations({refresh,active}:{refresh:()=>Promise<void>;active:boolean}) {
  const [doc,setDoc]=useState<(Omit<WorkbookDocument,'book'> & {book?:QuotationBook})|null>(null);
  const [list,setList]=useState<{id:string;title:string;version:number}[]>([]);
  const [rows,setRows]=useState<QuotationRow[]>([]);
  const [warnings,setWarnings]=useState<string[]>([]);
  const [busy,setBusy]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [message,setMessage]=useState('');
  const [automatic,setAutomatic]=useState(true);
  const [prices,setPrices]=useState(false);
  const [lastRead,setLastRead]=useState('');
  const running=useRef(false);
  const initialized=useRef(false);
  const show=(current:WorkbookDocument,result:WorkbookResult)=>{
    setDoc({...current,book:result.book});setRows(result.rows);setWarnings(result.warnings);
  };
  const run=async(operation:()=>Promise<void>)=>{
    if(running.current)return;
    running.current=true;setBusy(true);setMessage('');
    try{await operation();}catch(error){setMessage((error as Error).message);}
    finally{running.current=false;setBusy(false);}
  };
  const open=async(id:string)=>{
    const loaded=await api.workbookSummary(id);
    setDoc(loaded);setRows(loaded.rows);setWarnings(loaded.warnings);setDirty(false);
  };
  useEffect(()=>{if(!active || initialized.current)return;initialized.current=true;void run(async()=>{
    try{const saved=await api.workbookList();setList(saved);if(saved.length)await open(saved[0].id);}
    catch(reason){initialized.current=false;throw reason;}
  });},[active]);
  useEffect(()=>{
    const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[dirty]);
  const save=async(current:WorkbookDocument,sheets:string[])=>{
    const result=await api.workbookSave(current,sheets,prices);
    show({...current,id:result.id,version:result.version,bindings:result.bindings},result);
    setDirty(false);setList(await api.workbookList());await refresh();
    setMessage(`Salvo no banco: ${result.created} produtos novos e ${result.updated} atualizados.`);
  };
  const saveCurrent=async()=>{
    if(!doc)return;
    const loaded=doc.book?{...doc,book:doc.book}:await api.workbookGet(doc.id!);
    if(loaded.version!==doc.version)throw new Error('A cotação mudou em outra sessão. Reabra Produtos antes de salvar.');
    await save(loaded,rows.map(row=>row.sheet));
  };
  const importBook=async(book:QuotationBook,source:string|null,background=false)=>{
    const result=await api.workbookCalculate(book);
    const current:WorkbookDocument={id:doc?.id,version:doc?.version??0,title:doc?.title??'Cotações Petit Pedaço',source_url:source,book:result.book,
      bindings:Object.fromEntries(Object.entries(doc?.bindings??{}).filter(([name])=>book.sheets.some(sheet=>sheet.name===name)))};
    setLastRead(new Date().toLocaleTimeString('pt-BR'));
    if(background && JSON.stringify(result.book)===JSON.stringify(doc?.book))return;
    show(current,result);setDirty(true);
    await save(current,result.rows.map(row=>row.sheet));
  };
  useEffect(()=>{
    if(!active || !automatic || !doc?.source_url || dirty)return;
    const timer=window.setInterval(()=>{
      if(window.document.visibilityState!=='visible' || running.current)return;
      void run(async()=>{const source=doc.source_url!;await importBook((await api.workbookGoogle(source)).book,source,true);});
    },60_000);
    return()=>window.clearInterval(timer);
  },[active,automatic,doc,dirty,prices]);
  const replaceAllowed=()=>!dirty || confirm('Há uma importação não salva. Deseja substituir?');
  return <div className="quotation-page">
    <section className="card quotation-tools">
      <div className="card-title"><h2>Cotação de produtos</h2><span>{dirty?'Alterações não salvas':`${rows.length} fichas reconhecidas`}</span></div>
      <p>Custos e preços sugeridos das fichas importadas, vinculados aos produtos pelo SKU. Novos produtos começam com estoque zero.</p>
      <div className="quotation-actions">
        <button disabled={busy} onClick={()=>{if(replaceAllowed())void run(async()=>{const source=doc?.source_url??SOURCE;await importBook((await api.workbookGoogle(source)).book,source);});}}>Atualizar do Google Sheets</button>
        <label className="upload-label">Importar Excel<input disabled={busy} type="file" accept=".xlsx" onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file && replaceAllowed())void run(async()=>importBook((await api.workbookExcel(file)).book,null));}}/></label>
        <button disabled={busy} onClick={()=>{const source=prompt('Endereço público da nova planilha Google Sheets:',doc?.source_url??SOURCE);if(source && replaceAllowed())void run(async()=>importBook((await api.workbookGoogle(source)).book,source));}}>Trocar fonte de importação</button>
        <button className="primary" disabled={busy || !doc} onClick={()=>void run(saveCurrent)}>Salvar atualizações no banco</button>
        <button disabled={busy} onClick={()=>{if(replaceAllowed())void run(async()=>{const saved=await api.workbookList();setList(saved);if(saved.length)await open(saved[0].id);});}}>Recarregar resumo</button>
      </div>
      {list.length>1 && <label>Cotação salva<select disabled={busy} value={doc?.id??''} onChange={event=>{const id=event.target.value;if(id && replaceAllowed())void run(()=>open(id));}}>{list.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}
      <label><input type="checkbox" style={{width:'auto',display:'inline'}} checked={automatic} onChange={event=>setAutomatic(event.target.checked)}/> Atualizar do Google a cada minuto enquanto a tela Produtos estiver aberta</label>
      {dirty && <p>Atualização automática pausada até salvar a cotação.</p>}
      {doc && !doc.source_url && <p>Fonte Excel: envie uma nova versão para atualizar os produtos.</p>}
      <label><input type="checkbox" style={{width:'auto',display:'inline'}} checked={prices} onChange={event=>setPrices(event.target.checked)}/> Atualizar também o preço de venda ao importar ou salvar</label>
      {lastRead && <p>Última leitura: {lastRead}</p>}
      {busy && <p role="status">Lendo e salvando a cotação… A primeira leitura na nuvem pode levar alguns minutos.</p>}
      {message && <p role="status">{message}</p>}
      {warnings.length>0 && <details><summary>Fichas e cálculos para revisão ({warnings.length} avisos)</summary>{warnings.map((warning,index)=><p key={index}>{warning}</p>)}</details>}
    </section>
  </div>;
}
