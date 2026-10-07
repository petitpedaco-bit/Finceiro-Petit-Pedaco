import type { ABCResponse, CashFlow, DRE, Product, ProductInput, SaleSummary } from "./types";

const API = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

export interface QuotationRow {
  sheet: string; sku: string; name: string; cost_price: string;
  additional_cost: string; sale_price: string; target_margin_percentage: string;
}
export interface QuotationPreview { rows: QuotationRow[]; warnings: string[]; notice: string }

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
  products: () => request<Product[]>("/products"),
  createProduct: (data: ProductInput) => request<Product>("/products", { method: "POST", body: JSON.stringify(data) }),
  updateProduct: (id: string, data: Partial<ProductInput>) => request<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProduct: (id: string) => request<void>(`/products/${id}`, { method: "DELETE" }),
  checkout: (data: unknown) => request("/sales/checkout", { method: "POST", body: JSON.stringify(data) }),
  expense: (data: unknown) => request("/cash-flow/expenses", { method: "POST", body: JSON.stringify(data) }),
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
};
