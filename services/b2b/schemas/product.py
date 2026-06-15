from datetime import datetime
from typing import List, Optional
from uuid import UUID

from database.models import ProductStatusEnum
from pydantic import BaseModel, ConfigDict, Field
from schemas.sku import SkuResponse


class Characteristic(BaseModel):
	name: str = Field(..., min_length=1, max_length=255)
	value: str = Field(..., min_length=1, max_length=255)


class ProductImageCreate(BaseModel):
	url: str = Field(..., min_length=1, max_length=512)
	ordering: int = 0


class ProductCreate(BaseModel):
	title: str = Field(..., min_length=1, max_length=255)
	description: str = Field(..., min_length=1, max_length=5000)
	category_id: UUID
	slug: str | None = Field(default=None, min_length=1, max_length=255)
	images: List[ProductImageCreate] = Field(default_factory=list)
	characteristics: List[Characteristic] = Field(default_factory=list)


class ProductUpdate(BaseModel):
	title: Optional[str] = Field(None, min_length=1, max_length=255)
	description: Optional[str] = Field(None, max_length=5000)
	category_id: Optional[UUID] = None
	characteristics: Optional[List[Characteristic]] = None


class ProductSellerRead(BaseModel):
	id: UUID
	seller_id: UUID
	title: str
	slug: str
	description: str | None
	status: ProductStatusEnum
	category_id: UUID
	deleted: bool
	skus_count: int
	total_active_quantity: int
	created_at: datetime
	updated_at: datetime

	model_config = ConfigDict(from_attributes=True)


class ProductPaginatedResponse(BaseModel):
	items: list[ProductSellerRead]
	total_count: int
	limit: int
	offset: int


class ProductImageResponse(BaseModel):
	id: UUID
	url: str
	ordering: int


class CharacteristicsResponse(BaseModel):
	id: UUID
	name: str
	value: str


class BlockingReason(BaseModel):
	id: UUID
	title: str
	comment: str


class FieldReport(BaseModel):
	field_name: str
	sku_id: UUID | None = None
	comment: str


class ProductDetailResponse(BaseModel):
	id: UUID
	seller_id: UUID
	category_id: UUID
	title: str
	slug: str
	description: str
	status: ProductStatusEnum
	deleted: bool
	images: List[ProductImageResponse]
	characteristics: List[CharacteristicsResponse]
	skus: List[SkuResponse]
	created_at: datetime
	updated_at: datetime
	blocked: bool
	blocking_reason: BlockingReason | None
	field_reports: List[FieldReport]


class ProductResponse(BaseModel):
	id: UUID
	seller_id: UUID
	category_id: UUID
	title: str
	slug: str
	description: str
	status: ProductStatusEnum
	deleted: bool
	blocking_reason_id: UUID | None
	moderator_comment: str | None
	images: List[ProductImageResponse]
	characteristics: List[CharacteristicsResponse]
	skus: List[SkuResponse]
	created_at: datetime
	updated_at: datetime
