from __future__ import annotations

import dataclasses
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    TypeVar,
    Union,
    _AnnotatedAlias,  # type: ignore
    cast,
    get_args,
    overload,
)

from django.db.models.expressions import BaseExpression, Combinable
from graphql.type.definition import GraphQLResolveInfo
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.auto import StrawberryAuto
from strawberry.types.base import (
    StrawberryContainer,
    StrawberryType,
    WithStrawberryObjectDefinition,
)
from strawberry.types.lazy_type import LazyType, StrawberryLazyReference
from strawberry.utils.typing import is_classvar
from typing_extensions import Protocol

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Prefetch
    from typing_extensions import Literal, TypeAlias, TypeGuard

    from strawberry_django.type import StrawberryDjangoDefinition

_T = TypeVar("_T")
_Type = TypeVar("_Type", bound="StrawberryType | type")

TypeOrSequence: TypeAlias = Union[_T, Sequence[_T]]
TypeOrMapping: TypeAlias = Union[_T, Mapping[str, _T]]
TypeOrIterable: TypeAlias = Union[_T, Iterable[_T]]
UserType: TypeAlias = Union["AbstractBaseUser", "AnonymousUser"]
PrefetchCallable: TypeAlias = Callable[[GraphQLResolveInfo], "Prefetch[Any]"]
PrefetchType: TypeAlias = Union[str, "Prefetch[Any]", PrefetchCallable]
AnnotateCallable: TypeAlias = Callable[
    [GraphQLResolveInfo],
    Union[BaseExpression, Combinable],
]
AnnotateType: TypeAlias = Union[BaseExpression, Combinable, AnnotateCallable]


class WithStrawberryDjangoObjectDefinition(WithStrawberryObjectDefinition, Protocol):
    __strawberry_django_definition__: ClassVar[StrawberryDjangoDefinition]


def has_django_definition(
    obj: Any,
) -> TypeGuard[type[WithStrawberryDjangoObjectDefinition]]:
    return hasattr(obj, "__strawberry_django_definition__")


@overload
def get_django_definition(
    obj: Any,
    *,
    strict: Literal[True],
) -> StrawberryDjangoDefinition: ...


@overload
def get_django_definition(
    obj: Any,
    *,
    strict: bool = False,
) -> StrawberryDjangoDefinition | None: ...


def get_django_definition(
    obj: Any,
    *,
    strict: bool = False,
) -> StrawberryDjangoDefinition | None:
    return (
        obj.__strawberry_django_definition__
        if strict
        else getattr(obj, "__strawberry_django_definition__", None)
    )


def is_auto(obj: Any) -> bool:
    if isinstance(obj, str):
        return obj in {"auto", "strawberry.auto"}

    return isinstance(obj, StrawberryAuto)


def get_annotations(cls) -> dict[str, StrawberryAnnotation]:
    annotations: dict[str, StrawberryAnnotation] = {}

    for c in reversed(cls.__mro__):
        # Skip non dataclass bases other than cls itself
        if c is not cls and not dataclasses.is_dataclass(c):
            continue

        namespace = sys.modules[c.__module__].__dict__
        for k, v in getattr(c, "__annotations__", {}).items():
            if not is_classvar(cast("type", c), v):
                annotations[k] = StrawberryAnnotation(v, namespace=namespace)

    return annotations


@overload
def unwrap_type(type_: StrawberryContainer) -> type: ...


@overload
def unwrap_type(type_: LazyType) -> type: ...


@overload
def unwrap_type(type_: None) -> None: ...


@overload
def unwrap_type(type_: _Type) -> _Type: ...


def unwrap_type(type_):
    while True:
        if isinstance(type_, LazyType):
            type_ = type_.resolve_type()
        elif isinstance(type_, StrawberryContainer):
            type_ = type_.of_type
        else:
            break

    return type_


def get_type_from_lazy_annotation(type_: _AnnotatedAlias) -> type | None:
    first, *rest = get_args(type_)
    for arg in rest:
        if isinstance(arg, StrawberryLazyReference):
            return unwrap_type(arg.resolve_forward_ref(first))

    return None
