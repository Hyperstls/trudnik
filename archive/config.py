import warnings

from app.config import Config

warnings.warn(
    "Root config.py is deprecated. Import from app.config instead.",
    DeprecationWarning,
    stacklevel=2,
)