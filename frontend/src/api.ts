import type { ABCResponse, CashFlow, DRE, Product, ProductInput, SaleSummary } from "./types";

const API = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

export interface QuotationRow {
  sheet: string; sku: string; name: string; cost_price: string;
  additional_cost: string; sale_price: string; target_margin_percentage: string;
}
export interface QuotationPreview { rows: QuotationRow[]; warnings: string[]; notice: string }
export interface QuotationProduct extends QuotationRow { document_id:string; document_title:string; product:Product|null }
export interface SheetCell { value: string | number | boolean | null; formula?: string | null; format: string; error?: string | null }
export interface QuotationBook { sheets: {name: string; rows: SheetCell[][]}[] }
export interface WorkbookDocument { id?: string; version: number; title: string; source_url: string | null; book: QuotationBook; bindings: Record<string,string> }
export interface WorkbookResult { book: QuotationBook; rows: QuotationRow[]; warnings: string[] }
export interface WorkbookSummary extends Omit<WorkbookDocument,'book'> { rows:QuotationRow[]; warnings:string[]; sheet_names:string[] }
export interface ExpenseRecord { id:string;description:string;category:string|null;amount:string;payment_method:string;occurred_at:string;expense_nature:string;expense_behavior:string;expense_context:string;classification_reviewed:boolean }
export interface ExpenseSuggestion { expense_nature:string;expense_behavior:string;category:string;reason:string;confidence:string;method:string }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  if (import.meta.env.MODE === "github-pages" && !import.meta.env.VITE_API_URL) {
    throw new Error("A interface foi publicada. Falta configurar o endereço da API na nuvem (VITE_API_URL).");
  }
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Erro de comunicação com a API" }));
    throw new Error(body.detail ?? "Não foi possível concluir a operação");
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const api = {
  quotationProducts: (search:string,signal?:AbortSignal) => request<QuotationProduct[]>(`/quotations/products?search=${encodeURIComponent(search)}`,{signal}),
  products: () => request<Product[]>("/products"),
  createProduct: (data: ProductInput) => request<Product>("/products", { method: "POST", body: JSON.stringify(data) }),
  updateProduct: (id: string, data: Partial<ProductInput>) => request<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProduct: (id: string) => request<void>(`/products/${id}`, { method: "DELETE" }),
  checkout: (data: unknown) => request("/sales/checkout", { method: "POST", body: JSON.stringify(data) }),
  expense: (data: unknown) => request("/cash-flow/expenses", { method: "POST", body: JSON.stringify(data) }),
  suggestExpense: (data:unknown) => request<ExpenseSuggestion>('/cash-flow/expenses/suggest',{method:'POST',body:JSON.stringify(data)}),
  expenseHistory: (offset=0) => request<{items:ExpenseRecord[];total:number}>(`/cash-flow/expenses?limit=20&offset=${offset}`),
  reviewExpense: (id:string,data:unknown) => request<ExpenseRecord>(`/cash-flow/expenses/${id}/classification`,{method:'PATCH',body:JSON.stringify(data)}),
  expenseBreakdown: (start:string,end:string) => request<{groups:{expense_nature:string;expense_behavior:string;amount:string;count:number}[];notice:string}>(`/reports/expense-breakdown?start_date=${start}&end_date=${end}`),
  dre: (start: string, end: string) => request<DRE>(`/reports/dre?start_date=${start}&end_date=${end}`),
  abc: (start: string, end: string) => request<ABCResponse>(`/reports/abc-curve?start_date=${start}&end_date=${end}`),
  cashFlow: (start: string, end: string) => request<CashFlow>(`/reports/cash-flow?start_date=${start}&end_date=${end}`),
  sales: () => request<SaleSummary[]>("/sales"),
  cancelSale: (id: string) => request<void>(`/sales/${id}`, { method: "DELETE" }),
  quotationGoogle: (url: string) => request<QuotationPreview>("/quotations/preview/google", { method: "POST", body: JSON.stringify({url}) }),
  quotationExcel: async (file: File): Promise<QuotationPreview> => {
    const data = new FormData(); data.append("file", file);
    const response = await fetch(`${API}/quotations/preview/excel`, {method: "POST", body: data});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Não foi possível importar o Excel");
    return result;
  },
  quotationApply: (rows: QuotationRow[], update_sale_prices: boolean) => request<{created: number; updated: number}>("/quotations/apply", {method: "POST", body: JSON.stringify({rows, update_sale_prices})}),
  workbookGoogle: (url: string) => request<{book: QuotationBook}>("/quotations/workbook/google", {method: "POST", body: JSON.stringify({url})}),
  workbookExcel: async (file: File): Promise<{book: QuotationBook}> => {
    const data = new FormData(); data.append('file',file);
    const response = await fetch(`${API}/quotations/workbook/excel`, {method:'POST', body:data});
    const result = await response.json();
    if(!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Falha ao importar planilha');
    return result;
  },
  workbookCalculate: (book: QuotationBook) => request<WorkbookResult>('/quotations/workbook/calculate', {method:'POST',body:JSON.stringify(book)}),
  workbookList: () => request<{id:string;title:string;version:number}[]>('/quotations/documents'),
  workbookGet: (id:string) => request<WorkbookDocument>(`/quotations/documents/${id}`),
  workbookSummary: (id:string) => request<WorkbookSummary>(`/quotations/documents/${id}/summary`),
  workbookSave: (document:WorkbookDocument, sync_sheets:string[], update_sale_prices:boolean) => request<WorkbookResult & {id:string;version:number;bindings:Record<string,string>;created:number;updated:number}>('/quotations/documents/save',{method:'POST',body:JSON.stringify({...document,sync_sheets,update_sale_prices})}),
};
