class OrderError(Exception):
	"""Base exception for order operations"""

	pass


class IdempotencyConflictError(OrderError):
	"""Idempotency conflict error"""

	pass


class InvalidIdempotencyKeyError(OrderError):
	"""Invalid idempotency key error"""

	pass


class ReserveFailedError(OrderError):
	"""Reserve failed error"""

	pass


class AddressNotFoundError(OrderError):
	"""Address not found error"""

	pass


class PaymentMethodNotFoundError(OrderError):
	"""Payment method not found error"""

	pass


class EmptyCartError(OrderError):
	"""Empty cart error"""

	pass


class OrderNotFoundError(OrderError):
	"""Order not found error"""

	pass


class OrderNotCancelableError(OrderError):
	"""Order not cancelable error (not created or paid)"""

	pass


class OrderNotDeliverableError(OrderError):
	"""Order can't transition to DELIVERED (already cancelled)"""

	pass
