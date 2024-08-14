from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

import django
from django.db.models import ForeignKey
from strawberry import LazyType, relay
from strawberry.annotation import StrawberryAnnotation
from strawberry.auto import StrawberryAuto
from strawberry.field import UNRESOLVED, StrawberryField
from strawberry.type import (
    StrawberryContainer,
    StrawberryList,
    StrawberryOptional,
    StrawberryType,
    WithStrawberryObjectDefinition,
    get_object_definition,
)
from strawberry.union import StrawberryUnion
from strawberry.utils.inspect import get_specialized_type_var_map

from strawberry_django.resolvers import django_resolver
from strawberry_django.utils.typing import (
    WithStrawberryDjangoObjectDefinition,
    has_django_definition,
    unwrap_type,
)

if TYPE_CHECKING:
    from django.db import models
    from strawberry.object_type import StrawberryObjectDefinition
    from strawberry.types import Info
    from typing_extensions import Literal, Self

    from strawberry_django.type_extension import (
        DjangoObjectDefinition,
        WithStrawberryDjangoObjectDefinition,
    )

_QS = TypeVar("_QS", bound="models.QuerySet")

if django.VERSION >= (5, 0):
    from django.db.models import GeneratedField  # type: ignore
else:
    GeneratedField = None


class StrawberryDjangoFieldBase(StrawberryField):
    def __init__(
        self, django_name: str | None = None, is_relation: bool = False, **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.django_name = django_name
        self.is_relation = is_relation

        self._django_definition: DjangoObjectDefinition | None = None

    def __copy__(self) -> Self:
        new_field = super().__copy__()
        new_field.django_name = self.django_name
        new_field.is_relation = self.is_relation

        new_field._django_definition = self._django_definition
        return new_field

    @property
    def is_basic_field(self) -> bool:
        """Mark this field as not basic.

        All StrawberryDjango fields define a custom resolver that needs to be
        run, so always return False here.
        """
        return False

    @functools.cached_property
    def is_async(self) -> bool:
        # Our default resolver is sync by default but will return a coroutine
        # when running ASGI. If we happen to have an extension that only supports
        # async, make sure we mark the field as async as well to support resolving
        # it properly.
        return super().is_async or any(
            e.supports_async and not e.supports_sync for e in self.extensions
        )

    @functools.cached_property
    def django_type(self) -> type[WithStrawberryDjangoObjectDefinition] | None:
        origin = self.type

        if isinstance(origin, LazyType):
            origin = origin.resolve_type()

        object_definition = get_object_definition(origin)

        if object_definition and issubclass(object_definition.origin, relay.Connection):
            origin_specialized_type_var_map = (
                get_specialized_type_var_map(cast(type, origin)) or {}
            )
            origin = origin_specialized_type_var_map.get("NodeType")

            if origin is None:
                origin = object_definition.type_var_map.get("NodeType")

            if origin is None:
                specialized_type_var_map = (
                    object_definition.specialized_type_var_map or {}
                )
                origin = specialized_type_var_map["NodeType"]

            if isinstance(origin, LazyType):
                origin = origin.resolve_type()

        origin = unwrap_type(origin)
        if isinstance(origin, LazyType):
            origin = origin.resolve_type()

        if isinstance(origin, StrawberryUnion):
            origin_list: list[type[WithStrawberryDjangoObjectDefinition]] = []
            for t in origin.types:
                while isinstance(t, StrawberryContainer):
                    t = t.of_type  # noqa: PLW2901

                if has_django_definition(t):
                    origin_list.append(t)

            origin = origin_list[0] if len(origin_list) == 1 else None

        return origin if has_django_definition(origin) else None

    @functools.cached_property
    def django_model(self) -> type[models.Model] | None:
        django_type = self.django_type
        return (
            django_type.__strawberry_django_definition__.model
            if django_type is not None
            else None
        )

    @functools.cached_property
    def is_optional(self) -> bool:
        return isinstance(self.type, StrawberryOptional)

    @functools.cached_property
    def is_list(self) -> bool:
        type_ = self.type
        if isinstance(type_, StrawberryOptional):
            type_ = type_.of_type

        return isinstance(type_, StrawberryList)

    @functools.cached_property
    def is_connection(self) -> bool:
        type_ = self.type
        if isinstance(type_, StrawberryOptional):
            type_ = type_.of_type

        return isinstance(type_, type) and issubclass(type_, relay.Connection)

    @functools.cached_property
    def safe_resolver(self):
        resolver = self.base_resolver
        assert resolver

        if not resolver.is_async:
            resolver = django_resolver(resolver, qs_hook=None)

        return resolver

    @property
    def django_definition(self) -> DjangoObjectDefinition | None:
        from strawberry_django.type_extension import DjangoObjectDefinition

        if self._django_definition:
            return self._django_definition

        if (def_ := get_object_definition(self.origin)) and isinstance(
            def_, DjangoObjectDefinition
        ):
            self._django_definition = def_
            return def_

        return None

    def resolve_type(
        self,
        *,
        type_definition: StrawberryObjectDefinition | None = None,
    ) -> (
        StrawberryType | type[WithStrawberryObjectDefinition] | Literal[UNRESOLVED]  # type: ignore
    ):
        resolved = super().resolve_type(type_definition=type_definition)
        if resolved is UNRESOLVED or not (django_def := self.django_definition):
            # print(self.name, self.origin)
            # None origin -> Field has not yet been processed via type extension
            return resolved

        unwraped = unwrap_type(resolved)
        # FIXME: Why does this come as Any sometimes when using future annotations?

        # TODO: ? If the resolved type is an input but the origin is not, or vice versa,
        # resolve this again
        if unwraped is Any or isinstance(unwraped, StrawberryAuto):
            from .types import get_model_field, is_optional, resolve_model_field_type

            # print(self.python_name, resolved, self)

            model_field = get_model_field(
                django_def.model,
                self.django_name or self.python_name or self.name,
            )
            resolved_type = resolve_model_field_type(
                (
                    model_field.target_field
                    if (
                        self.python_name.endswith("_id")
                        and isinstance(model_field, ForeignKey)
                    )
                    else model_field
                ),
                django_def,
            )
            if is_optional(model_field, django_def.is_input, django_def.is_partial):
                resolved_type = Optional[resolved_type]

            self.type_annotation = StrawberryAnnotation(resolved_type)
            resolved = super().type

        if isinstance(resolved, StrawberryAuto):
            resolved = UNRESOLVED

        return resolved

    def resolver(
        self,
        source: Any,
        info: Info | None,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        return self.safe_resolver(*args, **kwargs)

    def get_result(self, source, info, args, kwargs):
        return self.resolver(info, source, args, kwargs)

    def get_queryset(self, queryset: _QS, info: Info, **kwargs) -> _QS:
        return queryset
