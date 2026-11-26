"""Abstract base storage backend interface."""

from abc import ABC, abstractmethod
from typing import Any, Sequence


class BaseStorage(ABC):
    """Contract for streaming extracted records into analytical storage."""

    @abstractmethod
    async def write(self, record: Any) -> None:
        """Write single record (dict or Pydantic model)."""
        pass

    @abstractmethod
    async def write_batch(self, records: Sequence[Any]) -> None:
        """Write batch of records."""
        pass

    @abstractmethod
    async def flush(self) -> None:
        """Ensure all buffered records are written."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close database connections."""
        pass
