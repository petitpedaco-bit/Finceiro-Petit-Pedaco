import { FormEvent, useEffect, useState } from 'react';
import { api, ExpenseRecord, ExpenseSuggestion } from './api';
import BankImportPanel from './BankImportPanel';

export const natureLabels:Record<string,string>={DIRECT_COST:'Custo direto',INDIRECT_COST:'Custo indireto de produção',ADMINISTRATIVE:'Despesa administrativa',COMMERCIAL:'Despesa comercial',FINANCIAL:'Despesa financeira',TAX:'Tributos',UNCLASSIFIED:'Não classificado / revisar'};
export const behaviorLabels:Record<string,string>={FIXED:'Fixo',VARIABLE:'Variável',MIXED:'Misto',UNSPECIFIED:'Não definido'};
const contexts:Record<string,string>={GENERAL:'Não informado / geral',PRODUCTION:'Produção',ADMINISTRATION:'Administração',SALES:'Vendas e distribuição'};
const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const blank=()=>({description:'',category:'',amount:'',payment_method:'PIX',payment_date:new Date().toLocaleDateString('en-CA')+'T12:00',expense_nature:'UNCLASSIFIED',expense_behavior:'UNSPECIFIED',expense_context:'GENERAL',classification_reviewed:false});

export default function ExpensePage({refresh,notify,fail}:{refresh:()=>Promise<void>;notify:(message:string)=>void;fail:(message:string)=>void}) {
  const [form,setForm]=useState(blank);
  const [review,setReview]=useState<ExpenseRecord|null>(null);
  const [suggestion,setSuggestion]=useState<ExpenseSuggestion|null>(null);
  const [records,setRecords]=useState<ExpenseRecord[]>([]);
  const [offset,setOffset]=useState(0);
  const [total,setTotal]=useState(0);
  const [busy,setBusy]=useState(false);
  const [suggesting,setSuggesting]=useState(false);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const load=async(page=offset)=>{
    setLoading(true);
    try{const result=await api.expenseHistory(page);setRecords(result.items);setTotal(result.total);}
    catch(reason){setError((reason as Error).message);}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load(offset);},[offset]);
  useEffect(()=>{
    if(form.description.trim().length<3){setSuggestion(null);return;}
    let active=true;
    const timer=window.setTimeout(()=>{
      setSuggesting(true);
      void api.suggestExpense({description:form.description,category:form.category,expense_context:form.expense_context})
        .then(result=>{if(active)setSuggestion(result);})
        .catch(reason=>{if(active)setError((reason as Error).message);})
        .finally(()=>{if(active)setSuggesting(false);});
    },700);
    return()=>{active=false;setSuggesting(false);window.clearTimeout(timer);};
  },[form.description,form.category,form.expense_context]);
  const beginReview=(record:ExpenseRecord)=>{
    setReview(record);setSuggestion(null);setError('');
    const local=new Date(record.occurred_at);const date=local.toLocaleDateString('en-CA');
    setForm({description:record.description,category:record.category??'',amount:record.amount,payment_method:record.payment_method,
      payment_date:`${date}T${String(local.getHours()).padStart(2,'0')}:${String(local.getMinutes()).padStart(2,'0')}`,
      expense_nature:record.expense_nature,expense_behavior:record.expense_behavior,expense_context:record.expense_context,classification_reviewed:false});
    window.scrollTo({top:0,behavior:'smooth'});
  };
  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;setBusy(true);setError('');
    try{
      const classification={category:form.category,expense_nature:form.expense_nature,expense_behavior:form.expense_behavior,expense_context:form.expense_context,classification_reviewed:form.classification_reviewed};
      if(review)await api.reviewExpense(review.id,classification);
      else await api.expense({...form,amount:Number(form.amount),payment_date:new Date(form.payment_date).toISOString()});
      setForm(blank());setReview(null);setSuggestion(null);
      notify(review?'Classificação atualizada. Valor e data preservados.':'Gasto registrado.');
      if(offset===0)await load(0);else setOffset(0);
      await refresh();
    }catch(reason){const message=(reason as Error).message;setError(message);fail(message);}
    finally{setBusy(false);}
  };
  return <div className="expense-page">
    <BankImportPanel onSaved={async()=>{if(offset===0)await load(0);else setOffset(0);await refresh();}}/>
    <section className="form-page card"><h2>{review?'Revisar classificação':'Custos e despesas'}</h2>
      <p className="subtitle">Classificação local por regras e exemplos confirmados, sem API paga. Sugestões não são lançadas automaticamente.</p>
      <form onSubmit={submit}><fieldset disabled={busy} className="expense-fields">
        <label>Descrição<input required maxLength={255} readOnly={!!review} value={form.description} placeholder="Ex.: Farinha para bolos ou energia da cozinha" onChange={event=>setForm({...form,description:event.target.value,classification_reviewed:false})}/></label>
        <label>Finalidade<select value={form.expense_context} onChange={event=>setForm({...form,expense_context:event.target.value,classification_reviewed:false})}>{Object.entries(contexts).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        {suggesting && <p role="status">Preparando sugestão local…</p>}
        {suggestion && <div className="expense-suggestion"><b>Sugestão: {natureLabels[suggestion.expense_nature]} · {behaviorLabels[suggestion.expense_behavior]}</b>
          <p>{suggestion.reason}</p><small>{suggestion.method==='CONFIRMED_EXAMPLE'?'Base: confirmações anteriores':'Base: regras locais e finalidade informada'}. É uma indicação, não uma decisão contábil.</small>
          <button type="button" onClick={()=>setForm({...form,expense_nature:suggestion.expense_nature,expense_behavior:suggestion.expense_behavior,category:suggestion.category,classification_reviewed:false})}>Aplicar sugestão</button>
        </div>}
        <div className="form-grid"><label>Classificação<select value={form.expense_nature} onChange={event=>setForm({...form,expense_nature:event.target.value,classification_reviewed:false})}>{Object.entries(natureLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>Comportamento<select value={form.expense_behavior} onChange={event=>setForm({...form,expense_behavior:event.target.value,classification_reviewed:false})}>{Object.entries(behaviorLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label></div>
        <label>Categoria<input required maxLength={100} value={form.category} onChange={event=>setForm({...form,category:event.target.value,classification_reviewed:false})}/></label>
        <div className="form-grid"><label>Valor (R$)<input required readOnly={!!review} type="number" min="0.01" step="0.01" value={form.amount} onChange={event=>setForm({...form,amount:event.target.value})}/></label>
        <label>Pagamento<select disabled={!!review} value={form.payment_method} onChange={event=>setForm({...form,payment_method:event.target.value})}><option value="PIX">PIX</option><option value="CASH">Dinheiro</option><option value="CARD">Cartão</option><option value="CREDIT_CARD">Crédito</option><option value="DEBIT_CARD">Débito</option></select></label></div>
        <label>Data<input required readOnly={!!review} type="datetime-local" value={form.payment_date} onChange={event=>setForm({...form,payment_date:event.target.value})}/></label>
        <label className="expense-review"><input type="checkbox" checked={form.classification_reviewed} onChange={event=>setForm({...form,classification_reviewed:event.target.checked})}/> Revisei a classificação e a finalidade deste gasto</label>
        <p className="subtitle">Agrupamento gerencial: não altera CMV, fichas de produto nem lucro automaticamente. Confira custos já incluídos nas fichas e taxas já registradas para evitar lançamentos duplicados.</p>
        {error && <p className="alert error" role="alert">{error}</p>}
        <div className="quotation-actions"><button className="primary" disabled={(review || form.expense_nature!=='UNCLASSIFIED') && !form.classification_reviewed || busy}>{busy?'Salvando…':review?'Atualizar classificação':'Registrar gasto'}</button>
          {review && <button type="button" onClick={()=>{setReview(null);setForm(blank());setSuggestion(null);}}>Cancelar revisão</button>}</div>
      </fieldset></form>
    </section>
    <section className="card abc"><div className="card-title"><h2>Histórico de custos e despesas</h2><button type="button" disabled={loading} onClick={()=>void load()}>Atualizar histórico</button></div>
      {loading && <p role="status">Carregando histórico…</p>}
      <table><thead><tr><th>Data</th><th>Descrição</th><th>Classificação</th><th>Comportamento</th><th>Valor</th><th></th></tr></thead><tbody>{records.map(record=><tr key={record.id}>
        <td>{new Date(record.occurred_at).toLocaleDateString('pt-BR')}</td><td>{record.description}</td><td>{natureLabels[record.expense_nature]}{!record.classification_reviewed && <small> · Não revisado</small>}</td><td>{behaviorLabels[record.expense_behavior]}</td><td>{money(record.amount)}</td><td><button disabled={busy} onClick={()=>beginReview(record)}>Revisar</button></td>
      </tr>)}</tbody></table>
      {!records.length && !loading && <p>Nenhum gasto registrado.</p>}
      <div className="quotation-actions"><button disabled={offset===0 || loading} onClick={()=>setOffset(Math.max(0,offset-20))}>Anterior</button><span>{total?`${offset+1}–${Math.min(offset+20,total)} de ${total}`:'0 registros'}</span><button disabled={offset+20>=total || loading} onClick={()=>setOffset(offset+20)}>Próxima</button></div>
    </section>
  </div>;
}

export function ExpenseBreakdown({start,end}:{start:string;end:string}) {
  const [result,setResult]=useState<Awaited<ReturnType<typeof api.expenseBreakdown>>|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;setResult(null);setError('');void api.expenseBreakdown(start,end).then(data=>{if(active)setResult(data);}).catch(reason=>{if(active)setError((reason as Error).message);});return()=>{active=false;};},[start,end]);
  return <section className="card abc"><div className="card-title"><h2>Gastos por classificação</h2><span>Gerencial</span></div>
    {error?<p className="alert error">{error}</p>:!result?<p>Carregando classificação…</p>:<><p className="subtitle">{result.notice}</p><table><thead><tr><th>Classificação</th><th>Comportamento</th><th>Lançamentos</th><th>Total pago</th></tr></thead><tbody>{result.groups.map(group=><tr key={`${group.expense_nature}:${group.expense_behavior}`}><td>{natureLabels[group.expense_nature]}</td><td>{behaviorLabels[group.expense_behavior]}</td><td>{group.count}</td><td>{money(group.amount)}</td></tr>)}</tbody></table>{!result.groups.length && <p>Nenhum gasto no período.</p>}</>}
  </section>;
}
