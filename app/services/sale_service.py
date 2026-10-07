from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InsufficientStockError, ProductNotFoundError
from app.models import CashFlowTransaction, CashFlowType, Product, Sale, SaleItem
from app.schemas import CheckoutRequest, DiscountType, MONEY_QUANTUM


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def discount(base: Decimal, kind: DiscountType | None, value: Decimal) -> Decimal:
    """Calcula e valida desconto sem jamais permitir total negativo."""
    amount = base * value / Decimal("100") if kind == DiscountType.PERCENTAGE else value
    amount = money(amount)
    if amount > base:
        raise ValueError("desconto não pode ser superior ao valor aplicado")
    return amount


def pagbank_fee_rate(payment_method: object, card_brand: str | None) -> Decimal:
    """Taxas iniciais PagBank para recebimento imediato; podem ser sobrescritas futuramente."""
    method = getattr(payment_method, "value", payment_method)
    other_brand = (card_brand or "").upper() in {"ELO", "AMEX", "HIPERCARD", "OUTROS"}
    if method == "DEBIT_CARD":
        return Decimal("0.0298") if other_brand else Decimal("0.0199")
    if method in {"CREDIT_CARD", "CARD"}:
        return Decimal("0.0617") if other_brand else Decimal("0.0499")
    return Decimal("0")


class SaleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def checkout(self, request: CheckoutRequest) -> Sale:
        """Confirma uma venda, baixa o estoque e cria a entrada de caixa em uma única transação."""
        async with self.session.begin():
            product_ids = [item.product_id for item in request.items]
            result = await self.session.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            )
            products = {product.id: product for product in result.scalars()}
            missing = set(product_ids) - set(products)
            if missing:
                raise ProductNotFoundError(f"Produtos não encontrados: {', '.join(map(str, missing))}")

            for item in request.items:
                product = products[item.product_id]
                if product.current_stock < item.quantity:
                    raise InsufficientStockError(
                        f"Estoque insuficiente para {product.sku}: disponível {product.current_stock}"
                    )

            prepared: list[tuple[Product, int, Decimal, Decimal, Decimal]] = []
            gross_total = Decimal("0")
            subtotal_after_item_discount = Decimal("0")
            item_discount_total = Decimal("0")
            for item in request.items:
                product = products[item.product_id]
                gross = money(product.sale_price * item.quantity)
                item_discount = discount(gross, item.discount_type, item.discount_value)
                subtotal = gross - item_discount
                prepared.append((product, item.quantity, gross, item_discount, subtotal))
                gross_total += gross
                subtotal_after_item_discount += subtotal
                item_discount_total += item_discount

            sale_discount = discount(
                subtotal_after_item_discount, request.sale_discount_type, request.sale_discount_value
            )
            net_total = money(subtotal_after_item_discount - sale_discount)
            fee_rate = pagbank_fee_rate(request.payment_method, request.card_brand)
            fee_amount = money(net_total * fee_rate)
            sale = Sale(
                gross_total=money(gross_total),
                discount_total=money(item_discount_total + sale_discount),
                net_total=net_total,
                payment_fee_rate=fee_rate,
                payment_fee_amount=fee_amount,
                received_total=net_total - fee_amount,
                payment_method=request.payment_method,
            )
            self.session.add(sale)
            await self.session.flush()

            # Rateia desconto da venda nas linhas; o resíduo de arredondamento fica na última.
            allocated = Decimal("0")
            for index, (product, quantity, gross, item_discount, subtotal) in enumerate(prepared):
                allocated_sale_discount = (
                    sale_discount - allocated
                    if index == len(prepared) - 1
                    else money(sale_discount * subtotal / subtotal_after_item_discount)
                    if subtotal_after_item_discount
                    else Decimal("0")
                )
                allocated += allocated_sale_discount
                product.current_stock -= quantity
                self.session.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.sale_price,
                        unit_cost=money(product.cost_price + product.additional_cost),
                        discount_amount=money(item_discount + allocated_sale_discount),
                        line_total=money(subtotal - allocated_sale_discount),
                    )
                )

            self.session.add(
                CashFlowTransaction(
                    transaction_type=CashFlowType.INCOME,
                    description=f"Venda {sale.id}",
                    category="Vendas",
                    amount=sale.received_total,
                    payment_method=request.payment_method,
                    occurred_at=datetime.now(timezone.utc),
                    sale_id=sale.id,
                )
            )

        await self.session.refresh(sale, attribute_names=["items"])
        return sale

    async def cancel(self, sale_id: object) -> None:
        """Cancela a venda, recompõe estoque e remove somente sua entrada de caixa."""
        async with self.session.begin():
            sale = await self.session.scalar(select(Sale).where(Sale.id == sale_id).with_for_update())
            if sale is None:
                raise ProductNotFoundError("Venda não encontrada")
            if sale.is_cancelled:
                raise ValueError("Esta venda já foi cancelada")
            items = (await self.session.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))).scalars().all()
            for item in items:
                product = await self.session.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
                if product is not None:
                    product.current_stock += item.quantity
            sale.is_cancelled = True
            sale.cancelled_at = datetime.now(timezone.utc)
            await self.session.execute(delete(CashFlowTransaction).where(CashFlowTransaction.sale_id == sale.id))
