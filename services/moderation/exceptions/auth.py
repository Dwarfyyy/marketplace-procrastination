from exceptions.base import MarketplaceError


class InvalidTokenError(MarketplaceError):
	"""Raised when the moderator's bearer token is missing or invalid."""
