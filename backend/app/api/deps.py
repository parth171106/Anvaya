from typing import Annotated

from fastapi import Depends, Request

from app.core.container import Container


async def _c(request: Request) -> Container:
    if request.app.state.auth.accounts:
        principal = request.state.principal
        return request.app.state.workspaces.get(principal["id"])
    return request.app.state.c


C = Annotated[Container, Depends(_c)]
