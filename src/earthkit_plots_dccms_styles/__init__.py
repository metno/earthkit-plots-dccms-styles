
try:
    from ._version import __version__
except ImportError:  # pragma: no cover
    # Local copy or not installed with setuptools
    __version__ = "999"