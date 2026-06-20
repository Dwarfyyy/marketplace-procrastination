import uuid
from typing import List

from pydantic import BaseModel, ConfigDict

from schemas.category import CategoryInFavorite
from schemas.characteristic import CharacteristicInFavorite
from schemas.image import ImageInFavorite
from schemas.sku import SkuInFavorite


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
