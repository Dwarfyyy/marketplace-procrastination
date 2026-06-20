from __future__ import annotations

import uuid

from enum import Enum

from pydantic import BaseModel, ConfigDict

from database.models.catalog.base import FilterTypeEnum


class CategoryParent(BaseModel):
	id: uuid.UUID
	name: str
	slug: str


class Seo(BaseModel):
	title: str
	description: str
	keywords: list[str]


class CategoryMeta(BaseModel):
	og_title: str | None
	og_description: str | None
	og_image: str | None
	twitter_card: str | None


class CategoryInfoResponse(BaseModel):
	id: uuid.UUID
	name: str
	slug: str
	description: str | None
	parent: CategoryParent | None
	product_count: int | None
	seo: Seo | None
	meta_tags: CategoryMeta | None
	image_url: str | None
	is_active: bool
	created_at: str
	updated_at: str


class Filter(BaseModel):
	id: uuid.UUID
	slug: str
	name: str
	type: FilterTypeEnum
	value: list[str] | str | float | None = None
	min: float | None = None
	max: float | None = None


class FilterResponse(BaseModel):
	items: list[Filter]


class FacetValue(BaseModel):
	value: str
	count: int


class Facet(BaseModel):
	name: str
	values: list[FacetValue]


class FacetsResponse(BaseModel):
	category_id: str
	filters: list[Filter]
	facets: list[Facet]


class BreadcrumbItem(BaseModel):
	id: uuid.UUID
	slug: str
	name: str
	url: str
	level: int
	is_current: bool  # Всмысле является ли элемент текущим? кто это писал? -_-


class ResolveViaEnum(str, Enum):
	CATEGORY = "CATEGORY"
	PRODUCT = "PRODUCT"


class BreadcrumbMeta(BaseModel):
	resolved_via: ResolveViaEnum
	category_id: uuid.UUID | None
	product_id: uuid.UUID | None


class BreadcrumbResponse(BaseModel):
	data: list[BreadcrumbItem]
	meta: BreadcrumbMeta


class CategoryInFavorite(BaseModel):
	id: uuid.UUID
	name: str
	model_config = ConfigDict(from_attributes=True)
