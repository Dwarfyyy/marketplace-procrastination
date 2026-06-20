import uuid
from typing import List

from pydantic import BaseModel, ConfigDict, Field, computed_field

from schemas.characteristic import Characteristic


class CategoryRef(BaseModel):
	id: uuid.UUID
	name: str
	parent_id: uuid.UUID | None = None
	level: int = Field(ge=0)
	path: List[str]
	model_config = ConfigDict(from_attributes=True)


class CategoryTreeNode(CategoryRef):
	children: List["CategoryTreeNode"] = Field(default_factory=list)
	model_config = ConfigDict(from_attributes=True)


class ImageRef(BaseModel):
	id: uuid.UUID
	url: str
	alt: str = ""
	ordering: int = Field(ge=0)
	is_main: bool = False
	model_config = ConfigDict(from_attributes=True)


class CatalogProductSeller(BaseModel):
	id: uuid.UUID
	display_name: str
	model_config = ConfigDict(from_attributes=True)


class CatalogProductCard(BaseModel):
	id: uuid.UUID
	name: str
	min_price: int
	old_price: int | None = None
	slug: str | None = None
	category: CategoryRef | None = None
	has_stock: bool
	rating: float | None = Field(default=None, ge=0, le=5)
	reviews_count: int = Field(default=0, ge=0)
	images: List[ImageRef]
	seller: CatalogProductSeller | None = None
	model_config = ConfigDict(from_attributes=True)


class CatalogSku(BaseModel):
	id: uuid.UUID
	name: str
	price: int
	discount: int = 0
	available_quantity: int = Field(ge=0)
	characteristics: List[Characteristic] = []
	images: List[ImageRef] = []
	model_config = ConfigDict(from_attributes=True)

	@computed_field
	@property
	def in_stock(self) -> bool:
		return self.available_quantity > 0


class CatalogProductDetail(BaseModel):
	id: uuid.UUID
	name: str
	slug: str
	description: str | None = None
	min_price: int
	has_stock: bool
	images: List[ImageRef]
	characteristics: List[Characteristic] = []
	skus: List[CatalogSku] = []
	model_config = ConfigDict(from_attributes=True)


class PaginatedCatalogProducts(BaseModel):
	items: List[CatalogProductCard]
	total_count: int
	limit: int
	offset: int
	model_config = ConfigDict(from_attributes=True)
