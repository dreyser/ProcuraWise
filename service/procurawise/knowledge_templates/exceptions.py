class KnowledgeTemplateNotFoundError(Exception):
    """No KnowledgeTemplate exists for this id within the caller's tenant."""


class TemplateItemNotFoundError(Exception):
    """No item exists for this id within the given KnowledgeTemplate."""
