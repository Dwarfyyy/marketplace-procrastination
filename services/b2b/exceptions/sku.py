from exceptions.base import MarketplaceError


class SkuError(MarketplaceError):
	"""Base exception for SKU-related errors."""


class SkuNotFoundError(SkuError):
	"""Raised when a SKU is not found in the catalog."""


class SkuAlreadyExistsError(SkuError):
	"""Raised when a SKU with the same attributes already exists."""


class SkuForbiddenError(SkuError):
	"""Raised when SKU operation is not allowed (e.g. HARD_BLOCKED product)."""


class SkuValidationError(SkuError):
	"""Raised when SKU request data fails business validation."""


class SkuActiveReservesError(SkuError):
	"""Raised when a SKU with active reserves cannot be deleted."""


class SkuInsufficientStockError(SkuError):
	"""Raised when an inventory operation cannot be applied atomically."""


class SkuIdempotencyConflictError(SkuError):
	"""Raised when an idempotency key is reused with a different payload."""
