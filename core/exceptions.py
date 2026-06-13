class DependencyMissing(Exception):
    """Raised when a required third-party library is not installed."""
    pass

class UnauthorizedException(Exception):
    """Raised when trying to do something you're not authorized to do"""
    pass
