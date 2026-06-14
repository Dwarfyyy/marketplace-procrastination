import uuid
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from schemas.category import CategoryInFavorite
from schemas.characteristic import CharacteristicInFavorite
from schemas.image import ImageInFavorite
from schemas.sku import SkuInFavorite


class ProductShort(BaseModel):
	id: uuid.UUID
	title: str
	image: str = Field(format="uri")
	price: float
	in_stock: bool
	is_in_cart: bool
	model_config = ConfigDict(from_attributes=True)


class ProductShortListResponse(BaseModel):
	total_count: int
	limit: int
	offset: int
	items: List[ProductShort]
	model_config = ConfigDict(from_attributes=True)


class ProductInFavorite(BaseModel):
	id: uuid.UUID
	title: str
	description: str | None
	status: str
	category: CategoryInFavorite
	images: List[ImageInFavorite]
	characteristics: List[CharacteristicInFavorite]
	skus: List[SkuInFavorite]
	model_config = ConfigDict(from_attributes=True)
