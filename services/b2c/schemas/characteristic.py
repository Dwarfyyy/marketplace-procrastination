import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints, Field, ConfigDict

CharacteristicName = Annotated[
	str,
	StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[A-Z_]+$"),
	Field(
		examples=["BRAND", "COLOR", "SIZE"],
	),
]


class Characteristic(BaseModel):
	id: uuid.UUID
	name: CharacteristicName
	value: str
	model_config = ConfigDict(from_attributes=True)


class CharacteristicInFavorite(BaseModel):
	name: str
	value: str
	model_config = ConfigDict(from_attributes=True)
