import type { ABCResponse, CashFlow, DRE, Product, ProductInput } from "./types";

const API = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
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
};
