"""
Custom Exception Classes for Algo Trading System.
"""


class AlgoTradingError(Exception):
    """Base exception for trading engine."""
    pass


class AuthenticationError(AlgoTradingError):
    """Raised when broker login or access token generation fails."""
    pass


class RiskBreachError(AlgoTradingError):
    """Raised when a risk limit (max loss, max trades, circuit breaker) is breached."""
    pass


class OrderExecutionError(AlgoTradingError):
    """Raised when broker order placement fails or is rejected."""
    pass


class MarketClosedError(AlgoTradingError):
    """Raised when an operation requires live market but market is closed."""
    pass
