import uuid
from typing import List

from pydantic import BaseModel, ConfigDict

from database.models import ProductStatusEnum
from schemas.category import CategoryInFavorite
from schemas.characteristic import Characteristic, CharacteristicInFavorite
from schemas.image import Image, ImageInFavorite
from schemas.sku import Sku, SkuInFavorite


class Product(BaseModel):
	id: uuid.UUID
	slug: str
	title: str
	description: str
	images: List[Image]
	status: ProductStatusEnum
	characteristics: List[Characteristic]
	skus: List[Sku]
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
