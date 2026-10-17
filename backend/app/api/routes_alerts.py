from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, SecretStr, StrictBool

from app.api.deps import C
from app.api.errors import ApiError, not_found
from app.delivery.alerts import TelegramError

router = APIRouter(prefix='/api')


@router.get('/alerts')
async def alerts(c: C, before: int | None = Query(default=None, ge=1)):
    return c.alerts.listing(before)


@router.post('/alerts/{alert_id}/acknowledge')
async def acknowledge(alert_id: int, c: C):
    try:
        c.alerts.acknowledge(alert_id)
    except KeyError:
        raise not_found('Alert')
    return {'ok': True}


class TelegramSettings(BaseModel, extra='forbid'):
    bot_token: SecretStr = Field(max_length=150)
    chat_id: str = Field(max_length=19)
    consent: StrictBool


@router.get('/notifications/telegram')
async def telegram_status(c: C):
    return c.alerts.status()


def secure_settings(request: Request):
    # Credentials must not be submitted over a public unencrypted origin.
    origin = request.app.state.auth.origin
    if request.app.state.auth.enabled and not origin.startswith('https://'):
        raise ApiError(400, 'bad_request', 'Telegram setup requires HTTPS on an authenticated deployment.')


@router.post('/notifications/telegram')
async def telegram_configure(body: TelegramSettings, request: Request, c: C):
    secure_settings(request)
    try:
        return await c.alerts.configure(body.bot_token.get_secret_value(), body.chat_id.strip(), body.consent)
    except ValueError as error:
        raise ApiError(400, 'bad_request', str(error))
    except TelegramError:
        raise ApiError(502, 'telegram_unavailable', 'Telegram could not validate this bot and private chat. Check the token, start your bot, and try again.')


@router.post('/notifications/telegram/disable')
async def telegram_disable(c: C):
    return await c.alerts.disable()


@router.post('/notifications/telegram/test')
async def telegram_test(c: C):
    try:
        return await c.alerts.test()
    except ValueError as error:
        raise ApiError(400, 'bad_request', str(error))
    except TelegramError:
        raise ApiError(502, 'telegram_unavailable', 'Test delivery failed. Check your bot and private chat, then retry.')
