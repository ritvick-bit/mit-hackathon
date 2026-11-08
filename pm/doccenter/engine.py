"""Shim for Yichang's document center: the only thing it needs from eqore-demo's engine is DomainError."""


class DomainError(Exception):
    pass
