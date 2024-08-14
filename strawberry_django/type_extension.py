from __future__ import annotations

import dataclasses
import functools
import inspect
import sys
import types
from typing import TYPE_CHECKING, Any, ClassVar, Collection, Iterator, Optional, cast

import strawberry
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey
from django.db.models.base import Model
from django.db.models.fields.reverse_related import ManyToManyRel, ManyToOneRel
from strawberry import UNSET, relay
from strawberry.annotation import StrawberryAnnotation
from strawberry.exceptions import (
    MissingFieldAnnotationError,
)
from strawberry.field import StrawberryField
from strawberry.private import is_private
from strawberry.types.type_extension import TypeExtension
from strawberry.types.types import StrawberryObjectDefinition
from strawberry.utils.str_converters import to_camel_case
from typing_extensions import Literal, Protocol, Self

from strawberry_django.optimizer import OptimizerStore
from strawberry_django.relay import (
    resolve_model_id,
    resolve_model_id_attr,
    resolve_model_node,
    resolve_model_nodes,
)
from strawberry_django.utils.typing import (
    AnnotateType,
    PrefetchType,
    TypeOrMapping,
    TypeOrSequence,
    is_auto,
)

from .descriptors import ModelProperty
from .fields.field import StrawberryDjangoField
from .fields.types import get_model_field, resolve_model_field_name
from .settings import strawberry_django_settings as django_settings

if TYPE_CHECKING:
    from django.db.models import Model

    from strawberry_django.utils.typing import (
        AnnotateType,
        PrefetchType,
        TypeOrMapping,
        TypeOrSequence,
    )


class WithStrawberryDjangoObjectDefinition(Protocol):
    __strawberry_definition__: ClassVar[DjangoObjectDefinition]


@dataclasses.dataclass(eq=False)
class DjangoObjectDefinition(StrawberryObjectDefinition):
    # Older python does not have KW_ONLY dataclass concept - using UNSET
    model: type[Model] = strawberry.UNSET
    store: OptimizerStore = strawberry.UNSET
    is_partial: bool = False
    is_filter: Literal["lookups"] | bool = False
    filters: type[WithStrawberryDjangoObjectDefinition] | None = None
    order: type[WithStrawberryDjangoObjectDefinition] | None = None
    pagination: bool = False
    field_cls: type[StrawberryDjangoField] = StrawberryDjangoField
    disable_optimization: bool = False


class DjangoTypeExtension(TypeExtension):
    def __init__(
        self,
        model: type[Model],
        name: str | None = None,
        field_cls: type[StrawberryDjangoField] = StrawberryDjangoField,
        is_input: bool = False,
        is_partial: bool = False,
        is_filter: Literal["lookups"] | bool = False,
        filters: type[WithStrawberryDjangoObjectDefinition] | None = None,
        order: type[WithStrawberryDjangoObjectDefinition] | None = None,
        pagination: bool = False,
        only: TypeOrSequence[str] | None = None,
        select_related: TypeOrSequence[str] | None = None,
        prefetch_related: TypeOrSequence[PrefetchType] | None = None,
        annotate: TypeOrMapping[AnnotateType] | None = None,
        disable_optimization: bool = False,
        fields: list[str] | Literal["__all__"] | None = None,
        exclude: list[str] | None = None,
    ):
        if fields == "__all__":
            names = [f.name for f in model._meta.fields]
        elif isinstance(fields, Collection):
            names = [f.name for f in model._meta.fields if f.name in fields]
        elif isinstance(exclude, Collection) and len(exclude) > 0:
            names = [f.name for f in model._meta.fields if f.name not in exclude]
        else:
            names = []

        if django_settings()["MAP_AUTO_ID_AS_GLOBAL_ID"] and "id" in names:
            names.remove("id")

        self._model_field_names = names
        self._name = name
        self._origin: type = strawberry.UNSET
        self._use_fields_description = django_settings()[
            "FIELD_DESCRIPTION_FROM_HELP_TEXT"
        ]

        self.is_input = is_input
        self.model = model
        self.is_filter = is_filter
        self.is_partial = is_partial
        self.field_cls = field_cls
        self.filters = filters
        self.order = order
        self.pagination = pagination
        self.store = OptimizerStore.with_hints(
            only=only,
            select_related=select_related,
            prefetch_related=prefetch_related,
            annotate=annotate,
        )
        self.disable_optimization = disable_optimization

    def on_wrap_dataclass(self, cls: type[Any]) -> Iterator[None]:
        self._origin = cls
        self._name = self._name or to_camel_case(cls.__name__)

        cls_annotations = cls.__dict__.get("__annotations__", {})
        cls.__annotations__ = cls_annotations

        for name in self._model_field_names:
            if name in cls_annotations or hasattr(cls, name):
                continue
            cls_annotations[name] = strawberry.auto

        if self.is_filter:
            cls_annotations.update(
                {
                    "AND": Optional[Self],
                    "OR": Optional[Self],
                    "NOT": Optional[Self],
                    "DISTINCT": Optional[bool],
                },
            )

        yield

        if not issubclass(cls, relay.Node):
            return

        for attr, func in [
            ("resolve_id", resolve_model_id),
            ("resolve_id_attr", resolve_model_id_attr),
            ("resolve_node", resolve_model_node),
            ("resolve_nodes", resolve_model_nodes),
        ]:
            existing_resolver = getattr(cls, attr, None)
            if (
                existing_resolver is None
                or existing_resolver.__func__ is getattr(relay.Node, attr).__func__
            ):
                setattr(cls, attr, types.MethodType(func, cls))

            # Adjust types that inherit from other types/interfaces that implement Node
            # to make sure they pass themselves as the node type
            meth = getattr(cls, attr)
            if isinstance(meth, types.MethodType) and meth.__self__ is not cls:
                setattr(
                    cls, attr, types.MethodType(cast(classmethod, meth).__func__, cls)
                )

    def create_object_definition(
        self, *args: Any, origin: type, **kwargs: Any
    ) -> DjangoObjectDefinition:
        kwargs["is_type_of"] = lambda obj, info: isinstance(obj, (origin, self.model))
        if (
            django_settings()["TYPE_DESCRIPTION_FROM_MODEL_DOCSTRING"]
            and kwargs.get("description", None) is None
            and self.model.__doc__
        ):
            kwargs["description"] = inspect.cleandoc(self.model.__doc__)

        return DjangoObjectDefinition(
            *args,
            origin=origin,
            model=self.model,
            store=self.store,
            is_partial=self.is_partial,
            is_filter=self.is_filter,
            filters=self.filters,
            order=self.order,
            pagination=self.pagination,
            field_cls=self.field_cls,
            disable_optimization=self.disable_optimization,
            **kwargs,
        )

    def _get_model_attrs(
        self, field: dataclasses.Field[Any] | StrawberryField
    ) -> dict[str, Any]:
        from strawberry_django.fields.types import is_optional, resolve_model_field_type

        python_name: str = getattr(field, "python_name", field.name)
        model_name = getattr(field, "django_name", None) or python_name
        description: str | None = getattr(field, "description", None)

        try:
            model_attr = get_model_field(self.model, model_name)
        except FieldDoesNotExist as e:
            model_attr = getattr(self.model, model_name, None)
            if not model_attr:
                raise

            is_relation = False

            if isinstance(model_attr, ModelProperty):
                type_annotation = StrawberryAnnotation(
                    model_attr.type_annotation,
                    namespace=sys.modules[model_attr.func.__module__].__dict__,
                )

                if description is None and self._use_fields_description:
                    description = model_attr.description
            elif isinstance(model_attr, (property, functools.cached_property)):
                func = (
                    model_attr.fget
                    if isinstance(model_attr, property)
                    else model_attr.func
                )

                return_type = func.__annotations__.get("return")
                if return_type is None:
                    raise MissingFieldAnnotationError(model_name, self._origin) from e
                type_annotation = StrawberryAnnotation(
                    return_type, namespace=sys.modules[func.__module__].__dict__
                )

                if (
                    description is None
                    and func.__doc__
                    and self._use_fields_description
                ):
                    description = inspect.cleandoc(func.__doc__)
            else:
                raise
        else:
            is_relation = model_attr.is_relation
            is_fk_id = python_name.endswith("_id") and isinstance(
                model_attr, ForeignKey
            )

            resolved_type = resolve_model_field_type(
                model_attr.target_field if is_fk_id else model_attr, self
            )
            if is_optional(model_attr, self.is_input, self.is_partial):
                resolved_type = Optional[resolved_type]
            type_annotation = StrawberryAnnotation(resolved_type)

            if description is None and self._use_fields_description:
                try:
                    from django.contrib.contenttypes.fields import (
                        GenericForeignKey,
                        GenericRel,
                    )
                except (ImportError, RuntimeError):  # pragma: no cover
                    GenericForeignKey = None  # noqa: N806
                    GenericRel = None  # noqa: N806

                if (
                    GenericForeignKey is not None
                    and GenericRel is not None
                    and isinstance(model_attr, (GenericRel, GenericForeignKey))
                ):
                    f_description = None
                elif isinstance(model_attr, (ManyToOneRel, ManyToManyRel)):
                    f_description = model_attr.field.help_text
                else:
                    f_description = getattr(model_attr, "help_text", None)

                if f_description:
                    description = str(f_description)

            model_name = getattr(
                field,
                "django_name",
                resolve_model_field_name(
                    model_attr,
                    is_input=self.is_input,
                    is_filter=bool(self.is_filter),
                    is_fk_id=is_fk_id,
                ),
            )

        return {
            "django_name": model_name,
            "type_annotation": type_annotation,
            "description": description,
            "is_relation": is_relation,
        }

    def on_field(self, field: dataclasses.Field[Any] | StrawberryField) -> Any:
        # TODO: for auto fields It _might_ be good optimization
        #  to copy field def from parent if available?
        # origin etc. would have to be changed
        if getattr(field, "origin", None):
            ...
            # THis most likely means that field is from parent and has resolver?

        type_ = field.type
        if is_private(type_):
            # TODO: is_private ignores if type is str (__future__ annotations)
            return field

        attrs = {
            "type_annotation": getattr(
                field, "type_annotation", StrawberryAnnotation(type_)
            )
        }
        if is_auto(type_):
            attrs = self._get_model_attrs(field)

        if isinstance(field, StrawberryDjangoField):
            for attr, value in attrs.items():
                setattr(field, attr, value)
        elif isinstance(field, StrawberryField) and field.base_resolver is not None:
            # If this is not a StrawberryDjangoField, but has a base_resolver, no need
            # avoid forcing it to be a StrawberryDjangoField
            return field
        else:
            field = self.field_cls(
                default=getattr(field, "default", dataclasses.MISSING),
                default_factory=getattr(field, "default_factory", dataclasses.MISSING),
                python_name=getattr(field, "python_name", field.name),
                graphql_name=getattr(field, "graphql_name", None),
                is_subscription=getattr(field, "is_subscription", False),
                base_resolver=getattr(field, "base_resolver", None),
                permission_classes=getattr(field, "permission_classes", ()),
                deprecation_reason=getattr(field, "deprecation_reason", None),
                origin=getattr(field, "origin", None),
                directives=getattr(field, "directives", ()),
                pagination=getattr(field, "pagination", UNSET),
                filters=getattr(field, "filters", UNSET),
                order=getattr(field, "order", UNSET),
                extensions=getattr(field, "extensions", ()),
                **attrs,
            )

        if (
            self.is_input
            and field.default == dataclasses.MISSING
            and field.default_value == dataclasses.MISSING
        ):
            field.default = field.default_value = UNSET

        return field
