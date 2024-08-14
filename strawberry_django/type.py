import dataclasses
from typing import (
    Callable,
    Generic,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

import strawberry
from django.db.models.base import Model
from strawberry.field import StrawberryField
from strawberry.type import WithStrawberryObjectDefinition
from typing_extensions import Literal, dataclass_transform

from strawberry_django.optimizer import OptimizerStore
from strawberry_django.utils.typing import (
    AnnotateType,
    PrefetchType,
    TypeOrMapping,
    TypeOrSequence,
)

from .fields.field import StrawberryDjangoField
from .fields.field import field as _field
from .type_extension import DjangoTypeExtension

__all__ = ["input", "interface", "partial", "type"]

_T = TypeVar("_T", bound=type)
_O = TypeVar("_O", bound=Type[WithStrawberryObjectDefinition])
_M = TypeVar("_M", bound=Model)


@dataclasses.dataclass
class StrawberryDjangoDefinition(Generic[_O, _M]):
    # TODO: remove
    origin: _O
    model: Type[_M]
    store: OptimizerStore
    is_input: bool = False
    is_partial: bool = False
    is_filter: Union[Literal["lookups"], bool] = False
    filters: Optional[type] = None
    order: Optional[type] = None
    pagination: bool = False
    field_cls: Type[StrawberryDjangoField] = StrawberryDjangoField
    disable_optimization: bool = False


@dataclass_transform(order_default=True, field_specifiers=(StrawberryField, _field))
def type(  # noqa: A001
    model: Type[Model],
    *,
    name: Optional[str] = None,
    field_cls: Type[StrawberryDjangoField] = StrawberryDjangoField,
    is_input: bool = False,
    is_interface: bool = False,
    is_filter: Union[Literal["lookups"], bool] = False,
    partial: bool = False,
    description: Optional[str] = None,
    directives: Optional[Sequence[object]] = (),
    extend: bool = False,
    filters: Optional[type] = None,
    order: Optional[type] = None,
    pagination: bool = False,
    only: Optional[TypeOrSequence[str]] = None,
    select_related: Optional[TypeOrSequence[str]] = None,
    prefetch_related: Optional[TypeOrSequence[PrefetchType]] = None,
    annotate: Optional[TypeOrMapping[AnnotateType]] = None,
    disable_optimization: bool = False,
    fields: Optional[Union[List[str], Literal["__all__"]]] = None,
    exclude: Optional[List[str]] = None,
) -> Callable[[_T], _T]:
    """Annotates a class as a Django GraphQL type.

    Examples
    --------
        It can be used like this:

        >>> @strawberry_django.type(SomeModel)
        ... class X:
        ...     some_field: strawberry.auto
        ...     otherfield: str = strawberry_django.field()

    """
    return strawberry.type(
        name=name,
        is_input=is_input,
        is_interface=is_interface,
        description=description,
        directives=directives,
        extend=extend,
        extension=DjangoTypeExtension(
            model=model,
            name=name,
            field_cls=field_cls,
            is_input=is_input,
            is_partial=partial,
            is_filter=is_filter,
            filters=filters,
            order=order,
            pagination=pagination,
            only=only,
            select_related=select_related,
            prefetch_related=prefetch_related,
            annotate=annotate,
            disable_optimization=disable_optimization,
            fields=fields,
            exclude=exclude,
        ),
    )


@dataclass_transform(order_default=True, field_specifiers=(StrawberryField, _field))
def interface(
    model: Type[Model],
    *,
    name: Optional[str] = None,
    field_cls: Type[StrawberryDjangoField] = StrawberryDjangoField,
    description: Optional[str] = None,
    directives: Optional[Sequence[object]] = (),
    disable_optimization: bool = False,
) -> Callable[[_T], _T]:
    """Annotates a class as a Django GraphQL interface.

    Examples
    --------
        It can be used like this:

        >>> @strawberry_django.interface(SomeModel)
        ... class X:
        ...     some_field: strawberry.auto
        ...     otherfield: str = strawberry_django.field()

    """
    return type(
        model=model,
        name=name,
        field_cls=field_cls,
        is_interface=True,
        description=description,
        directives=directives,
        disable_optimization=disable_optimization,
    )


@dataclass_transform(order_default=True, field_specifiers=(StrawberryField, _field))
def input(  # noqa: A001
    model: Type[Model],
    *,
    name: Optional[str] = None,
    field_cls: Type[StrawberryDjangoField] = StrawberryDjangoField,
    description: Optional[str] = None,
    directives: Optional[Sequence[object]] = (),
    is_filter: Union[Literal["lookups"], bool] = False,
    partial: bool = False,
    fields: Optional[Union[List[str], Literal["__all__"]]] = None,
    exclude: Optional[List[str]] = None,
) -> Callable[[_T], _T]:
    """Annotates a class as a Django GraphQL input.

    Examples
    --------
        It can be used like this:

        >>> @strawberry_django.input(SomeModel)
        ... class X:
        ...     some_field: strawberry.auto
        ...     otherfield: str = strawberry_django.field()

    """
    return type(
        model=model,
        name=name,
        field_cls=field_cls,
        is_input=True,
        description=description,
        directives=directives,
        is_filter=is_filter,
        partial=partial,
        fields=fields,
        exclude=exclude,
    )


@dataclass_transform(order_default=True, field_specifiers=(StrawberryField, _field))
def partial(
    model: Type[Model],
    *,
    name: Optional[str] = None,
    field_cls: Type[StrawberryDjangoField] = StrawberryDjangoField,
    description: Optional[str] = None,
    directives: Optional[Sequence[object]] = (),
    fields: Optional[Union[List[str], Literal["__all__"]]] = None,
    exclude: Optional[List[str]] = None,
) -> Callable[[_T], _T]:
    """Annotates a class as a Django GraphQL partial.

    Examples
    --------
        It can be used like this:

        >>> @strawberry_django.partial(SomeModel)
        ... class X:
        ...     some_field: strawberry.auto
        ...     otherfield: str = strawberry_django.field()

    """
    return type(
        model=model,
        name=name,
        field_cls=field_cls,
        is_input=True,
        description=description,
        directives=directives,
        partial=True,
        fields=fields,
        exclude=exclude,
    )
