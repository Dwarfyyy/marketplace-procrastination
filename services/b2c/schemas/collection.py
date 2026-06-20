import uuid

from pydantic import BaseModel, ConfigDict

from schemas.catalog import CatalogProductCard


class Collection(BaseModel):
	"""Подборка товаров для главной (US-CART-05) с обогащёнными карточками.

	B2C хранит только список UUID товаров подборки; `products` собираются
	batch-обогащением из B2B на каждый запрос. В `products` попадают только
	доступные товары (`MODERATED`, не удалённые, с остатком `> 0`); недоступные
	(удалены/заблокированы/на модерации/нет в наличии) в выдачу не включаются —
	подборка при этом не ломается. Поле `name` соответствует колонке `title`
	модели. Нет доступных товаров → `products: []` (валидный ответ).
	"""

	id: uuid.UUID
	name: str
	description: str = ""
	cover_image_url: str | None = None
	target_url: str | None = None
	products: list[CatalogProductCard]
	model_config = ConfigDict(from_attributes=True)
