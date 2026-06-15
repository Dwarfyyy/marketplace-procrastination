from jose import JWTError, jwt

from core.config import settings


def decode_access_token(token: str) -> dict:
	if token.startswith("Bearer "):
		token = token[7:]

	try:
		return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
	except JWTError as e:
		raise ValueError(f"Невалидный или истёкший токен: {e}") from e
