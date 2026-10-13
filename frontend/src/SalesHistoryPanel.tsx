import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { SaleHistoryEntry } from './types';

const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const payments:Record<string,string>={PIX:'PIX',CASH:'Dinheiro',CARD:'Cartão',CREDIT_CARD:'Crédito',DEBIT_CARD:'Débito'};

export default function SalesHistoryPanel({refresh}:{refresh:()=>Promise<void>}) {
  const [sales,setSales]=useState<SaleHistoryEntry[]>([]);
  const [offset,setOffset]=useState(0);
  const [state,setState]=useState('ALL');
  const [total,setTotal]=useState(0);
  const [loading,setLoading]=useState(true);
  const [cancelling,setCancelling]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [lastRead,setLastRead]=useState('');
  const activeRequest=useRef<AbortController|null>(null);
  const mutation=useRef(false);
  const load=async()=>{
    activeRequest.current?.abort();const controller=new AbortController();activeRequest.current=controller;
    setLoading(true);setError('');
    try{
      const result=await api.salesHistory(offset,state,controller.signal);
      if(controller.signal.aborted)return;
      setSales(result.items);setTotal(result.total);setLastRead(new Date().toLocaleTimeString('pt-BR'));
      if(offset>0&&offset>=result.total)setOffset(Math.max(0,Math.floor((result.total-1)/20)*20));
    }catch(reason){if(!controller.signal.aborted)setError((reason as Error).message);}
    finally{if(!controller.signal.aborted)setLoading(false);}
  };
  useEffect(()=>{
    void load();
    const visible=()=>{if(document.visibilityState==='visible'&&!mutation.current)void load();};
    const focus=()=>{if(!mutation.current)void load();};
    window.addEventListener('focus',focus);document.addEventListener('visibilitychange',visible);
    return()=>{activeRequest.current?.abort();window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',visible);};
  },[offset,state]);
  const cancel=async(sale:SaleHistoryEntry)=>{
    if(mutation.current||sale.is_cancelled)return;
    if(!window.confirm(`Excluir/cancelar a venda ${sale.id.slice(0,8)} de ${money(sale.net_total)}?\n\nO estoque será devolvido e a venda sairá do caixa, lucro e relatórios. Ela ficará no histórico como cancelada. Isso não realiza estorno no banco.`))return;
    mutation.current=true;setCancelling(true);setError('');setMessage('');
    activeRequest.current?.abort();
    try{
      await api.cancelSale(sale.id);
      setSales(current=>current.map(item=>item.id===sale.id?{...item,is_cancelled:true}:item));
      setMessage('Venda excluída dos cálculos. Estoque, caixa e relatórios atualizados; histórico preservado.');
      await load();await refresh();
    }catch(reason){setError((reason as Error).message);}
    finally{mutation.current=false;setCancelling(false);setLoading(false);}
  };
  return <section className="card abc sales-history-panel"><div className="card-title"><h2>Vendas do sistema</h2><button type="button" disabled={loading||cancelling} onClick={()=>void load()}>Atualizar vendas</button></div>
    <p className="subtitle">Vendas confirmadas em Nova venda, inclusive fora do período da DRE acima. Receitas de extratos não são vendas de produtos.</p>
    <label>Situação<select disabled={cancelling} value={state} onChange={event=>{setState(event.target.value);setOffset(0);setSales([]);setTotal(0);}}><option value="ALL">Todas as vendas</option><option value="ACTIVE">Ativas</option><option value="CANCELLED">Canceladas</option></select></label>
    {lastRead && <p className="subtitle">Última atualização: {lastRead} · {total} venda(s) encontrada(s).</p>}
    {loading && <p role="status">Carregando vendas…</p>}{error && <p className="alert error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <table><thead><tr><th>Data / identificação</th><th>Produtos</th><th>Pagamento</th><th>Valor da venda</th><th>Líquido recebido</th><th>Ação / situação</th></tr></thead><tbody>{sales.map(sale=><tr key={sale.id} className={sale.is_cancelled?'expense-cancelled':''}>
      <td>{new Date(sale.created_at).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'})}<br/><code title={sale.id}>{sale.id.slice(0,8)}</code></td>
      <td className="sale-history-products">{sale.products.length?sale.products.map((item,index)=><div key={`${item.sku}:${index}`}>{item.quantity} × {item.name}<small>{item.sku}</small></div>):'Venda registrada sem detalhes de itens'}</td>
      <td>{payments[sale.payment_method]??sale.payment_method}</td><td>{money(sale.net_total)}</td><td>{money(sale.received_total)}</td>
      <td>{sale.is_cancelled?'Cancelada':<button type="button" className="sale-cancel-button expense-cancel-button" disabled={loading||cancelling} onClick={()=>void cancel(sale)}>Excluir / cancelar</button>}</td>
    </tr>)}</tbody></table>
    {!sales.length&&!loading&&!error && <p>Nenhuma venda {state==='ALL'?'registrada':state==='ACTIVE'?'ativa':'cancelada'} encontrada.</p>}
    <div className="quotation-actions"><button disabled={!offset||loading||cancelling} onClick={()=>setOffset(Math.max(0,offset-20))}>Anterior</button><span>{total?`${offset+1}–${Math.min(offset+20,total)} de ${total}`:'0 vendas'}</span><button disabled={offset+20>=total||loading||cancelling} onClick={()=>setOffset(offset+20)}>Próxima</button></div>
  </section>;
}
