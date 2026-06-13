import uuid

from pydantic import BaseModel, ConfigDict

from schemas.catalog import CatalogProductCard


class CollectionSummary(BaseModel):
	"""Метаданные подборки для главной — без товаров внутри."""

	id: uuid.UUID
	name: str
	description: str = ""
	cover_image_url: str | None = None
	target_url: str | None = None
	model_config = ConfigDict(from_attributes=True)


class CollectionProducts(BaseModel):
	"""Товары конкретной подборки после batch-обогащения из B2B.

	`items` — доступные карточки товаров; `unavailable_ids` — UUID товаров,
	которые B2C хранит в составе подборки, но которые сейчас недоступны в B2B
	(удалены/заблокированы/на модерации/нет в наличии). Все товары недоступны →
	`items: []`, `unavailable_ids: [...]` — это валидный ответ, не ошибка.
	"""

	id: uuid.UUID
	name: str
	items: list[CatalogProductCard]
	unavailable_ids: list[uuid.UUID]
	model_config = ConfigDict(from_attributes=True)
