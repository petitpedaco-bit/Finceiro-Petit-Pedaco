import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Product, SaleItem
from app.schemas import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["Produtos"])


def not_found(product_id: uuid.UUID) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Produto {product_id} não encontrado")


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate, session: AsyncSession = Depends(get_session)
) -> ProductResponse:
    product = Product(**payload.model_dump())
    try:
        async with session.begin():
            session.add(product)
            await session.flush()
            await session.refresh(product)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU já cadastrado") from exc
    return ProductResponse.model_validate(product)


@router.get("", response_model=list[ProductResponse])
async def list_products(session: AsyncSession = Depends(get_session)) -> list[ProductResponse]:
    result = await session.execute(select(Product).order_by(Product.name))
    return [ProductResponse.model_validate(product) for product in result.scalars()]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> ProductResponse:
    product = await session.get(Product, product_id)
    if product is None:
        raise not_found(product_id)
    return ProductResponse.model_validate(product)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, session: AsyncSession = Depends(get_session)
) -> ProductResponse:
    try:
        async with session.begin():
            product = await session.get(Product, product_id)
            if product is None:
                raise not_found(product_id)
            for field, value in payload.model_dump(exclude_unset=True).items():
                setattr(product, field, value)
            await session.flush()
            await session.refresh(product)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU já cadastrado") from exc
    return ProductResponse.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Response:
    async with session.begin():
        product = await session.get(Product, product_id)
        if product is None:
            raise not_found(product_id)
        has_sales = await session.scalar(
            select(SaleItem.id).where(SaleItem.product_id == product_id).limit(1)
        )
        if has_sales is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Produto com histórico de vendas não pode ser excluído",
            )
        await session.delete(product)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
