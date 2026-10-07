export type PaymentMethod = "PIX" | "CARD" | "CASH";

export interface Product {
  id: string;
  name: string;
  sku: string;
  cost_price: string;
  sale_price: string;
  current_stock: number;
}

export interface ProductInput {
  name: string;
  sku: string;
  cost_price: number | string;
  sale_price: number | string;
  current_stock: number;
}

export interface DRE {
  gross_revenue: string;
  deductions_and_discounts: string;
  net_revenue: string;
  cogs: string;
  gross_profit: string;
  operating_expenses: string;
  net_profit: string;
}

export interface ABCProduct {
  product_id: string;
  product_name: string;
  revenue: string;
  revenue_percentage: string;
  cumulative_percentage: string;
  classification: "A" | "B" | "C";
}

export interface ABCResponse { total_revenue: string; products: ABCProduct[] }

export interface CashFlow {
  opening_balance: string;
  income: string;
  expenses: string;
  closing_balance: string;
}
