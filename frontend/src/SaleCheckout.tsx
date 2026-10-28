import {useMemo,useRef,useState} from 'react';
import {api} from './api';
import type {PaymentMethod,Product} from './types';
import SaleProductPicker from './SaleProductPicker';
import {calculateSale,decimal} from './saleAmounts';
import type {CartLine,DiscountKind} from './saleAmounts';
type Props={products:Product[];refresh:()=>Promise<void>;notify:(message:string)=>void;fail:(message:string)=>void};
const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const currency=(value:bigint)=>money(decimal(value));

export default function SaleCheckout({products,refresh,notify,fail}:Props){
  const [lines,setLines]=useState<CartLine[]>([]);
  const [payment,setPayment]=useState<PaymentMethod>('PIX');
  const [saleDiscount,setSaleDiscount]=useState('');
  const [saleDiscountType,setSaleDiscountType]=useState<DiscountKind>('FIXED');
  const [submitting,setSubmitting]=useState(false);
  const checkoutLock=useRef(false);
  const calculation=useMemo(()=>{try{return{quote:calculateSale(lines,saleDiscount,saleDiscountType),error:''};}catch(error){return{quote:null,error:(error as Error).message};}},[lines,saleDiscount,saleDiscountType]);
  const add=(product:Product)=>setLines(current=>{
    if(product.current_stock<1)return current;
    const existing=current.find(row=>row.product.id===product.id);
    return existing?current.map(row=>row.product.id===product.id?{...row,quantity:Math.min(row.quantity+1,product.current_stock)}:row):[...current,{product,quantity:1,discount:'',discountType:'FIXED'}];
  });
  const change=(id:string,patch:Partial<CartLine>)=>setLines(current=>current.map(row=>row.product.id===id?{...row,...patch}:row));
  const checkout=async()=>{
    if(checkoutLock.current)return;
    if(!lines.length)return fail('Adicione pelo menos um produto à venda.');
    if(!calculation.quote)return fail(calculation.error);
    const quote=calculation.quote;
    checkoutLock.current=true;setSubmitting(true);
    try{
      const result=await api.checkout({payment_method:payment,items:quote.items,sale_discount_type:quote.sale_discount_type,sale_discount_value:quote.sale_discount_value,expected_net_total:quote.expected_net_total});
      setLines([]);setSaleDiscount('');setSaleDiscountType('FIXED');
      notify(`Venda ${result.id.slice(0,8)} confirmada. Descontos: ${money(result.discount_total)}. Total da venda: ${money(result.net_total)}. Recebido no caixa: ${money(result.received_total)}. Disponível em Relatórios → Vendas do sistema.`);
      await refresh();
    }catch(error){fail((error as Error).message);}finally{checkoutLock.current=false;setSubmitting(false);}
  };
  const quote=calculation.quote;
  return <fieldset disabled={submitting} className="pos sale-guard" aria-label="Nova venda">
    <SaleProductPicker products={products} quantities={Object.fromEntries(lines.map(row=>[row.product.id,row.quantity]))} add={add}/>
    <section className="cart"><h2>Venda atual</h2><div className="cart-lines">
      {!lines.length&&<p className="empty">Selecione um produto na lista e clique em Adicionar à venda.</p>}
      {lines.map(line=><article className="checkout-item" key={line.product.id}>
        <div className="checkout-item-title"><div><b>{line.product.name}</b><small>{money(line.product.sale_price)} cada</small></div><button type="button" className="remove" aria-label={`Remover ${line.product.name}`} onClick={()=>setLines(current=>current.filter(row=>row.product.id!==line.product.id))}>×</button></div>
        <label>Quantidade<input type="number" min="1" max={line.product.current_stock} step="1" value={line.quantity||''} onChange={event=>change(line.product.id,{quantity:Number(event.target.value)})}/></label>
        <div className="form-grid"><label>Tipo de desconto do produto<select value={line.discountType} onChange={event=>change(line.product.id,{discountType:event.target.value as DiscountKind})}><option value="FIXED">R$ — valor total do item</option><option value="PERCENTAGE">% — percentual do item</option></select></label>
        <label>Desconto do produto ({line.discountType==='FIXED'?'R$':'%'})<input type="text" inputMode="decimal" value={line.discount} placeholder="0,00" onChange={event=>change(line.product.id,{discount:event.target.value})}/></label></div>
        <small>O desconto é aplicado ao total deste produto, considerando toda a quantidade, não a cada unidade.</small>
      </article>)}
    </div><div className="checkout">
      <div className="form-grid"><label>Tipo de desconto da venda<select value={saleDiscountType} onChange={event=>setSaleDiscountType(event.target.value as DiscountKind)}><option value="FIXED">R$ — valor em dinheiro</option><option value="PERCENTAGE">% — percentual</option></select></label>
      <label>Desconto da venda ({saleDiscountType==='FIXED'?'R$':'%'})<input type="text" inputMode="decimal" value={saleDiscount} placeholder="0,00" onChange={event=>setSaleDiscount(event.target.value)}/></label></div>
      <p className="subtitle">O desconto da venda é aplicado após os descontos dos produtos.</p>
      {calculation.error&&<p role="alert" className="alert error">{calculation.error}</p>}
      <div className="sale-breakdown" aria-live="polite">
        <div className="line"><span>Valor bruto dos produtos</span><b>{quote?currency(quote.gross):'—'}</b></div>
        <div className="line"><span>Descontos dos produtos</span><b>{quote?currency(quote.itemDiscount):'—'}</b></div>
        <div className="line"><span>Desconto da venda</span><b>{quote?currency(quote.saleDiscount):'—'}</b></div>
        <div className="line"><span>Desconto total</span><b>{quote?currency(quote.discountTotal):'—'}</b></div>
      </div>
      <div className="payment">{(['PIX','CARD','CASH'] as PaymentMethod[]).map(method=><button type="button" key={method} className={payment===method?'selected':''} onClick={()=>setPayment(method)}>{({PIX:'PIX',CARD:'Cartão',CASH:'Dinheiro'} as Record<PaymentMethod,string>)[method]}</button>)}</div>
      <div className="total"><span>Total a cobrar do cliente</span><strong>{quote?currency(quote.net):'—'}</strong></div>
      <p className="subtitle">Taxas de cartão, quando aplicáveis, são separadas do desconto. O valor recebido no caixa será confirmado ao salvar.</p>
      <button type="button" className="primary checkout-button" disabled={submitting||!lines.length||!quote} onClick={()=>void checkout()}>{submitting?'Confirmando…':'Confirmar venda'}</button>
    </div></section>
  </fieldset>;
}
