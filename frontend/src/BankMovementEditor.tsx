import { FormEvent, useEffect, useState } from 'react';
import { api, BankChoice, BankEditData, BankEditInput } from './api';
import { defaultBankChoice, invalidBankChoice } from './bankImportChoices';

const natures:Record<string,string>={UNCLASSIFIED:'Não classificado / revisar',DIRECT_COST:'Custo direto',INDIRECT_COST:'Custo indireto',ADMINISTRATIVE:'Administrativa',COMMERCIAL:'Comercial',FINANCIAL:'Financeira',TAX:'Tributos'};
const behaviors:Record<string,string>={UNSPECIFIED:'Não definido',FIXED:'Fixo',VARIABLE:'Variável',MIXED:'Misto'};
const contexts:Record<string,string>={GENERAL:'Geral / não informado',PRODUCTION:'Produção',ADMINISTRATION:'Administração',SALES:'Vendas'};
const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function BankMovementEditor({id,action,close,onSaved}:{id:string;action?:BankChoice['action'];close:()=>void;onSaved:(message:string)=>Promise<void>}) {
  const [data,setData]=useState<BankEditData|null>(null);
  const [form,setForm]=useState<BankEditInput|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;void api.bankEditGet(id).then(result=>{
    if(!active)return;setData(result);const {fingerprint,...defaults}=defaultBankChoice('');
    setForm({...defaults,expected_version:result.version,expected_state:result.expected_state,
      action:action??result.disposition,cash_transaction_id:result.disposition==='LINK'?result.cash?.id??null:null,
      category:result.cash?.category??(result.direction==='INCOME'?'Outras receitas':'Outros / revisar'),
      payment_method:result.cash?.payment_method??'PIX',expense_nature:result.cash?.expense_nature??'UNCLASSIFIED',
      expense_behavior:result.cash?.expense_behavior??'UNSPECIFIED',expense_context:result.cash?.expense_context??'GENERAL',
      classification_reviewed:false,note:result.note,reviewed:false});
  }).catch(reason=>{if(active)setError((reason as Error).message);});return()=>{active=false;};},[id,action]);
  const change=(fields:Partial<BankEditInput>)=>setForm(current=>current?{...current,...fields,reviewed:false}:current);
  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(!form||!data||busy||!form.reviewed)return;
    if(!window.confirm('Salvar este tratamento? Receitas e despesas serão refletidas no financeiro. A data, o valor e a descrição original do extrato serão preservados.'))return;
    setBusy(true);setError('');
    try{const result=await api.bankEditSave(id,form);await onSaved(result.message);close();}
    catch(reason){setError((reason as Error).message);}finally{setBusy(false);}
  };
  const externalLink=data?.disposition==='LINK'&&data.cash&&!data.cash.is_cancelled;
  return <div className="modal-backdrop"><section className="modal bank-editor" role="dialog" aria-modal="true" aria-labelledby="bank-editor-title">
    <div className="modal-header"><h2 id="bank-editor-title">Editar tratamento bancário</h2><button type="button" disabled={busy} aria-label="Fechar edição" onClick={close}>×</button></div>
    {error && <p className="alert error" role="alert">{error}</p>}
    {!form||!data?<p role="status">{error?'Feche e abra novamente para tentar de novo.':'Carregando movimentação…'}</p>:<form onSubmit={submit}><fieldset disabled={busy}>
      <p>{new Date(data.occurred_at).toLocaleDateString('pt-BR')} · {data.direction==='INCOME'?'Entrada':'Saída'} · <b>{money(data.amount)}</b></p><p className="bank-original">{data.description}</p>
      <small>Data, direção, valor e descrição são do extrato original e não são alterados. Use a observação para complementar.</small>
      <label>Tratamento<select value={form.action} onChange={event=>change({action:event.target.value as BankChoice['action'],cash_transaction_id:null})}>
        <option value="BANK_ONLY">Somente conferência (sem novo lançamento)</option>
        {data.direction==='INCOME'?<option value="INCOME" disabled={!!externalLink}>Adicionar como receita</option>:<option value="EXPENSE" disabled={!!externalLink}>Adicionar como despesa</option>}
        <option value="LINK">Vincular a lançamento existente</option></select></label>
      <p className="subtitle">Não trate transferências entre suas contas, aportes ou empréstimos como receitas/despesas. Recebimentos de vendas já registradas devem ser vinculados, não adicionados novamente.</p>
      {externalLink && <p>Já vinculado: trocar para conferência ou outro vínculo não cancela a venda/despesa existente.</p>}
      {data.disposition==='EXPENSE'||data.disposition==='INCOME'?<p>{data.cash?.is_cancelled?'O lançamento anterior foi cancelado. Escolher receita/despesa criará um novo lançamento após confirmação.':'Ao trocar de receita/despesa para conferência ou vínculo, o lançamento criado por esta importação será cancelado no financeiro e preservado no histórico.'}</p>:null}
      {form.action==='LINK' && <label>Lançamento<select required value={form.cash_transaction_id??''} onChange={event=>change({cash_transaction_id:event.target.value||null})}><option value="">Selecione após conferir</option>{data.candidates.map(item=><option key={item.id} value={item.id}>{new Date(item.occurred_at).toLocaleDateString('pt-BR')} · {item.is_sale?'Venda':'Lançamento'} · {money(item.amount)} · {item.description}</option>)}</select>{!data.candidates.length && <small>Nenhum candidato do mesmo valor/direção em até 3 dias.</small>}</label>}
      {(form.action==='INCOME'||form.action==='EXPENSE') && <><label>Categoria<input required maxLength={100} value={form.category} onChange={event=>change({category:event.target.value,classification_reviewed:false})}/></label>
        <label>Pagamento<select value={form.payment_method} onChange={event=>change({payment_method:event.target.value})}><option value="PIX">PIX / transferência</option><option value="CARD">Cartão</option><option value="DEBIT_CARD">Débito</option><option value="CREDIT_CARD">Crédito</option><option value="CASH">Dinheiro</option></select></label>
        {!!data.candidates.length && <p>Há lançamentos existentes do mesmo valor/data. Confira se não é duplicação antes de criar receita ou despesa.</p>}
      </>}
      {form.action==='EXPENSE' && <>{data.suggestion && <button type="button" onClick={()=>change({expense_nature:data.suggestion!.expense_nature,expense_behavior:data.suggestion!.expense_behavior,category:data.suggestion!.category,classification_reviewed:false})}>Aplicar sugestão local</button>}
        <label>Finalidade<select value={form.expense_context} onChange={event=>change({expense_context:event.target.value,classification_reviewed:false})}>{Object.entries(contexts).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Classificação<select value={form.expense_nature} onChange={event=>change({expense_nature:event.target.value,classification_reviewed:false})}>{Object.entries(natures).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Comportamento<select value={form.expense_behavior} onChange={event=>change({expense_behavior:event.target.value,classification_reviewed:false})}>{Object.entries(behaviors).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label className="bank-check"><input type="checkbox" checked={form.classification_reviewed} onChange={event=>change({classification_reviewed:event.target.checked})}/> Revisei a classificação desta despesa</label>
      </>}
      <label>Observação<input maxLength={500} value={form.note} onChange={event=>change({note:event.target.value})}/></label>
      <label className="bank-check"><input type="checkbox" checked={form.reviewed} onChange={event=>setForm({...form,reviewed:event.target.checked})}/> Revisei o tratamento e o impacto financeiro. Não estou duplicando um valor já lançado nem registrando transferência/aporte/empréstimo como resultado.</label>
      <div className="modal-footer"><button type="button" disabled={busy} onClick={close}>Cancelar edição</button><button className="primary" disabled={!form.reviewed||invalidBankChoice({...form,fingerprint:''},data.direction)||busy}>{busy?'Salvando…':'Salvar alterações'}</button></div>
    </fieldset></form>}
  </section></div>;
}
