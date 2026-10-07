import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class PaymentMethod(str, enum.Enum):
    PIX = "PIX"
    CARD = "CARD"
    CREDIT_CARD = "CREDIT_CARD"
    DEBIT_CARD = "DEBIT_CARD"
    CREDIT_CARD = "CREDIT_CARD"
    DEBIT_CARD = "DEBIT_CARD"
    CASH = "CASH"


class CashFlowType(str, enum.Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    additional_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    target_margin_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    reseller_cash_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reseller_card_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    additional_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    target_margin_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    reseller_cash_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reseller_card_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sale_items: Mapped[list["SaleItem"]] = relationship(back_populates="product")


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gross_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    payment_fee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    received_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    payment_fee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    received_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    cash_transaction: Mapped["CashFlowTransaction | None"] = relationship(back_populates="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sales.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="sale_items")


class CashFlowTransaction(Base):
    __tablename__ = "cash_flow_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transaction_type: Mapped[CashFlowType] = mapped_column(Enum(CashFlowType), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sales.id"), unique=True, nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sale: Mapped[Sale | None] = relationship(back_populates="cash_transaction")
