import uuid
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.models import ProductStatusEnum
from schemas.category import CategoryInFavorite
from schemas.characteristic import Characteristic, CharacteristicInFavorite
from schemas.image import ImageInFavorite
from schemas.sku import Sku, SkuInFavorite


class Product(BaseModel):
	id: uuid.UUID
	slug: str
	title: str
	description: str
	images: List[str]
	status: ProductStatusEnum
	characteristics: List[Characteristic]
	skus: List[Sku]
	model_config = ConfigDict(from_attributes=True)

	@field_validator("images", mode="before")
	@classmethod
	def _extract_image_urls(cls, value: Any) -> Any:
		return [item.url if hasattr(item, "url") else item for item in value]


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
