import { useRef, useState } from 'react';
import type { Product } from './types';
import { filterSaleProducts, saleStockRemaining, searchSelection } from './saleProductSearch';

const money=(value:string)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function SaleProductPicker({products,quantities,add}:{products:Product[];quantities:Record<string,number>;add:(product:Product)=>void}) {
  const [selectedId,setSelectedId]=useState('');
  const [query,setQuery]=useState('');
  const dropdown=useRef<HTMLSelectElement>(null);
  const matches=filterSaleProducts(products,query);
  const selected=matches.find(product=>product.id===selectedId);
  const remaining=saleStockRemaining(selected,selected?quantities[selected.id]??0:0);
  return <section className="product-picker">
    <h2>Produtos cadastrados</h2>
    <label className="sale-product-select">Buscar por nome ou SKU
      <input type="search" value={query} placeholder="Digite o nome ou SKU do produto" onChange={event=>{
        const value=event.target.value;setQuery(value);setSelectedId(searchSelection(products,value));
      }} onKeyDown={event=>{
        if(event.key==='Enter'){
          event.preventDefault();
          const id=searchSelection(products,query);
          if(id)setSelectedId(id);else dropdown.current?.focus();
        }
      }}/>
    </label>
    <label className="sale-product-select">Selecione o produto
      <select ref={dropdown} value={selected?selectedId:''} disabled={!products.length || !matches.length} onChange={event=>setSelectedId(event.target.value)}>
        <option value="">{!products.length?'Nenhum produto cadastrado':!matches.length?'Nenhum produto encontrado':'Selecione um produto…'}</option>
        {matches.map(product=><option key={product.id} value={product.id}>
          {product.name} · {product.sku} · {money(product.sale_price)} · {product.current_stock>0?`${product.current_stock} em estoque`:'Sem estoque'}
        </option>)}
      </select>
    </label>
    {products.length>0 && <p className="subtitle" role="status">{matches.length} produto(s) encontrado(s). {query && !matches.length?'Revise o nome ou SKU, ou limpe a busca para ver todos.':''}</p>}
    {selected && <div className="sale-product-details">
      <p>Preço de venda: <b>{money(selected.sale_price)}</b></p>
      <p>Estoque: {selected.current_stock} · Na venda: {quantities[selected.id]??0}</p>
      {!remaining && <p role="status">{selected.current_stock<=0?'Este produto está sem estoque. Atualize o cadastro para vender.':'Todo o estoque disponível já foi adicionado à venda.'}</p>}
    </div>}
    <button className="primary" type="button" disabled={!selected || !remaining} onClick={()=>{if(selected && remaining)add(selected);}}>Adicionar à venda</button>
    {!products.length?<p className="subtitle">Cadastre ou importe os produtos na aba Produtos.</p>:
      <p className="subtitle">Você pode selecionar qualquer produto, inclusive sem estoque. Para adicionar à venda, informe o estoque disponível em Produtos → Editar → Estoque atual.</p>}
  </section>;
}
