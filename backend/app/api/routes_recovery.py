import json
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, StrictStr, ValidationError
from app.api.errors import ApiError

router = APIRouter(prefix='/api')


async def body(request, model):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 8192:
            raise ApiError(413, 'payload_too_large', 'Recovery request is too large.')
    try:
        return model.model_validate(json.loads(data))
    except (ValueError, ValidationError):
        # Never echo submitted passwords or recovery codes in validation responses.
        raise ApiError(422, 'validation_error', 'Check the recovery fields. Passwords must be 12–1024 characters.') from None


def service(request):
    auth = request.app.state.auth
    if not auth.recovery:
        raise ApiError(404, 'not_found', 'Recovery is unavailable in this deployment.')
    bucket = auth.recovery_attempts
    now = time.time()
    while bucket and bucket[0] <= now - 60:
        bucket.popleft()
    if len(bucket) >= 10:
        raise ApiError(429, 'recovery_rate_limited', 'Too many recovery requests. Wait one minute and try again.')
    bucket.append(now)
    return auth.recovery


class Password(BaseModel):
    password: StrictStr = Field(min_length=1, max_length=1024)


class Reset(BaseModel):
    username: StrictStr = Field(min_length=1, max_length=128)
    code: StrictStr = Field(min_length=1, max_length=128)
    password: StrictStr = Field(min_length=12, max_length=1024)


@router.get('/auth/recovery-options')
async def options(request: Request):
    recovery = request.app.state.auth.recovery
    return {'code_available': bool(recovery)}


@router.post('/account/recovery-code')
async def issue_code(request: Request):
    recovery = service(request)
    data = await body(request, Password)
    account_id = request.state.principal['id']
    recovery.verify_password(account_id, data.password)
    return {'code': recovery.issue_code(account_id)}


@router.post('/auth/reset-password')
async def reset(request: Request):
    recovery = service(request)
    data = await body(request, Reset)
    account_id = recovery.reset(data.username, data.code, data.password)
    auth = request.app.state.auth
    for key in list(auth.session_users):
        if auth.session_users[key] == account_id:
            auth.sessions.pop(key, None)
            auth.session_users.pop(key, None)
    return {'ok': True}
