import time

import strawberry

import strawberry_django
from tests.models import Fruit

_NUM = 15_000


def do():
    types: list[type] = []

    for i in range(_NUM):

        @strawberry_django.type(Fruit, fields="__all__", name=f"C{i}")
        class C: ...

        types.append(C)

    @strawberry.type
    class Query:
        test: str = "SOMETHING"

    strawberry.Schema(Query, types=types)


def test_perf():
    t0 = time.time()
    do()
    t1 = time.time()
    print(f"Took {t1 - t0}")

    assert False
