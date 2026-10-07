import { FormEvent, useEffect, useState } from 'react';
import { api, QuotationProduct } from './api';
import type { Product } from './types';

const money=(value:string|number)=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function ProductModal({product,close,refresh,notify,fail}:{product:Product|null;close:()=>void;refresh:()=>Promise<void>;notify:(message:string)=>void;fail:(message:string)=>void}) {
  const [target,setTarget]=useState(product);
  const [form,setForm]=useState({name:product?.name??'',sku:product?.sku??'',cost_price:product?.cost_price??'',
    additional_cost:product?.additional_cost??'0',target_margin_percentage:product?.target_margin_percentage??'0',
    sale_price:product?.sale_price??'',current_stock:String(product?.current_stock??0)});
  const [query,setQuery]=useState(product?.sku??'');
  const [matches,setMatches]=useState<QuotationProduct[]>([]);
  const [chosen,setChosen]=useState<QuotationProduct|null>(null);
  const [searching,setSearching]=useState(false);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{
    let active=true;const controller=new AbortController();setSearching(true);setMatches([]);setError('');
    const timer=window.setTimeout(()=>{
      void api.quotationProducts(query,controller.signal).then(result=>{if(active)setMatches(result);})
        .catch(reason=>{if(active)setError((reason as Error).message);})
        .finally(()=>{if(active)setSearching(false);});
    },300);
    return()=>{active=false;controller.abort();window.clearTimeout(timer);};
  },[query]);
  const choose=(row:QuotationProduct)=>{
    if(product && row.product && row.product.id!==product.id){
      setError('Essa ficha está vinculada a outro produto. Abra o cadastro dele para atualizar.');return;
    }
    const existing=product??row.product;
    setTarget(existing);setChosen(row);setError('');
    setForm(current=>({...current,name:existing?.name??row.name,sku:row.sku,cost_price:row.cost_price,
      additional_cost:row.additional_cost,target_margin_percentage:row.target_margin_percentage,
      sale_price:existing?.sale_price??row.sale_price,
      current_stock:existing && existing.id!==target?.id?String(existing.current_stock):!existing && target?'0':current.current_stock}));
  };
  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(saving)return;setSaving(true);setError('');
    const data={name:form.name,sku:form.sku,cost_price:Number(form.cost_price),additional_cost:Number(form.additional_cost),
      target_margin_percentage:Number(form.target_margin_percentage),sale_price:Number(form.sale_price)};
    try{
      // Do not rewrite stock from a stale form unless the user explicitly changed it.
      if(target)await api.updateProduct(target.id,{...data,...(Number(form.current_stock)!==target.current_stock?{current_stock:Number(form.current_stock)}:{})});
      else await api.createProduct({...data,current_stock:Number(form.current_stock)});
      await refresh();notify(target?'Produto atualizado.':'Produto cadastrado.');close();
    }catch(reason){const message=(reason as Error).message;setError(message);fail(message);}
    finally{setSaving(false);}
  };
  return <div className="modal-backdrop"><form className="modal product-modal" onSubmit={submit}>
    <div className="modal-header"><h2>{target?'Editar produto':'Novo produto'}</h2><button type="button" disabled={saving} onClick={close}>×</button></div>
    <fieldset disabled={saving}>
      <section className="product-quotation-picker">
        <label>Buscar na cotação por SKU ou nome<input aria-label="Buscar na cotação por SKU ou nome" value={query} placeholder="Digite o SKU ou nome do produto" maxLength={160} onChange={event=>setQuery(event.target.value)}/></label>
        {searching?<p role="status">Buscando fichas salvas…</p>:<>
          <div className="quotation-matches">{matches.map(row=><button type="button" key={`${row.document_id}:${row.sheet}`} onClick={()=>choose(row)}>
            <span><b>{row.name}</b><small>{row.sku} · {row.product?'Já cadastrado':'Novo produto'}</small></span>
            <span>{money(Number(row.cost_price)+Number(row.additional_cost))}<small>Custo total · Usar cotação</small></span>
          </button>)}</div>
          {!matches.length && <p>Nenhuma ficha encontrada. Importe e salve a planilha no painel Cotação de produtos abaixo da lista, ou cadastre manualmente.</p>}
        </>}
        {chosen && <p className="quotation-chosen">Ficha selecionada: <b>{chosen.name}</b>. O SKU mantém o vínculo com a cotação.
          {target && <> O preço de venda e o estoque existentes foram preservados.</>}
          {target && <button type="button" onClick={()=>setForm({...form,sale_price:chosen.sale_price})}>Usar preço sugerido: {money(chosen.sale_price)}</button>}
        </p>}
      </section>
      {error && <p className="alert error" role="alert">{error}</p>}
      <label>Nome<input required value={form.name} maxLength={160} onChange={event=>{setForm({...form,name:event.target.value});if(!chosen)setQuery(event.target.value);}}/></label>
      <label>SKU<input required value={form.sku} maxLength={64} readOnly={!!chosen} onChange={event=>{setForm({...form,sku:event.target.value});setQuery(event.target.value);}}/></label>
      <div className="form-grid">
        <label>Custo de matéria-prima<input required min="0" step="0.01" type="number" value={form.cost_price} onChange={event=>setForm({...form,cost_price:event.target.value})}/></label>
        <label>Custos adicionais<input required min="0" step="0.01" type="number" value={form.additional_cost} onChange={event=>setForm({...form,additional_cost:event.target.value})}/></label>
      </div>
      <p>Custo total: <b>{money(Number(form.cost_price)+Number(form.additional_cost))}</b></p>
      <label>Preço de venda<input required min="0" step="0.01" type="number" value={form.sale_price} onChange={event=>setForm({...form,sale_price:event.target.value})}/></label>
      <label>Estoque atual<input required min="0" step="1" type="number" value={form.current_stock} onChange={event=>setForm({...form,current_stock:event.target.value})}/></label>
    </fieldset>
    <div className="modal-footer"><button type="button" disabled={saving} onClick={close}>Cancelar</button><button className="primary" disabled={saving || searching} type="submit">{saving?'Salvando…':'Salvar produto'}</button></div>
  </form></div>;
}
