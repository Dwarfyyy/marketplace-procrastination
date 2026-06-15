import fastapi

import uuid
from typing import Annotated, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Request
import json

from exceptions.banner import BannerNotFoundError, EmptyEventsError
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


from schemas.collection import Collection
from services import (
	banner_service,
	category_service,
	collection_service,
	product_service,
)
from core.db import get_db

router = fastapi.APIRouter(prefix="/api/v1/catalog")


def _parse_deep_object(query_params, prefix: str) -> dict:
	"""Parse deepObject-style query params (``prefix[key]=value``) into a dict.

	Repeated keys collapse into a list, matching ``style: deepObject,
	explode: true`` from the OpenAPI contract.
	"""
	open_token = f"{prefix}["
	result: dict = {}
	for key, value in query_params.multi_items():
		if key.startswith(open_token) and key.endswith("]"):
			inner = key[len(open_token) : -1]
			if inner in result:
				if isinstance(result[inner], list):
					result[inner].append(value)
				else:
					result[inner] = [result[inner], value]
			else:
				result[inner] = value
	return result


@router.get("/products", response_model=PaginatedCatalogProducts)
async def get_catalog_products(
	request: Request,
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	limit: Annotated[int, fastapi.Query(ge=1, le=100)] = 20,
	offset: Annotated[int, fastapi.Query(ge=0)] = 0,
	sort: str = "popularity",
	q: Optional[str] = None,
) -> PaginatedCatalogProducts:
	# `filter` is a deepObject per the contract: filter[category_id]=...&filter[price_min]=...
	filter_obj = _parse_deep_object(request.query_params, "filter")

	category_id_raw = filter_obj.pop("category_id", None)
	category_id: Optional[uuid.UUID] = None
	if category_id_raw is not None:
		try:
			category_id = uuid.UUID(str(category_id_raw))
		except (ValueError, TypeError) as e:
			raise fastapi.HTTPException(
				status_code=400,
				detail={
					"code": "INVALID_REQUEST",
					"message": "filter[category_id] must be a valid UUID",
				},
			) from e

	filters_param = json.dumps(filter_obj, ensure_ascii=False) if filter_obj else None

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
	deep = _parse_deep_object(request.query_params, "filters")
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


@router.get("/collections", response_model=list[Collection])
async def get_collections(
	db: Annotated[AsyncSession, fastapi.Depends(get_db)],
) -> list[Collection]:
	"""Active collections with their products, batch-enriched from B2B.

	Each collection embeds available product cards in ``products``; unavailable
	products (deleted/blocked/under moderation/out of stock) are omitted. No
	active collections yields ``200`` with an empty array.
	"""
	return await collection_service.get_collections(db)


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
