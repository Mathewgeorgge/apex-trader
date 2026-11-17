"""
Compatibility Layer for Windows Sandbox and Twisted Network Primitives.
Prevents WinError 10013 when importing KiteConnect / KiteTicker.
"""

# Monkey-patch twisted reactor waker before kiteconnect imports it
try:
    import twisted.internet.posixbase
    twisted.internet.posixbase.PosixReactorBase.installWaker = lambda self: None
except Exception:
    pass
