import type { Product } from './types';
export type DiscountKind='FIXED'|'PERCENTAGE';
export type CartLine={product:Product;quantity:number;discount:string;discountType:DiscountKind};
const MAX_MONEY=99999999999999n;

export function cents(raw:string):bigint {
  let value=raw.trim().replace(/^R\$\s*/, '').replace(/\s/g,'');
  if(!value)return 0n;
  if(value.includes(',')) {
    if(!/^(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{0,2})?$/.test(value))throw new Error('Informe um valor válido com até duas casas decimais.');
    value=value.replace(/\./g,'').replace(',','.');
  }
  if(!/^\d+(?:\.\d{0,2})?$/.test(value))throw new Error('Informe um valor não negativo com até duas casas decimais.');
  const [whole,fraction='']=value.split('.');
  const amount=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
  if(amount>MAX_MONEY)throw new Error('Valor acima do limite permitido.');
  return amount;
}
export function decimal(value:bigint):string {return `${value/100n}.${(value%100n).toString().padStart(2,'0')}`;}
export function discountCents(base:bigint,kind:DiscountKind,raw:string):bigint {
  const value=cents(raw);
  if(kind==='PERCENTAGE'&&value>10000n)throw new Error('O desconto percentual não pode ultrapassar 100%.');
  const amount=kind==='PERCENTAGE'?(base*value+5000n)/10000n:value;
  if(amount>base)throw new Error('O desconto não pode ser maior que o valor dos produtos.');
  return amount;
}
export function calculateSale(lines:CartLine[],orderRaw:string,orderKind:DiscountKind) {
  let gross=0n,itemDiscount=0n;
  const items=lines.map(line=>{
    if(!Number.isSafeInteger(line.quantity)||line.quantity<1||line.quantity>line.product.current_stock)throw new Error(`Confira a quantidade e o estoque de ${line.product.name}.`);
    const amount=cents(line.product.sale_price)*BigInt(line.quantity);
    const reduction=discountCents(amount,line.discountType,line.discount);
    gross+=amount;itemDiscount+=reduction;
    const value=cents(line.discount);
    return {product_id:line.product.id,quantity:line.quantity,discount_type:value?line.discountType:null,discount_value:decimal(value)};
  });
  if(gross>MAX_MONEY)throw new Error('Total da venda acima do limite permitido.');
  const subtotal=gross-itemDiscount;
  const saleDiscount=discountCents(subtotal,orderKind,orderRaw);
  const net=subtotal-saleDiscount;
  return {gross,itemDiscount,subtotal,saleDiscount,discountTotal:itemDiscount+saleDiscount,net,items,
    sale_discount_type:cents(orderRaw)?orderKind:null,sale_discount_value:decimal(cents(orderRaw)),expected_net_total:decimal(net)};
}
