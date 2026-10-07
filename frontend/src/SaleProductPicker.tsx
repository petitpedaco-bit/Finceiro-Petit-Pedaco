import { useState } from 'react';
import type { Product } from './types';

const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function SaleProductPicker({products,quantities,add}:{products:Product[];quantities:Record<string,number>;add:(product:Product)=>void}) {
  const [selectedId,setSelectedId]=useState('');
  const selected=products.find(product=>product.id===selectedId);
  const remaining=selected?Math.max(0,selected.current_stock-(quantities[selected.id]??0)):0;
  return <section className="product-picker">
    <h2>Produtos cadastrados</h2>
    <label className="sale-product-select">Selecione o produto
      <select value={selected?selectedId:''} disabled={!products.length} onChange={event=>setSelectedId(event.target.value)}>
        <option value="">{products.length?'Selecione um produto…':'Nenhum produto cadastrado'}</option>
        {[...products].sort((a,b)=>a.name.localeCompare(b.name,'pt-BR')).map(product=><option key={product.id} value={product.id} disabled={product.current_stock<=0}>
          {product.name} · {product.sku} · {money(product.sale_price)} · {product.current_stock>0?`${product.current_stock} em estoque`:'Sem estoque'}
        </option>)}
      </select>
    </label>
    {selected && <div className="sale-product-details">
      <p>Preço de venda: <b>{money(selected.sale_price)}</b></p>
      <p>Estoque: {selected.current_stock} · Na venda: {quantities[selected.id]??0}</p>
      {!remaining && <p role="status">{selected.current_stock<=0?'Este produto está sem estoque. Atualize o cadastro para vender.':'Todo o estoque disponível já foi adicionado à venda.'}</p>}
    </div>}
    <button className="primary" type="button" disabled={!selected || !remaining} onClick={()=>{if(selected && remaining)add(selected);}}>Adicionar à venda</button>
    {!products.length?<p className="subtitle">Cadastre ou importe os produtos na aba Produtos.</p>:
      <p className="subtitle">Produtos sem estoque aparecem na lista, mas não podem ser vendidos. Atualize o estoque na aba Produtos.</p>}
  </section>;
}
