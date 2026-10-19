import { FormEvent, useEffect, useRef, useState } from 'react';
import { api, BankChoice, BankPreview, BankRecord } from './api';
import { defaultBankChoice, invalidBankChoice } from './bankImportChoices';
import BankMovementEditor from './BankMovementEditor';
import { emptyBankFilters } from './bankHistoryFilters';

const natures:Record<string,string>={UNCLASSIFIED:'Não classificado / revisar',DIRECT_COST:'Custo direto',INDIRECT_COST:'Custo indireto',ADMINISTRATIVE:'Administrativa',COMMERCIAL:'Comercial',FINANCIAL:'Financeira',TAX:'Tributos'};
const behaviors:Record<string,string>={UNSPECIFIED:'Não definido',FIXED:'Fixo',VARIABLE:'Variável',MIXED:'Misto'};
const contexts:Record<string,string>={GENERAL:'Geral / não informado',PRODUCTION:'Produção',ADMINISTRATION:'Administração',SALES:'Vendas'};
const actions:Record<string,string>={BANK_ONLY:'Somente conferência bancária',INCOME:'Receita registrada',EXPENSE:'Despesa registrada',LINK:'Vinculado a lançamento existente'};
const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const date=(value:string)=>new Date(value).toLocaleDateString('pt-BR');

export default function BankImportPanel({onSaved,refreshVersion=0}:{onSaved:()=>Promise<void>;refreshVersion?:number}) {
  const [file,setFile]=useState<File|null>(null);
  const [preview,setPreview]=useState<BankPreview|null>(null);
  const [choices,setChoices]=useState<Record<string,BankChoice>>({});
  const [selected,setSelected]=useState<Record<string,boolean>>({});
  const [reviewed,setReviewed]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [history,setHistory]=useState<BankRecord[]>([]);
  const [offset,setOffset]=useState(0);
  const [total,setTotal]=useState(0);
  const [loading,setLoading]=useState(false);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [historyError,setHistoryError]=useState('');
  const [editing,setEditing]=useState<{id:string;action?:BankChoice['action']}|null>(null);
  const [filterDraft,setFilterDraft]=useState(emptyBankFilters);
  const [filters,setFilters]=useState(emptyBankFilters);
  const historyRequest=useRef<AbortController|null>(null);
  const load=async(page=offset)=>{
    historyRequest.current?.abort();const request=new AbortController();historyRequest.current=request;
    setLoading(true);setHistoryError('');
    try{const data=await api.bankHistory(page,filters,request.signal);if(!request.signal.aborted){setHistory(data.items);setTotal(data.total);if(page>0&&page>=data.total)setOffset(Math.max(0,Math.floor((data.total-1)/20)*20));}}
    catch(reason){if(!request.signal.aborted)setHistoryError((reason as Error).message);}
    finally{if(!request.signal.aborted)setLoading(false);}
  };
  useEffect(()=>{if(historyOpen)void load(offset);return()=>historyRequest.current?.abort();},[historyOpen,offset,refreshVersion,filters]);
  const applyFilters=(event:FormEvent)=>{event.preventDefault();setOffset(0);setHistory([]);setTotal(0);setFilters({...filterDraft});};
  const clearFilters=()=>{setFilterDraft(emptyBankFilters());setFilters(emptyBankFilters());setOffset(0);setHistory([]);setTotal(0);};
  useEffect(()=>{if(refreshVersion){setPreview(null);setChoices({});setSelected({});setReviewed(false);}},[refreshVersion]);
  const change=(id:string,fields:Partial<BankChoice>)=>{setChoices(current=>({...current,[id]:{...current[id],...fields}}));setReviewed(false);};
  const read=async()=>{
    if(!file || busy)return;setBusy(true);setError('');setMessage('');setPreview(null);setReviewed(false);
    try{
      const result=await api.bankPreview(file);setPreview(result);
      setChoices(Object.fromEntries(result.rows.map(row=>[row.fingerprint,defaultBankChoice(row.fingerprint)])));
      setSelected(Object.fromEntries(result.rows.map(row=>[row.fingerprint,!row.duplicate])));
    }catch(reason){setError((reason as Error).message);}finally{setBusy(false);}
  };
  const save=async()=>{
    if(!file || !reviewed || busy)return;setBusy(true);setError('');setMessage('');
    try{
      const rows=Object.values(choices).filter(row=>selected[row.fingerprint]);
      const result=await api.bankSave(file,rows);
      // A resposta de sucesso invalida a prévia antes das consultas: evita salvar duas vezes se a atualização falhar.
      setPreview(null);setChoices({});setSelected({});setReviewed(false);
      setMessage(`${result.saved} movimentações salvas; ${result.expenses} despesas criadas; ${result.linked} vínculos; ${result.skipped} duplicadas ignoradas.`);
      if(historyOpen&&offset===0)await load(0);
      setHistoryOpen(true);if(offset!==0)setOffset(0);
      await onSaved();
    }catch(reason){setError((reason as Error).message);}finally{setBusy(false);}
  };
  const selectedRows=preview?.rows.filter(row=>selected[row.fingerprint])??[];
  const invalid=selectedRows.some(row=>invalidBankChoice(choices[row.fingerprint],row.direction));
  return <section className="card bank-import"><h2>Importar extrato PDF — Nubank</h2>
    <p>Leia entradas e saídas e revise antes de salvar. O PDF não é guardado; somente as movimentações selecionadas.</p>
    <p className="subtitle">Conferência bancária não altera receitas, despesas ou estoque. Para uma saída impactar o financeiro, escolha explicitamente “Registrar nova despesa”. Entradas não criam vendas.</p>
    <p className="subtitle">Privacidade: o sistema atual não exige login. Pessoas com o endereço da API podem acessar os lançamentos. CPF e contas são ocultados, mas nomes e descrições permanecem; não importe dados sensíveis sem restringir o acesso.</p>
    <fieldset disabled={busy}><label>PDF original exportado pelo Nubank (até 8 MB e 40 páginas)<input type="file" accept="application/pdf,.pdf" onChange={event=>{setFile(event.target.files?.[0]??null);setPreview(null);setChoices({});setSelected({});setReviewed(false);setError('');setMessage('');}}/></label>
      <button type="button" className="primary" disabled={!file || busy} onClick={()=>void read()}>{busy?'Processando…':'Ler PDF e preparar prévia'}</button>
      {preview && <><p><b>{preview.rows.length} movimentações</b> · Entradas: {money(preview.income)} · Saídas: {money(preview.expense)} · Totais diários conferidos.</p>
        {preview.warnings.map(warning=><p className="subtitle" key={warning}>{warning}</p>)}
        <div className="bank-table"><table><thead><tr><th>Importar</th><th>Data / direção</th><th>Descrição</th><th>Valor</th><th>Tratamento após revisão</th></tr></thead><tbody>{preview.rows.map(row=>{
          const choice=choices[row.fingerprint];return <tr key={row.fingerprint}><td><input aria-label={`Importar ${row.description}`} type="checkbox" disabled={row.duplicate} checked={!!selected[row.fingerprint]} onChange={event=>{setSelected({...selected,[row.fingerprint]:event.target.checked});setReviewed(false);}}/>{row.duplicate && <small>Já importado</small>}</td>
            <td>{date(row.occurred_at)}<br/>{row.direction==='INCOME'?'Entrada':'Saída'}</td><td className="bank-description">{row.description}{!!row.receipts?.length&&<div className="receipt-duplicate-alert" role="alert">Possível duplicidade: {row.receipts.length} cupom(ns) com mesmo valor em até 3 dias ({row.receipts.map(item=>item.supplier).join(', ')}). Confira o pagamento. Se já houver despesa, use Vincular ou somente conferência, não lance novamente.</div>}</td><td>{money(row.amount)}</td><td className="bank-treatment">
              {!row.duplicate && <><select aria-label="Tratamento da movimentação" disabled={!selected[row.fingerprint]} value={choice.action} onChange={event=>change(row.fingerprint,{action:event.target.value as BankChoice['action'],cash_transaction_id:null})}>
                <option value="BANK_ONLY">Somente conferência (sem impacto financeiro)</option><option value="LINK">Vincular a lançamento existente</option>{row.direction==='EXPENSE' && <option value="EXPENSE">Registrar nova despesa (altera lucro)</option>}</select>
                {!!row.candidates.length && <small>{row.candidates.length} possíveis lançamentos existentes por valor e data. Confira para não duplicar.</small>}
                {choice.action==='LINK' && <label>Lançamento<select aria-label="Lançamento para conciliar" value={choice.cash_transaction_id??''} onChange={event=>change(row.fingerprint,{cash_transaction_id:event.target.value||null})}><option value="">Escolha após conferir</option>{row.candidates.map(item=><option key={item.id} value={item.id}>{date(item.occurred_at)} · {item.is_sale?'Venda':'Despesa'} · {money(item.amount)} · {item.description}</option>)}</select>{!row.candidates.length && <small>Nenhum lançamento do mesmo valor/direção em até 3 dias. Guarde somente para conferência.</small>}</label>}
                {choice.action==='EXPENSE' && <div className="bank-expense"><p>Não use para transferência entre suas contas, aporte, pagamento de empréstimo ou custo/taxa já registrado.</p>
                  {row.suggestion && <><small>Sugestão local: {natures[row.suggestion.expense_nature]} · {row.suggestion.reason}</small><button type="button" onClick={()=>change(row.fingerprint,{expense_nature:row.suggestion!.expense_nature,expense_behavior:row.suggestion!.expense_behavior,category:row.suggestion!.category,classification_reviewed:false})}>Aplicar sugestão</button></>}
                  <label>Categoria<input maxLength={100} value={choice.category} onChange={event=>change(row.fingerprint,{category:event.target.value,classification_reviewed:false})}/></label>
                  <label>Finalidade<select value={choice.expense_context} onChange={event=>change(row.fingerprint,{expense_context:event.target.value,classification_reviewed:false})}>{Object.entries(contexts).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
                  <label>Classificação<select value={choice.expense_nature} onChange={event=>change(row.fingerprint,{expense_nature:event.target.value,classification_reviewed:false})}>{Object.entries(natures).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
                  <label>Comportamento<select value={choice.expense_behavior} onChange={event=>change(row.fingerprint,{expense_behavior:event.target.value,classification_reviewed:false})}>{Object.entries(behaviors).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
                  <label>Pagamento<select value={choice.payment_method} onChange={event=>change(row.fingerprint,{payment_method:event.target.value})}><option value="PIX">PIX / transferência</option><option value="DEBIT_CARD">Débito</option><option value="CREDIT_CARD">Crédito</option><option value="CARD">Cartão</option><option value="CASH">Dinheiro</option></select></label>
                  <label className="bank-check"><input type="checkbox" checked={choice.classification_reviewed} onChange={event=>change(row.fingerprint,{classification_reviewed:event.target.checked})}/> Revisei a classificação deste gasto</label>
                </div>}</>}
              {row.duplicate && <small>Ignorado para evitar duplicação. Consulte o histórico abaixo.</small>}
            </td></tr>;
        })}</tbody></table></div>
        <p>{selectedRows.length} selecionadas · {selectedRows.filter(row=>choices[row.fingerprint].action==='EXPENSE').length} novas despesas · {selectedRows.filter(row=>choices[row.fingerprint].action==='LINK').length} vínculos (sem criar novos valores).</p>
        <label className="bank-check"><input type="checkbox" checked={reviewed} onChange={event=>setReviewed(event.target.checked)}/> Conferi a seleção e os vínculos. Novas despesas não são transferências nem valores já contabilizados.</label>
        <button type="button" className="primary" disabled={!reviewed||!selectedRows.length||invalid||busy} onClick={()=>void save()}>Salvar movimentações selecionadas</button>
      </>}
    </fieldset>
    {error && <p className="alert error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <button type="button" onClick={()=>setHistoryOpen(!historyOpen)}>{historyOpen?'Ocultar':'Ver'} histórico de extratos importados</button>
    {historyOpen && <><h3>Conferência bancária — separada do resultado operacional</h3><button disabled={loading} onClick={()=>void load()}>Atualizar histórico bancário</button>
      <form className="bank-history-filters" onSubmit={applyFilters}>
        <label>Data inicial<input type="date" value={filterDraft.start_date} max={filterDraft.end_date||undefined} onChange={event=>setFilterDraft({...filterDraft,start_date:event.target.value})}/></label>
        <label>Data final<input type="date" value={filterDraft.end_date} min={filterDraft.start_date||undefined} onChange={event=>setFilterDraft({...filterDraft,end_date:event.target.value})}/></label>
        <label>Direção<select value={filterDraft.direction} onChange={event=>setFilterDraft({...filterDraft,direction:event.target.value})}><option value="">Todas</option><option value="INCOME">Entradas</option><option value="EXPENSE">Saídas</option></select></label>
        <label>Tratamento<select value={filterDraft.treatment} onChange={event=>setFilterDraft({...filterDraft,treatment:event.target.value})}><option value="">Todos</option><option value="BANK_ONLY">Somente conferência</option><option value="INCOME">Receitas</option><option value="EXPENSE">Despesas</option><option value="LINK">Vinculados</option><option value="CANCELLED">Lançamentos cancelados</option></select></label>
        <label className="bank-search-filter">Buscar descrição ou observação<input type="search" maxLength={150} placeholder="Nome, descrição ou observação…" value={filterDraft.search} onChange={event=>setFilterDraft({...filterDraft,search:event.target.value})}/></label>
        <div className="quotation-actions"><button type="submit" className="primary" disabled={busy}>Aplicar filtros</button><button type="button" disabled={busy} onClick={clearFilters}>Limpar filtros</button></div>
      </form>
      {loading && <p role="status">Carregando extratos…</p>}{historyError && <p className="alert error">{historyError}</p>}
      <div className="bank-table"><table><thead><tr><th>Data</th><th>Direção</th><th>Descrição</th><th>Valor</th><th>Tratamento</th><th>Ações</th></tr></thead><tbody>{history.map(row=><tr key={row.id}><td>{date(row.occurred_at)}</td><td>{row.direction==='INCOME'?'Entrada':'Saída'}</td><td className="bank-description">{row.description}{row.note && <small>Observação: {row.note}</small>}</td><td>{money(row.amount)}</td><td className="bank-treatment"><select aria-label={`Tratamento de ${row.description}`} disabled={busy||loading} value={row.disposition} onChange={event=>setEditing({id:row.id,action:event.target.value as BankChoice['action']})}>
        <option value="BANK_ONLY">Somente conferência bancária</option>{row.direction==='INCOME'?<option value="INCOME">Adicionar como receita</option>:<option value="EXPENSE">Adicionar como despesa</option>}<option value="LINK">Vincular a lançamento existente</option></select><small>{row.cash_cancelled?'Lançamento cancelado · sem impacto financeiro':actions[row.disposition]}</small>{row.disposition==='LINK'&&!row.cash_transaction_id && <small> · Lançamento removido/cancelado</small>}</td><td><button type="button" className="bank-edit-button" disabled={busy||loading} onClick={()=>setEditing({id:row.id})}>Editar</button></td></tr>)}</tbody></table></div>
      {!loading&&!historyError&&!history.length && <p>{Object.values(filters).some(Boolean)?'Nenhuma movimentação encontrada com estes filtros.':'Nenhum extrato importado.'}</p>}
      <div className="quotation-actions"><button disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-20))}>Anterior</button><span>{total?`${offset+1}–${Math.min(offset+20,total)} de ${total}`:'0 registros'}</span><button disabled={offset+20>=total||loading} onClick={()=>setOffset(offset+20)}>Próxima</button></div></>}
    {editing && <BankMovementEditor id={editing.id} action={editing.action} close={()=>setEditing(null)} onSaved={async result=>{setEditing(null);setPreview(null);setChoices({});setSelected({});setReviewed(false);setMessage(result);await load();await onSaved();}}/>}
  </section>;
}
