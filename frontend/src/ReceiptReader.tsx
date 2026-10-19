import { useEffect, useRef, useState } from 'react';
import { request } from './api';

export type Supplier = {id:string;name:string;cnpj:string};
type Item = {name:string;unit:string;quantity:string;total:string};
type Suggestion = {supplier_name:string;cnpj:string;fiscal_key:string;number:string;date:string;amount:string;items:Item[];warnings:string[]};
const emptyItem = ():Item=>({name:'',unit:'UN',quantity:'1',total:''});
const localDate=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Sao_Paulo'}).format(new Date());

export default function ReceiptReader({onSaved}:{onSaved:()=>Promise<void>}) {
  const [suppliers,setSuppliers]=useState<Supplier[]>([]);
  const [supplierId,setSupplierId]=useState('');
  const [supplierName,setSupplierName]=useState('');const [cnpj,setCnpj]=useState('');
  const [number,setNumber]=useState('');const [fiscalKey,setFiscalKey]=useState('');
  const [date,setDate]=useState(localDate);const [amount,setAmount]=useState('');
  const [items,setItems]=useState<Item[]>([emptyItem()]);const [text,setText]=useState('');
  const [expense,setExpense]=useState('NONE');const [payment,setPayment]=useState('PIX');
  const [candidates,setCandidates]=useState<{id:string;description:string;amount:string;date:string}[]>([]);
  const [reviewed,setReviewed]=useState(false);const [busy,setBusy]=useState(false);
  const [progress,setProgress]=useState('');const [error,setError]=useState('');const [message,setMessage]=useState('');
  const [image,setImage]=useState('');const worker=useRef<{terminate:()=>Promise<unknown>}|null>(null);
  const alive=useRef(true);const lock=useRef(false);
  useEffect(()=>{alive.current=true;request<Supplier[]>('/suppliers').then(rows=>{if(alive.current)setSuppliers(rows);}).catch(err=>{if(alive.current)setError(err.message);});return()=>{alive.current=false;void worker.current?.terminate();};},[]);
  useEffect(()=>()=>{if(image)URL.revokeObjectURL(image);},[image]);
  const applyText=async(value:string)=>{
    const result=await request<Suggestion>('/suppliers/receipts/preview',{method:'POST',body:JSON.stringify({text:value})});
    if(!alive.current)return;
    setSupplierName(result.supplier_name);setCnpj(result.cnpj);setFiscalKey(result.fiscal_key);setNumber(result.number);
    setDate(result.date||localDate());setAmount(result.amount);setItems(result.items.length?result.items:[emptyItem()]);
    const existing=suppliers.find(row=>row.cnpj&&row.cnpj===result.cnpj);setSupplierId(existing?.id||'');
    setReviewed(false);setCandidates([]);setExpense('NONE');setProgress('Leitura concluída. Revise os campos e complete os itens não reconhecidos.');
  };
  const read=async(file?:File)=>{
    if(!file||lock.current)return;
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>6*1024*1024){setError('Use uma foto JPG, PNG ou WebP com até 6 MB.');return;}
    lock.current=true;setBusy(true);setError('');setMessage('');setReviewed(false);setImage(URL.createObjectURL(file));
    try {
      setProgress('Preparando leitor local… Na primeira leitura serão baixados os arquivos de português.');
      const {createWorker}=await import('tesseract.js');
      if(!alive.current)return;
      const reader=await createWorker('por',1,{logger:event=>{if(alive.current&&event.status==='recognizing text')setProgress(`Lendo cupom: ${Math.round(event.progress*100)}%`);}});
      worker.current=reader;
      if(!alive.current){await reader.terminate();return;}
      const result=await reader.recognize(file);
      if(alive.current){setText(result.data.text);await applyText(result.data.text);}
    }catch(err){if(alive.current){setError(`Não foi possível concluir a leitura. Você pode preencher o cupom manualmente. ${(err as Error).message}`);setProgress('');}}
    finally{await worker.current?.terminate().catch(()=>{});worker.current=null;lock.current=false;if(alive.current)setBusy(false);}
  };
  const interpret=async()=>{if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await applyText(text);}catch(err){setError((err as Error).message);}finally{lock.current=false;setBusy(false);}};
  const findExpenses=async()=>{setBusy(true);setError('');try{const rows=await request<typeof candidates>(`/suppliers/receipts/candidates?purchase_date=${date}&amount=${encodeURIComponent(amount)}`);setCandidates(rows);setProgress(rows.length?'Possível duplicidade: confira as despesas abaixo. Vincular não cria nova despesa.':'Nenhuma despesa disponível com mesmo valor e data próxima.');}catch(err){setError((err as Error).message);}finally{setBusy(false);}};
  const updateItem=(index:number,field:keyof Item,value:string)=>{setItems(rows=>rows.map((row,i)=>i===index?{...row,[field]:value}:row));setReviewed(false);};
  const save=async()=>{
    if(lock.current)return;lock.current=true;setBusy(true);setError('');setMessage('');
    try{
      const result=await request<{message:string;updated_products:number}>('/suppliers/receipts',{method:'POST',body:JSON.stringify({supplier_name:supplierName,supplier_id:supplierId||null,cnpj,number,fiscal_key:fiscalKey,date,amount,items,reviewed,create_expense:expense==='NEW',cash_transaction_id:!['NEW','NONE'].includes(expense)?expense:null,payment_method:payment})});
      setMessage(`${result.message} ${result.updated_products} produto(s) criado(s)/atualizado(s).`);setReviewed(false);setNumber('');setFiscalKey('');setAmount('');setItems([emptyItem()]);setText('');setImage('');setExpense('NONE');setCandidates([]);
      setSuppliers(await request<Supplier[]>('/suppliers'));await onSaved();
    }catch(err){setError((err as Error).message);}finally{lock.current=false;setBusy(false);}
  };
  const sum=items.reduce((value,item)=>value+Number(item.total||0),0);
  return <section className="card receipt-reader"><h2>Leitor de cupons fiscais</h2>
    <p>Fotografe o cupom ou escolha uma imagem. O reconhecimento acontece no seu aparelho, sem API paga. A API interpreta o texto; o cadastro só é salvo após sua confirmação. A imagem não é enviada nem arquivada.</p>
    <fieldset disabled={busy} className="expense-fields" onChange={()=>setReviewed(false)}>
      <label>Imagem do cupom (JPG, PNG ou WebP; até 6 MB)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={event=>{void read(event.target.files?.[0]);event.target.value='';}}/></label>
      {image&&<img className="receipt-image" src={image} alt="Cupom selecionado para conferência"/>}
      <details><summary>Texto reconhecido / preenchimento manual</summary><textarea maxLength={60000} rows={7} value={text} onChange={event=>setText(event.target.value)}/><button type="button" disabled={!text.trim()} onClick={()=>void interpret()}>Interpretar texto</button></details>
      <p>Dados são sugestões. Confira CNPJ do emitente, número, data, total e cada produto.</p>
      <div className="form-grid"><label>Fornecedor<select value={supplierId} onChange={event=>{const row=suppliers.find(item=>item.id===event.target.value);setSupplierId(event.target.value);setSupplierName(row?.name||'');setCnpj(row?.cnpj||'');}}><option value="">Cadastrar / identificar pelo CNPJ</option>{suppliers.map(row=><option key={row.id} value={row.id}>{row.name} — {row.cnpj}</option>)}</select></label>
      <label>Nome do fornecedor<input maxLength={160} value={supplierName} onChange={event=>setSupplierName(event.target.value)}/></label>
      <label>CNPJ do emitente<input inputMode="numeric" maxLength={18} value={cnpj} onChange={event=>setCnpj(event.target.value.replace(/\D/g,''))}/></label>
      <label>Número e série do cupom<input maxLength={80} placeholder="Ex.: 12345 / série 1" value={number} onChange={event=>setNumber(event.target.value)}/></label>
      <label>Data da compra<input type="date" value={date} onChange={event=>{setDate(event.target.value);setCandidates([]);setExpense('NONE');}}/></label>
      <label>Total pago (R$)<input type="number" min="0.01" step="0.01" value={amount} onChange={event=>{setAmount(event.target.value);setCandidates([]);setExpense('NONE');}}/></label></div>
      <label>Chave fiscal (44 dígitos, se houver)<input inputMode="numeric" maxLength={54} value={fiscalKey} onChange={event=>setFiscalKey(event.target.value.replace(/\D/g,''))}/></label>
      <h3>Produtos comprados</h3><p>Use a mesma descrição e unidade para atualizar o item do mesmo fornecedor. Rateie descontos nos totais dos itens. Compras antigas não substituem preços de compras mais recentes.</p>
      <div className="table-wrap"><table><thead><tr><th>Produto</th><th>Quantidade</th><th>Unidade</th><th>Total do item (R$)</th><th>Preço unitário</th><th></th></tr></thead><tbody>{items.map((item,index)=><tr key={index}>
        <td><input aria-label={`Produto ${index+1}`} maxLength={160} value={item.name} onChange={event=>updateItem(index,'name',event.target.value)}/></td>
        <td><input aria-label={`Quantidade ${index+1}`} type="number" min="0.0001" step="0.0001" value={item.quantity} onChange={event=>updateItem(index,'quantity',event.target.value)}/></td>
        <td><input aria-label={`Unidade ${index+1}`} maxLength={16} value={item.unit} onChange={event=>updateItem(index,'unit',event.target.value)}/></td>
        <td><input aria-label={`Total do item ${index+1}`} type="number" min="0.01" step="0.01" value={item.total} onChange={event=>updateItem(index,'total',event.target.value)}/></td>
        <td>{Number(item.quantity)>0?(Number(item.total)/Number(item.quantity)).toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:4}):'—'}</td>
        <td><button type="button" disabled={items.length===1} onClick={()=>{setItems(rows=>rows.filter((_,i)=>i!==index));setReviewed(false);}}>Remover</button></td>
      </tr>)}</tbody></table></div>
      <div className="quotation-actions"><button type="button" disabled={items.length>=200} onClick={()=>{setItems(rows=>[...rows,emptyItem()]);setReviewed(false);}}>+ Produto comprado</button><span>Soma dos itens: {sum.toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}</span></div>
      <button type="button" disabled={!date||!amount} onClick={()=>void findExpenses()}>Conferir possíveis despesas duplicadas</button>
      <div className="form-grid"><label>Tratamento financeiro<select value={expense} onChange={event=>setExpense(event.target.value)}><option value="NONE">Somente registrar cupom e preços (sem despesa)</option><option value="NEW">Registrar uma nova despesa</option>{candidates.map(row=><option key={row.id} value={row.id}>Vincular: {row.description} — {new Date(row.date).toLocaleDateString('pt-BR')}</option>)}</select></label>
      <label>Pagamento<select value={payment} onChange={event=>setPayment(event.target.value)}><option value="PIX">PIX</option><option value="CASH">Dinheiro</option><option value="DEBIT_CARD">Débito</option><option value="CREDIT_CARD">Crédito</option></select></label></div>
      <p>Uma compra só deve gerar uma despesa. Ao enviar o Nubank, confira o alerta e vincule à despesa já registrada, sem lançar novamente. Isso não altera o CMV das vendas nem a planilha de cotação.</p>
    </fieldset>
    <label className="receipt-review"><input type="checkbox" disabled={busy} checked={reviewed} onChange={event=>setReviewed(event.target.checked)}/> Conferi o emitente, os produtos, os valores e o tratamento financeiro.</label>
    {progress&&<p role="status">{progress}</p>}{error&&<p className="alert error" role="alert">{error}</p>}{message&&<p className="alert success" role="status">{message}</p>}
    <button type="button" className="primary" disabled={busy||!reviewed} onClick={()=>void save()}>{busy?'Processando…':'Salvar cupom e atualizar preços de compra'}</button>
  </section>;
}
