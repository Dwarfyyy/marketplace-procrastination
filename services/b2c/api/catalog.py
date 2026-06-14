import fastapi

import uuid
from typing import Annotated, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Request
import json

from exceptions.banner import BannerNotFoundError, EmptyEventsError
from exceptions.collection import CollectionNotFoundError
from exceptions.product import ProductNotFoundError
from schemas.banner import Banner, BannerEventsRequest
from schemas.catalog import (
	CatalogProductCard,
	CatalogProductDetail,
	CategoryRef,
	CategoryTreeNode,
	PaginatedCatalogProducts,
)
from schemas.category import CategoryInfoResponse, FacetsResponse, FilterResponse
from exceptions.category import CategoryNotFoundError
from core import db


from schemas.collection import CollectionProducts, CollectionSummary
from services import (
	banner_service,
	category_service,
	collection_service,
	product_service,
)
from core.db import get_db

router = fastapi.APIRouter(prefix="/api/v1/catalog")


@router.get("/products", response_model=PaginatedCatalogProducts)
async def get_catalog_products(
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	category_id: Optional[uuid.UUID] = None,
	limit: Annotated[int, fastapi.Query(ge=1, le=100)] = 20,
	offset: Annotated[int, fastapi.Query(ge=0)] = 0,
	filter: Optional[str] = None,
	sort: str = "popularity",
	q: Optional[str] = None,
) -> PaginatedCatalogProducts:
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


@router.get("/categories/tree", response_model=list[CategoryTreeNode])
async def get_categories_tree(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
) -> list[CategoryTreeNode]:
	"""Get categories tree

	Args:
		db (Annotated[AsyncSession, fastapi.Depends]): Database session

	Returns:
		list[CategoryTreeNode]: Categories tree
	"""
	try:
		return await category_service.get_categories_tree(db)
	except CategoryNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e
	except Exception as e:
		raise fastapi.HTTPException(status_code=503, detail=str(e)) from e


@router.get("/categories", response_model=list[CategoryRef])
async def get_categories_flat(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
) -> list[CategoryRef]:
	"""Get flat categories

	Args:
		db (Annotated[AsyncSession, fastapi.Depends]): Database session

	Returns:
		list[CategoryRef]: Flat categories
	"""
	try:
		return await category_service.get_categories_flat(db)
	except Exception as e:
		raise fastapi.HTTPException(status_code=503, detail=str(e)) from e


@router.get("/categories/{category_id}", response_model=CategoryInfoResponse)
async def get_category_info(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
	category_id: str,
	include_product_count: bool = False,
) -> CategoryInfoResponse:
	"""Get category info

	Args:
		db (Annotated[AsyncSession, fastapi.Depends]): Database session
		category_id (str): Category ID
		include_product_count (bool, optional): Include product count

	Returns:
		CategoryInfoResponse: Category info
	"""
	try:
		return await category_service.get_category_info(
			db, category_id, include_product_count
		)
	except ValueError as e:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "INVALID_REQUEST", "message": "id must be a valid UUID"},
		) from e
	except CategoryNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e
	except Exception as e:
		raise fastapi.HTTPException(status_code=503, detail=str(e)) from e


@router.get("/categories/{category_id}/filters", response_model=FilterResponse)
async def get_category_filters(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
	category_id: str,
) -> FilterResponse:
	"""Get category filters

	Args:
		db (Annotated[AsyncSession, fastapi.Depends]): Database session
		category_id (str): Category ID

	Returns:
		FilterResponse: Category filters
	"""
	try:
		return await category_service.get_category_filters(db, category_id)
	except ValueError as e:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "INVALID_REQUEST", "message": "id must be a valid UUID"},
		) from e
	except CategoryNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e
	except Exception as e:
		raise fastapi.HTTPException(status_code=503, detail=str(e)) from e


@router.get("/facets", response_model=FacetsResponse)
async def get_facets(
	request: Request,
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	category_id: uuid.UUID,
	filters: str | None = None,
) -> FacetsResponse:
	qp = request.query_params
	deep: dict = {}
	for k, v in qp.multi_items():
		if k.startswith("filters[") and k.endswith("]"):
			inner = k[len("filters[") : -1]
			if inner in deep:
				if isinstance(deep[inner], list):
					deep[inner].append(v)
				else:
					deep[inner] = [deep[inner], v]
			else:
				deep[inner] = v

	filters_param = json.dumps(deep, ensure_ascii=False) if deep else filters

	try:
		return await category_service.get_category_facets(
			db_session, category_id, filters_param
		)
	except CategoryNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e
	except SQLAlchemyError as e:
		raise fastapi.HTTPException(
			status_code=502,
			detail={"code": "B2B_UNAVAILABLE", "message": "Catalog service is unavailable"},
		) from e


@router.get("/collections", response_model=list[CollectionSummary])
async def get_collections(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
) -> list[CollectionSummary]:
	"""List active collections (metadata only, without products)."""
	return await collection_service.get_collection_summaries(db)


@router.get("/collections/{collection_id}", response_model=CollectionProducts)
async def get_collection_products(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
	collection_id: uuid.UUID,
) -> CollectionProducts:
	"""Products of a single collection, batch-enriched from B2B.

	Unavailable products go to ``unavailable_ids`` (not an error); an unknown
	collection yields ``404``.
	"""
	try:
		return await collection_service.get_collection_products(db, collection_id)
	except CollectionNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e


@router.get("/banners")
async def get_banners(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
) -> list[Banner]:
	"""Get active banners

	Args:
	    db (Annotated[AsyncSession, fastapi.Depends]): Database session

	Returns:
	    list[Banner]: List of active banners
	"""
	return await banner_service.get_active_banners(db)


@router.post("/banner-events", status_code=204)
async def post_banner_events(
	request: Request,
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
	body: BannerEventsRequest,
) -> fastapi.Response:
	user_id = getattr(request.state, "user_id", None)
	try:
		await banner_service.record_banner_events(db, body, user_id)
	except EmptyEventsError as e:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "EMPTY_EVENTS", "message": str(e)},
		) from e
	except BannerNotFoundError as e:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "BANNER_NOT_FOUND", "message": str(e)},
		) from e
	return fastapi.Response(status_code=204)


@router.get("/products/{product_id}", response_model=CatalogProductDetail)
async def get_catalog_product_api(
	db: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	product_id: uuid.UUID,
) -> CatalogProductDetail:
	"""Get a buyer-facing product card with nested SKUs by product id.

	Args:
		db (Annotated[AsyncSession, fastapi.Depends]): Database session
		product_id (uuid.UUID): Product ID

	Returns:
		CatalogProductDetail: Product detail card
	"""
	try:
		return await product_service.get_product_by_id(db, product_id)
	except ProductNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(err)},
		) from err
	except Exception as e:
		raise fastapi.HTTPException(status_code=500, detail=str(e)) from e


@router.get(
	"/products/{product_id}/similar",
	response_model=list[CatalogProductCard],
)
async def get_similar_products_api(
	db: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	product_id: uuid.UUID,
	limit: Annotated[int, fastapi.Query(ge=1, le=50)] = 10,
) -> list[CatalogProductCard]:
	try:
		return await product_service.get_similar_products(db, product_id, limit)
	except ProductNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(err)},
		) from err
	except Exception as e:
		raise fastapi.HTTPException(status_code=500, detail=str(e)) from e
