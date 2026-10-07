import type { Product } from './types';

export const normalizeSearch=(value:string)=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR').trim();

export function filterSaleProducts(products:Product[],query:string):Product[] {
  const terms=normalizeSearch(query).split(/\s+/).filter(Boolean);
  return products.filter(product=>{
    const text=normalizeSearch(`${product.name} ${product.sku}`);
    return terms.every(term=>text.includes(term));
  }).sort((a,b)=>a.name.localeCompare(b.name,'pt-BR'));
}

export function searchSelection(products:Product[],query:string):string {
  const term=normalizeSearch(query);
  if(!term)return '';
  const exact=products.filter(product=>normalizeSearch(product.sku)===term || normalizeSearch(product.name)===term);
  if(exact.length===1)return exact[0].id;
  const matches=filterSaleProducts(products,query);
  return matches.length===1?matches[0].id:'';
}

export const saleStockRemaining=(product:Product|undefined,quantity=0)=>product?Math.max(0,product.current_stock-quantity):0;
