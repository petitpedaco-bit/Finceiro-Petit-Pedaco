import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import Quotations from "./Quotations";
import ProductModal from "./ProductModal";
import SaleProductPicker from "./SaleProductPicker";
import type { ABCResponse, CashFlow, DRE, PaymentMethod, Product } from "./types";

type Screen = "dashboard" | "products" | "sales" | "expenses" | "reports";
const today = new Date().toISOString().slice(0, 10);
const firstDay = `${today.slice(0, 8)}01`;
const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const money = (value: string | number = 0) => currency.format(Number(value));
const paymentNames: Record<PaymentMethod, string> = { PIX: "PIX", CARD: "Cartão", CASH: "Dinheiro" };

function App() {
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [products, setProducts] = useState<Product[]>([]);
  const [period, setPeriod] = useState({ start: firstDay, end: today });
  const [dre, setDre] = useState<DRE | null>(null);
  const [cash, setCash] = useState<CashFlow | null>(null);
  const [abc, setAbc] = useState<ABCResponse | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const notify = (message: string) => { setNotice(message); setError(null); };
  const fail = (message: string) => { setError(message); setNotice(null); };
  const loadProducts = useCallback(async () => {
    try { setProducts(await api.products()); } catch (err) { fail((err as Error).message); }
  }, []);
  const loadReports = useCallback(async () => {
    try {
      const [nextDre, nextCash, nextAbc] = await Promise.all([
        api.dre(period.start, period.end), api.cashFlow(period.start, period.end), api.abc(period.start, period.end),
      ]);
      setDre(nextDre); setCash(nextCash); setAbc(nextAbc);
    } catch (err) { fail((err as Error).message); }
  }, [period]);
  useEffect(() => { void loadProducts(); void loadReports(); }, [loadProducts, loadReports]);

  const content = {
    dashboard: <Dashboard dre={dre} cash={cash} abc={abc} period={period} />,
    products: null,
    sales: <Sales products={products} refresh={async () => { await loadProducts(); await loadReports(); }} notify={notify} fail={fail} />,
    expenses: <Expenses refresh={loadReports} notify={notify} fail={fail} />,
    reports: <Reports period={period} setPeriod={setPeriod} dre={dre} cash={cash} abc={abc} />,
  }[screen];

  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span>PP</span><div>Petit Pedaço<small>Gestão inteligente</small></div></div>
      <nav>{([ ["dashboard", "⌂", "Visão geral"], ["products", "▣", "Produtos"], ["sales", "◉", "Nova venda"], ["expenses", "−", "Despesas"], ["reports", "▤", "Relatórios"] ] as [Screen, string, string][]).map(([id, icon, label]) =>
        <button key={id} className={screen === id ? "active" : ""} onClick={() => setScreen(id)}><i>{icon}</i>{label}</button>)}</nav>
      <div className="sidebar-footer">API Financeira<br/><small>v1.0</small></div>
    </aside>
    <main><header><div><p className="eyebrow">CONTROLE FINANCEIRO</p><h1>{({ dashboard: "Visão geral", products: "Produtos", sales: "Ponto de venda", expenses: "Lançar despesa", reports: "Relatórios" } as Record<Screen, string>)[screen]}</h1></div><div className="date">{new Intl.DateTimeFormat("pt-BR", { dateStyle: "full" }).format(new Date())}</div></header>
      {notice && <div className="alert success">✓ {notice}</div>}{error && <div className="alert error">! {error}</div>}
      {content}
      <div hidden={screen !== 'products'}>
        <Products products={products} refresh={loadProducts} notify={notify} fail={fail} />
        <div className="products-quotation-section"><Quotations refresh={loadProducts} /></div>
      </div>
    </main>
  </div>;
}

function percentage(value: string | number) { return Number(value).toFixed(1); }
function Dashboard({ dre, cash, abc, period }: { dre: DRE | null; cash: CashFlow | null; abc: ABCResponse | null; period: { start: string; end: string } }) {
  const top = abc?.products.slice(0, 5) ?? [];
  return <><p className="subtitle">Resultados entre {new Date(`${period.start}T12:00`).toLocaleDateString("pt-BR")} e {new Date(`${period.end}T12:00`).toLocaleDateString("pt-BR")}.</p>
    <section className="stats"><Stat title="Receita líquida" value={money(dre?.net_revenue)} tone="green"/><Stat title="Lucro líquido" value={money(dre?.net_profit)} tone="blue"/><Stat title="Saldo em caixa" value={money(cash?.closing_balance)} tone="gold"/><Stat title="Despesas" value={money(cash?.expenses)} tone="rose"/></section>
    <section className="grid two"><article className="card"><div className="card-title"><h2>Resumo de resultado</h2><span>DRE</span></div><div className="result-lines"><Line label="Receita bruta" value={dre?.gross_revenue}/><Line label="Descontos" value={dre?.deductions_and_discounts} negative/><Line label="CMV" value={dre?.cogs} negative/><Line label="Despesas operacionais" value={dre?.operating_expenses} negative/><Line label="Lucro líquido" value={dre?.net_profit} strong/></div></article>
      <article className="card"><div className="card-title"><h2>Produtos mais vendidos</h2><span>ABC</span></div>{top.length ? <div className="ranking">{top.map((product, index) => <div key={product.product_id}><b>{String(index + 1).padStart(2, "0")}</b><span>{product.product_name}<small>{percentage(product.revenue_percentage)}% do faturamento</small></span><strong>{money(product.revenue)}</strong></div>)}</div> : <Empty text="As vendas do período aparecerão aqui."/>}</article></section>
  </>;
}
function Stat({ title, value, tone }: { title: string; value: string; tone: string }) { return <article className={`stat ${tone}`}><p>{title}</p><strong>{value}</strong></article>; }
function Line({ label, value, negative, strong }: { label: string; value?: string; negative?: boolean; strong?: boolean }) { return <div className={strong ? "line strong" : "line"}><span>{label}</span><b className={negative ? "negative" : ""}>{negative ? "− " : ""}{money(value)}</b></div>; }
function Empty({ text }: { text: string }) { return <p className="empty">{text}</p>; }

function Products({ products, refresh, notify, fail }: { products: Product[]; refresh: () => Promise<void>; notify: (m: string) => void; fail: (m: string) => void }) {
  const [editing, setEditing] = useState<Product | null | undefined>(undefined);
  const remove = async (product: Product) => { if (!confirm(`Excluir ${product.name}?`)) return; try { await api.deleteProduct(product.id); await refresh(); notify("Produto excluído."); } catch (err) { fail((err as Error).message); } };
  return <><div className="toolbar"><p className="subtitle">{products.length} produto(s) cadastrado(s).</p><button className="primary" onClick={() => setEditing(null)}>+ Novo produto</button></div>
    <div className="card table-wrap"><table><thead><tr><th>Produto</th><th>SKU</th><th>Preço de custo</th><th>Preço de venda</th><th>Estoque</th><th></th></tr></thead><tbody>{products.map(product => <tr key={product.id}><td><b>{product.name}</b></td><td><code>{product.sku}</code></td><td>{money(product.cost_price)}</td><td>{money(product.sale_price)}</td><td><span className={product.current_stock === 0 ? "stock zero" : "stock"}>{product.current_stock} un.</span></td><td className="actions"><button onClick={() => setEditing(product)}>Editar</button><button className="danger-text" onClick={() => void remove(product)}>Excluir</button></td></tr>)}</tbody></table>{!products.length && <Empty text="Cadastre o primeiro produto para começar a vender."/>}</div>
    {editing !== undefined && <ProductModal product={editing} close={() => setEditing(undefined)} refresh={refresh} notify={notify} fail={fail}/>}</>;
}

function Sales({ products, refresh, notify, fail }: { products: Product[]; refresh: () => Promise<void>; notify: (m: string) => void; fail: (m: string) => void }) {
  const [lines, setLines] = useState<{ product: Product; quantity: number; discount: number }[]>([]); const [payment, setPayment] = useState<PaymentMethod>("PIX"); const [saleDiscount, setSaleDiscount] = useState(0);
  const subtotal = lines.reduce((sum, line) => sum + Number(line.product.sale_price) * line.quantity - line.discount, 0); const total = Math.max(0, subtotal - saleDiscount);
  const add = (product: Product) => setLines(current => { const existing = current.find(line => line.product.id === product.id); return existing ? current.map(line => line.product.id === product.id ? { ...line, quantity: Math.min(line.quantity + 1, product.current_stock) } : line) : [...current, { product, quantity: 1, discount: 0 }]; });
  const checkout = async () => { if (!lines.length) return fail("Adicione pelo menos um produto à venda."); try { await api.checkout({ payment_method: payment, sale_discount_type: saleDiscount ? "FIXED" : null, sale_discount_value: saleDiscount, items: lines.map(line => ({ product_id: line.product.id, quantity: line.quantity, discount_type: line.discount ? "FIXED" : null, discount_value: line.discount })) }); setLines([]); setSaleDiscount(0); await refresh(); notify("Venda confirmada, estoque e caixa atualizados."); } catch (err) { fail((err as Error).message); } };
  return <div className="pos"><SaleProductPicker products={products} quantities={Object.fromEntries(lines.map(line=>[line.product.id,line.quantity]))} add={add}/><section className="cart"><h2>Venda atual</h2>{lines.length ? <div className="cart-lines">{lines.map(line => <div className="cart-line" key={line.product.id}><div><b>{line.product.name}</b><small>{money(line.product.sale_price)} cada</small></div><input aria-label="Quantidade" type="number" min="1" max={line.product.current_stock} value={line.quantity} onChange={e => setLines(lines.map(item => item.product.id === line.product.id ? { ...item, quantity: Number(e.target.value) } : item))}/><input aria-label="Desconto" title="Desconto em reais" type="number" min="0" max={Number(line.product.sale_price) * line.quantity} step="0.01" value={line.discount || ""} placeholder="Desc." onChange={e => setLines(lines.map(item => item.product.id === line.product.id ? { ...item, discount: Number(e.target.value) } : item))}/><button className="remove" onClick={() => setLines(lines.filter(item => item.product.id !== line.product.id))}>×</button></div>)}</div> : <Empty text="Selecione um produto na lista e clique em Adicionar à venda."/>}<div className="checkout"><label>Desconto da venda (R$)<input type="number" min="0" max={subtotal} step="0.01" value={saleDiscount || ""} onChange={e => setSaleDiscount(Number(e.target.value))}/></label><div className="payment">{(["PIX", "CARD", "CASH"] as PaymentMethod[]).map(method => <button className={payment === method ? "selected" : ""} key={method} onClick={() => setPayment(method)}>{paymentNames[method]}</button>)}</div><div className="total"><span>Total a receber</span><strong>{money(total)}</strong></div><button className="primary checkout-button" onClick={() => void checkout()}>Confirmar venda</button></div></section></div>;
}

function Expenses({ refresh, notify, fail }: { refresh: () => Promise<void>; notify: (m: string) => void; fail: (m: string) => void }) { const [form, setForm] = useState({ description: "", category: "", amount: "", payment_method: "PIX" as PaymentMethod, payment_date: `${today}T12:00` }); const submit = async (event: FormEvent) => { event.preventDefault(); try { await api.expense({ ...form, amount: Number(form.amount), payment_date: new Date(form.payment_date).toISOString() }); await refresh(); setForm({ ...form, description: "", category: "", amount: "" }); notify("Despesa registrada no fluxo de caixa."); } catch (err) { fail((err as Error).message); } }; return <div className="form-page card"><p className="subtitle">Registre custos operacionais e mantenha a DRE atualizada.</p><form onSubmit={submit}><label>Descrição<input required placeholder="Ex.: Energia elétrica" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}/></label><div className="form-grid"><label>Categoria<input required placeholder="Ex.: Utilidades" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}/></label><label>Valor (R$)<input required type="number" min="0.01" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })}/></label></div><div className="form-grid"><label>Forma de pagamento<select value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value as PaymentMethod })}>{Object.entries(paymentNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Data do pagamento<input required type="datetime-local" value={form.payment_date} onChange={e => setForm({ ...form, payment_date: e.target.value })}/></label></div><button className="primary" type="submit">Registrar despesa</button></form></div>; }

function Reports({ period, setPeriod, dre, cash, abc }: { period: { start: string; end: string }; setPeriod: (v: { start: string; end: string }) => void; dre: DRE | null; cash: CashFlow | null; abc: ABCResponse | null }) { return <><div className="period card"><label>Início<input type="date" value={period.start} onChange={e => setPeriod({ ...period, start: e.target.value })}/></label><label>Fim<input type="date" value={period.end} onChange={e => setPeriod({ ...period, end: e.target.value })}/></label></div><section className="grid two"><article className="card"><div className="card-title"><h2>DRE</h2><span>Período selecionado</span></div><div className="result-lines"><Line label="Receita bruta" value={dre?.gross_revenue}/><Line label="Deduções e descontos" value={dre?.deductions_and_discounts} negative/><Line label="Receita líquida" value={dre?.net_revenue} strong/><Line label="CMV" value={dre?.cogs} negative/><Line label="Lucro bruto" value={dre?.gross_profit} strong/><Line label="Despesas operacionais" value={dre?.operating_expenses} negative/><Line label="Lucro líquido" value={dre?.net_profit} strong/></div></article><article className="card"><div className="card-title"><h2>Fluxo de caixa</h2><span>Período selecionado</span></div><div className="result-lines"><Line label="Saldo inicial" value={cash?.opening_balance}/><Line label="Entradas" value={cash?.income}/><Line label="Saídas" value={cash?.expenses} negative/><Line label="Saldo final" value={cash?.closing_balance} strong/></div></article></section><section className="card abc"><div className="card-title"><h2>Curva ABC de Produtos</h2><span>Faturamento: {money(abc?.total_revenue)}</span></div>{abc?.products.length ? <table><thead><tr><th>Produto</th><th>Faturamento</th><th>%</th><th>% acumulada</th><th>Classe</th></tr></thead><tbody>{abc.products.map(item => <tr key={item.product_id}><td>{item.product_name}</td><td>{money(item.revenue)}</td><td>{percentage(item.revenue_percentage)}%</td><td>{percentage(item.cumulative_percentage)}%</td><td><span className={`badge ${item.classification}`}>{item.classification}</span></td></tr>)}</tbody></table> : <Empty text="A Curva ABC será exibida assim que houver vendas no período."/>}</section><SalesCancellationPanel /></>; }

function SalesCancellationPanel() { const [sales, setSales] = useState<import("./types").SaleSummary[]>([]); const load = () => api.sales().then(setSales).catch(() => undefined); useEffect(() => { void load(); }, []); const cancel = async (id: string) => { if (!confirm("Cancelar esta venda? O estoque será devolvido e a entrada do caixa removida.")) return; try { await api.cancelSale(id); load(); } catch (error) { alert((error as Error).message); } }; return <section className="card abc"><div className="card-title"><h2>Vendas do sistema</h2><span>Cancelamento seguro</span></div><table><thead><tr><th>Data</th><th>Venda</th><th>Líquido recebido</th><th></th></tr></thead><tbody>{sales.map(s => <tr key={s.id}><td>{new Date(s.created_at).toLocaleDateString("pt-BR")}</td><td>{money(s.net_total)}</td><td>{money(s.received_total)}</td><td>{s.is_cancelled ? "Cancelada" : <button className="danger-text" onClick={() => void cancel(s.id)}>Cancelar</button>}</td></tr>)}</tbody></table>{!sales.length && <Empty text="Nenhuma venda cadastrada."/>}</section>; }

export default App;
