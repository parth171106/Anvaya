from typing import Annotated

from fastapi import Depends, Request

from app.core.container import Container


def _c(request: Request) -> Container:
    return request.app.state.c


C = Annotated[Container, Depends(_c)]
