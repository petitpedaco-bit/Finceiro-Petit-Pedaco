import { useEffect, useState } from 'react';
import { request } from './api';
import ReceiptReader, { Supplier } from './ReceiptReader';
type Product={id:string;name:string;unit:string;unit_price:string;price_date:string};
type Receipt={id:string;supplier:string;number:string;date:string;amount:string;items:{name:string;unit:string;quantity:string;total:string;unit_price:string;previous_price:string|null}[]};
export default function SuppliersPage({refresh}:{refresh:()=>Promise<void>}){
  const [suppliers,setSuppliers]=useState<Supplier[]>([]);const [selected,setSelected]=useState('');const [products,setProducts]=useState<Product[]>([]);
  const [receipts,setReceipts]=useState<Receipt[]>([]);const [offset,setOffset]=useState(0);const [total,setTotal]=useState(0);const [version,setVersion]=useState(0);
  const [error,setError]=useState('');const [loading,setLoading]=useState(false);
  useEffect(()=>{let active=true;setLoading(true);setError('');Promise.all([request<Supplier[]>('/suppliers'),request<{total:number;items:Receipt[]}>(`/suppliers/receipts/history?offset=${offset}`)])
    .then(([rows,history])=>{if(active){setSuppliers(rows);setReceipts(history.items);setTotal(history.total);}}).catch(err=>{if(active)setError(err.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[offset,version]);
  useEffect(()=>{let active=true;setProducts([]);if(selected)request<Product[]>(`/suppliers/${selected}/products`).then(rows=>{if(active)setProducts(rows);}).catch(err=>{if(active)setError(err.message);});return()=>{active=false;};},[selected,version]);
  return <div className="suppliers-page"><ReceiptReader onSaved={async()=>{setVersion(value=>value+1);await refresh();}}/>
    <section className="card abc"><div className="card-title"><h2>Produtos por fornecedor</h2><button type="button" onClick={()=>setVersion(value=>value+1)}>Atualizar fornecedores</button></div>
      <label>Fornecedor<select value={selected} onChange={event=>setSelected(event.target.value)}><option value="">Selecione um fornecedor</option>{suppliers.map(row=><option key={row.id} value={row.id}>{row.name} — {row.cnpj}</option>)}</select></label>
      <p>Catálogo de compras separado do catálogo de vendas. Preços são atualizados após salvar um cupom revisado, por fornecedor + descrição + unidade.</p>
      <table><thead><tr><th>Produto comprado</th><th>Unidade</th><th>Último preço de compra</th><th>Data da compra</th></tr></thead><tbody>{products.map(row=><tr key={row.id}><td>{row.name}</td><td>{row.unit}</td><td>{Number(row.unit_price).toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:4})}</td><td>{new Date(row.price_date).toLocaleDateString('pt-BR')}</td></tr>)}</tbody></table>
      {selected&&!products.length&&<p>Nenhum produto carregado para este fornecedor.</p>}</section>
    <section className="card abc"><h2>Cupons registrados / histórico de preços</h2>{loading&&<p role="status">Carregando compras…</p>}{error&&<p className="alert error">{error}</p>}
      {receipts.map(row=><details key={row.id} className="receipt-history"><summary>{row.date.split('-').reverse().join('/')} — {row.supplier} — Cupom {row.number} — {Number(row.amount).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}</summary>
        <table><thead><tr><th>Produto</th><th>Quantidade</th><th>Unidade</th><th>Total</th><th>Preço unitário</th><th>Preço anterior</th></tr></thead><tbody>{row.items.map((item,index)=><tr key={index}><td>{item.name}</td><td>{item.quantity}</td><td>{item.unit}</td><td>{item.total}</td><td>{item.unit_price}</td><td>{item.previous_price??'Novo produto'}</td></tr>)}</tbody></table></details>)}
      <div className="quotation-actions"><button disabled={!offset||loading} onClick={()=>setOffset(value=>Math.max(0,value-20))}>Anterior</button><span>{total?`${offset+1}–${Math.min(offset+20,total)} de ${total}`:'0 cupons'}</span><button disabled={offset+20>=total||loading} onClick={()=>setOffset(value=>value+20)}>Próxima</button></div>
    </section></div>;
}
