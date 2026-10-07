import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import PaymentMethod

MONEY_QUANTUM = Decimal("0.01")


class DiscountType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=64)
    cost_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    additional_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    target_margin_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    reseller_cash_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    reseller_card_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    sale_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    current_stock: int = Field(ge=0)

    @field_validator("name", "sku")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("não pode ser vazio")
        return value


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    additional_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    target_margin_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    reseller_cash_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    reseller_card_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    current_stock: int | None = Field(default=None, ge=0)

    @field_validator("name", "sku")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("não pode ser vazio")
        return value


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CheckoutItem(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    discount_type: DiscountType | None = None
    discount_value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def require_type_when_discounted(self) -> "CheckoutItem":
        if self.discount_value > 0 and self.discount_type is None:
            raise ValueError("discount_type é obrigatório quando há desconto")
        if self.discount_type == DiscountType.PERCENTAGE and self.discount_value > 100:
            raise ValueError("desconto percentual não pode exceder 100%")
        return self


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1)
    payment_method: PaymentMethod
    card_brand: str | None = Field(default=None, max_length=30)
    sale_discount_type: DiscountType | None = None
    sale_discount_value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @field_validator("items")
    @classmethod
    def reject_duplicate_products(cls, value: list[CheckoutItem]) -> list[CheckoutItem]:
        if len({item.product_id for item in value}) != len(value):
            raise ValueError("cada produto deve aparecer apenas uma vez na venda")
        return value

    @model_validator(mode="after")
    def validate_sale_discount(self) -> "CheckoutRequest":
        if self.sale_discount_value > 0 and self.sale_discount_type is None:
            raise ValueError("sale_discount_type é obrigatório quando há desconto")
        if self.sale_discount_type == DiscountType.PERCENTAGE and self.sale_discount_value > 100:
            raise ValueError("desconto percentual não pode exceder 100%")
        return self


class SaleItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    unit_cost: Decimal
    discount_amount: Decimal
    line_total: Decimal


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    gross_total: Decimal
    discount_total: Decimal
    net_total: Decimal
    payment_fee_amount: Decimal
    received_total: Decimal
    payment_method: PaymentMethod
    created_at: datetime
    items: list[SaleItemResponse]


class SaleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    net_total: Decimal
    received_total: Decimal
    payment_fee_amount: Decimal
    payment_method: PaymentMethod
    created_at: datetime
    is_cancelled: bool


class ExpenseCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_method: PaymentMethod
    payment_date: datetime


class DREResponse(BaseModel):
    start_date: date
    end_date: date
    gross_revenue: Decimal
    deductions_and_discounts: Decimal
    net_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    payment_fees: Decimal
    net_profit: Decimal


class ABCProduct(BaseModel):
    product_id: uuid.UUID
    product_name: str
    revenue: Decimal
    revenue_percentage: Decimal
    cumulative_percentage: Decimal
    classification: str


class ABCCurveResponse(BaseModel):
    start_date: date
    end_date: date
    total_revenue: Decimal
    products: list[ABCProduct]


class CashFlowResponse(BaseModel):
    start_date: date
    end_date: date
    opening_balance: Decimal
    income: Decimal
    expenses: Decimal
    closing_balance: Decimal
