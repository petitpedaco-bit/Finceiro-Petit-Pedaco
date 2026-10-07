import { useState } from 'react';
import { api, QuotationPreview } from './api';

export default function Quotations({ refresh }: { refresh: () => Promise<void> }) {
  const [url, setUrl] = useState('https://docs.google.com/spreadsheets/d/1kqfc0fzW6U-VV89_T62a-XUp1ys0rAvl/edit');
  const [preview, setPreview] = useState<QuotationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [updatePrices, setUpdatePrices] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setMessage('');
    try { await operation(); } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  };
  const show = (data: QuotationPreview) => { setPreview(data); setSelected(new Set()); };
  return <section className="card" style={{marginBottom: 20}}>
    <h2>Cotações da planilha</h2>
    <p>Leia as fichas, revise e escolha os produtos. Para vincular um produto existente, informe seu SKU. Novos produtos começam com estoque zero.</p>
    <label>Link público Google Sheets<input value={url} onChange={e => setUrl(e.target.value)} /></label>
    <button disabled={busy} onClick={() => void run(async () => show(await api.quotationGoogle(url)))}>Ler planilha do Google</button>
    <label>Ou selecione o Excel<input disabled={busy} type="file" accept=".xlsx" onChange={e => { const file = e.target.files?.[0]; if(file) void run(async () => show(await api.quotationExcel(file))); e.target.value = ''; }} /></label>
    {busy && <p role="status">Processando…</p>}{message && <p role="status">{message}</p>}
    {preview && <><p>{preview.notice}</p><p>{preview.rows.length} fichas reconhecidas.</p>
      {preview.warnings.length > 0 && <details><summary>Fichas que precisam de revisão ({preview.warnings.length})</summary>{preview.warnings.map((w,i) => <p key={i}>{w}</p>)}</details>}
      <div className="table-wrap"><table><thead><tr><th>Selecionar</th><th>Ficha</th><th>SKU vinculado</th><th>Matéria-prima</th><th>Custos adicionais</th><th>Preço sugerido</th></tr></thead><tbody>{preview.rows.map((row,i) => <tr key={i}>
        <td><input type="checkbox" checked={selected.has(i)} onChange={() => setSelected(current => { const next = new Set(current); next.has(i) ? next.delete(i) : next.add(i); return next; })} /></td>
        <td>{row.name}</td><td><input aria-label={`SKU de ${row.name}`} value={row.sku} maxLength={64} onChange={e => setPreview({...preview, rows: preview.rows.map((r,j) => j === i ? {...r, sku:e.target.value} : r)})} /></td>
        <td>R$ {row.cost_price}</td><td>R$ {row.additional_cost}</td><td>R$ {row.sale_price}</td></tr>)}</tbody></table></div>
      <label><input style={{width:'auto', display:'inline'}} type="checkbox" checked={updatePrices} onChange={e => setUpdatePrices(e.target.checked)} /> Atualizar também preço de venda de produtos existentes</label>
      <button className="primary" disabled={busy || selected.size === 0} onClick={() => void run(async () => {
        const result = await api.quotationApply(preview.rows.filter((_,i) => selected.has(i)), updatePrices);
        await refresh(); setMessage(`${result.created} produtos criados e ${result.updated} atualizados.`); setSelected(new Set());
      })}>Aplicar {selected.size} cotações selecionadas</button>
    </>}
  </section>;
}
