import strawberry
from django.contrib.auth.models import Group, User
from strawberry.type import StrawberryList

import strawberry_django
from strawberry_django import DjangoModelType
from tests.utils import get_sorted_fields


def test_user_type():
    @strawberry_django.type(User)
    class Type:
        username: strawberry.auto
        email: strawberry.auto
        groups: strawberry.auto

    assert [(f.name, f.type) for f in get_sorted_fields(Type)] == [
        ("username", str),
        ("email", str),
        ("groups", StrawberryList(DjangoModelType)),
    ]


def test_group_type():
    @strawberry_django.type(Group)
    class Type:
        name: strawberry.auto
        users: strawberry.auto = strawberry_django.field(field_name="user_set")

    assert [(f.name, f.type) for f in get_sorted_fields(Type)] == [
        ("name", str),
        ("users", StrawberryList(DjangoModelType)),
    ]
