from exceptions.base import MarketplaceError


class CardNotFoundError(MarketplaceError):
	"""Raised when a moderation card does not exist."""


class CardNotAssignedToModeratorError(MarketplaceError):
	"""Raised when the current moderator is not assigned to the card."""


class CardNotInReviewError(MarketplaceError):
	"""Raised when a card is not in IN_REVIEW status and cannot be approved."""


class CardMissingSkuError(MarketplaceError):
	"""Raised when a card's product snapshot has no SKUs and cannot be approved."""
