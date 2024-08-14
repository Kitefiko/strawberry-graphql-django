from django.db import models
from strawberry import auto

import strawberry_django
from tests.utils import get_sorted_fields


def test_forward_reference():
    global MyBytes

    class ForwardReferenceModel(models.Model):
        string = models.CharField(max_length=50)

    @strawberry_django.type(ForwardReferenceModel)
    class Type:
        bytes0: "MyBytes"
        string: auto

    class MyBytes(bytes):
        pass

    assert [(f.name, f.type) for f in get_sorted_fields(Type)] == [
        ("bytes0", MyBytes),
        ("string", str),
    ]

    del MyBytes
