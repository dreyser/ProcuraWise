from typing import Any

from pymongo.collection import Collection
from pymongo.cursor import Cursor
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult


class TenantScopeError(ValueError):
    """Raised when an operation would read, write, or move a document across
    a tenant boundary. Always signals a bug in calling code: once every write
    schema rejects unknown fields (extra="forbid", see shared/api_models.py),
    a client can never make tenant_id reach this layer in the first place."""


class TenantCollection:
    """Wraps a single pymongo Collection scoped to one resolved tenant_id.

    Every method injects/merges {"tenant_id": tenant_id} so a caller cannot
    forget it, and rejects any attempt - via filter, insert document, or
    update - to read or write a different tenant_id. The underlying
    `Collection` is never exposed (no passthrough, no raw accessor): a
    repository that needs an operation not covered here must have it added
    to this class explicitly, reviewed for tenant safety, rather than reach
    around it.
    """

    def __init__(self, collection: Collection, tenant_id: str) -> None:
        self._collection = collection
        self._tenant_id = tenant_id

    def find_one(
        self, filter_: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        scoped = self._scoped_filter(filter_)
        result: dict[str, Any] | None = self._collection.find_one(scoped, **kwargs)
        return result

    def find(self, filter_: dict[str, Any] | None = None, **kwargs: Any) -> Cursor:
        return self._collection.find(self._scoped_filter(filter_), **kwargs)

    def count_documents(self, filter_: dict[str, Any] | None = None, **kwargs: Any) -> int:
        return self._collection.count_documents(self._scoped_filter(filter_), **kwargs)

    def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
        return self._collection.insert_one(self._forced_tenant_document(document))

    def update_one(
        self, filter_: dict[str, Any], update: dict[str, Any], **kwargs: Any
    ) -> UpdateResult:
        """Accepts either an operator update (e.g. {"$set": {...}}), applied
        via `Collection.update_one`, or a full replacement document (e.g.
        {"name": "z"}, no "$" keys), applied via `Collection.replace_one` -
        PyMongo rejects a plain document passed to `update_one` outright, so
        the two shapes cannot share a driver call. A document mixing "$"
        operators with plain fields is ambiguous and rejected before either
        path runs."""
        has_operator_keys = any(key.startswith("$") for key in update)
        has_plain_keys = any(not key.startswith("$") for key in update)
        if has_operator_keys and has_plain_keys:
            raise TenantScopeError("update must not mix $ operators with plain fields")

        scoped_filter = self._scoped_filter(filter_)
        if has_operator_keys:
            safe_update = self._rejecting_tenant_mutation(update)
            return self._collection.update_one(scoped_filter, safe_update, **kwargs)

        replacement = self._forced_tenant_document(update)
        return self._collection.replace_one(scoped_filter, replacement, **kwargs)

    def delete_one(self, filter_: dict[str, Any], **kwargs: Any) -> DeleteResult:
        return self._collection.delete_one(self._scoped_filter(filter_), **kwargs)

    def _scoped_filter(self, filter_: dict[str, Any] | None) -> dict[str, Any]:
        scoped = dict(filter_ or {})
        existing = scoped.get("tenant_id")
        if existing is not None and existing != self._tenant_id:
            raise TenantScopeError(
                f"filter tenant_id={existing!r} does not match resolved tenant {self._tenant_id!r}"
            )
        scoped["tenant_id"] = self._tenant_id
        return scoped

    def _forced_tenant_document(self, document: dict[str, Any]) -> dict[str, Any]:
        doc = dict(document)
        existing = doc.get("tenant_id")
        if existing is not None and existing != self._tenant_id:
            raise TenantScopeError(
                f"document tenant_id={existing!r} does not match resolved tenant "
                f"{self._tenant_id!r}"
            )
        doc["tenant_id"] = self._tenant_id
        return doc

    def _rejecting_tenant_mutation(self, update: dict[str, Any]) -> dict[str, Any]:
        if "tenant_id" in update.get("$set", {}):
            raise TenantScopeError("$set must not modify tenant_id")
        if "tenant_id" in update.get("$setOnInsert", {}):
            raise TenantScopeError("$setOnInsert must not modify tenant_id")
        if "tenant_id" in update.get("$unset", {}):
            raise TenantScopeError("$unset must not remove tenant_id")
        return update
