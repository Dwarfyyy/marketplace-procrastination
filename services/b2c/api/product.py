import uuid
from typing import Annotated

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from core import db
from exceptions.product import ProductNotFoundError
from exceptions.sku import SkuNotFoundError
from schemas.sku import Sku as SkuSchema, SkuShort as SkuShortSchema
from services import product_service, sku_service

router = fastapi.APIRouter(prefix="/api/v1/products")
catalog_products_router = fastapi.APIRouter(prefix="/api/v1/catalog/products")


@catalog_products_router.get("", response_model=ProductShortListResponse)
async def get_product_list_api(
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	category_id: Optional[uuid.UUID] = None,
	limit: Annotated[int, fastapi.Query(ge=1, le=100)] = 20,
	offset: Annotated[int, fastapi.Query(ge=0)] = 0,
	filter: Optional[str] = None,
	sort: str = "popularity",
	q: Optional[str] = None,
) -> ProductShortListResponse:
	filters_param = None
	if filter:
		try:
			filters_obj = json.loads(filter)
			filters_param = json.dumps(filters_obj, ensure_ascii=False)
		except json.JSONDecodeError as e:
			raise fastapi.HTTPException(
				status_code=400,
				detail={
					"code": "INVALID_FILTER",
					"message": "Invalid JSON in filter parameter",
				},
			) from e

	try:
		return await product_service.get_products_list(
			db_session,
			limit,
			offset,
			str(category_id) if category_id else None,
			filters_param,
			sort,
			q,
		)
	except ValueError as e:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "INVALID_REQUEST", "message": str(e)},
		) from e
	except SQLAlchemyError as e:
		raise fastapi.HTTPException(
			status_code=502,
			detail={"code": "B2B_UNAVAILABLE", "message": "Catalog service is unavailable"},
		) from e


@router.get("/{product_id}/skus/{sku_id}", response_model=SkuSchema)
async def get_sku_by_id_api(
	sku_id: uuid.UUID,
	product_id: uuid.UUID,  # noqa
	db: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
) -> SkuSchema:
	"""
	API endpoint for getting a sku by id
	:param sku_id: SKU ID
	:param product_id: product ID
	:param db: database session
	:return: SKU
	"""
	try:
		sku = await sku_service.get_sku_by_id(db, sku_id)
		return SkuSchema.model_validate(sku)
	except SkuNotFoundError as err:
		raise fastapi.HTTPException(status_code=404, detail=str(err)) from err


@router.get("/{product_id}/skus", response_model=list[SkuShortSchema])
async def get_product_skus_short_api(
	product_id: uuid.UUID,
	db: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
) -> list[SkuShortSchema]:
	"""
	API endpoint for getting a SKUs by product ID
	:param product_id: product ID
	:param db: database session
	:return: SKUs short
	"""
	try:
		skus = await product_service.get_product_skus_short(db, product_id)
		skus_validated = (SkuShortSchema.model_validate(sku) for sku in skus)
		return list(skus_validated)
	except ProductNotFoundError as err:
		raise fastapi.HTTPException(status_code=404, detail=str(err)) from err
