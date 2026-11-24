import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import ssl
import time
from email.errors import MessageError
from email.headerregistry import Address
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from open_webui.config import ENABLE_PASSWORD_AUTH
from open_webui.env import WEBUI_AUTH, WEBUI_AUTH_TRUSTED_EMAIL_HEADER
from open_webui.events import EVENTS, publish_event
from open_webui.internal.db import get_async_db, get_async_session
from open_webui.models.auths import Auths, MfaData, PasswordResetTicket
from open_webui.models.config import Config
from open_webui.models.users import Users
from open_webui.routers.mfa import MfaRoute
from open_webui.utils.auth import get_password_hash, validate_password
from open_webui.utils.rate_limit import RateLimiter
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(route_class=MfaRoute)
log = logging.getLogger(__name__)
ip_limit = RateLimiter(limit=30, window=900)
email_limit = RateLimiter(limit=1, window=60)
INVALID_CODE = 'Invalid or expired reset code.'


def enabled(login_form: bool) -> bool:
    password = os.getenv('PASSWORD_RESET_SMTP_PASSWORD', '').strip()
    return bool(
        WEBUI_AUTH
        and ENABLE_PASSWORD_AUTH
        and not WEBUI_AUTH_TRUSTED_EMAIL_HEADER
        and login_form
        and password
        and password != 're_xxxxxx'
    )


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetConfirm(ResetRequest):
    reset_token: SecretStr = Field(min_length=1, max_length=64)
    new_password: SecretStr = Field(min_length=1, max_length=1024)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def check_access(request: Request, action: str):
    if not enabled(await Config.get('ui.enable_login_form')):
        raise HTTPException(403, 'Email password reset is disabled.')
    ip = request.client.host if request.client else 'unknown'
    if await ip_limit.is_limited(request.app.state.redis, f'pwreset:{action}:{digest(ip)}'):
        raise HTTPException(429, 'Too many attempts. Please try again later.')


async def local_account(email, db):
    user = await Users.get_user_by_email(email, db=db)
    if not user or user.oauth or user.scim:
        return None, None
    auth = await Auths.get_auth_by_id(user.id, db=db)
    # LDAP-only rows have a UUID placeholder rather than a local password hash.
    if not auth or not auth.active or auth.email.lower() != email or not auth.password.startswith(('$2', '$argon2')):
        return None, None
    return user, auth


def send_code(email: str, token: str):
    message = EmailMessage()
    message['From'] = Address(
        os.getenv('PASSWORD_RESET_SMTP_NAME', 'Chat'),
        addr_spec=os.getenv('PASSWORD_RESET_SMTP_FROM', 'no-replay@9991565.xyz'),
    )
    message['To'] = Address(addr_spec=email)
    message['Subject'] = '密码重置 / Password reset'
    message.set_content(
        f'密码重置码 / Password reset code:\n\n{token}\n\n'
        '15 分钟内有效。如非本人申请，请忽略本邮件。\n'
        'Expires in 15 minutes. If you did not request this, ignore this email.'
    )
    with smtplib.SMTP_SSL(
        os.getenv('PASSWORD_RESET_SMTP_HOST', 'smtp.resend.com'),
        int(os.getenv('PASSWORD_RESET_SMTP_PORT', '465')),
        timeout=10,
        context=ssl.create_default_context(),
    ) as smtp:
        smtp.login(os.getenv('PASSWORD_RESET_SMTP_USERNAME', 'resend'), os.environ['PASSWORD_RESET_SMTP_PASSWORD'])
        smtp.send_message(message, to_addrs=[email])


async def issue_code(email: str):
    async with get_async_db() as db:
        _, auth = await local_account(email, db)
        if not auth:
            return
        state = auth.mfa.model_copy(deep=True) if auth.mfa else MfaData()
        token = secrets.token_hex(12)
        state.password_reset = PasswordResetTicket(
            email=email, token_hash=digest(token), expires_at=int(time.time()) + 900
        )
        if not await Auths.update_mfa_by_id(auth, state, db=db):
            return
        await db.commit()
    try:
        await asyncio.to_thread(send_code, email, token)
    except Exception as error:
        # SMTP exceptions can include recipient or payload; log only the class.
        log.error('Password reset mail delivery failed (%s)', type(error).__name__)


@router.post('/request', status_code=202)
async def request_code(form: ResetRequest, request: Request, tasks: BackgroundTasks):
    await check_access(request, 'request')
    email = form.email.strip().lower()
    try:
        address = Address(addr_spec=email)
        if not address.domain or address.addr_spec != email or not email.isascii():
            raise ValueError
    except (ValueError, MessageError):
        raise HTTPException(400, 'Invalid email address.') from None
    if not await email_limit.is_limited(request.app.state.redis, 'pwreset:email:' + digest(email)):
        tasks.add_task(issue_code, email)
    return True


@router.post('/confirm')
async def confirm(form: ResetConfirm, request: Request, db: AsyncSession = Depends(get_async_session)):
    await check_access(request, 'confirm')
    email = form.email.strip().lower()
    user, auth = await local_account(email, db)
    ticket = auth.mfa.password_reset if auth and auth.mfa else None
    if (
        not ticket
        or ticket.email != email
        or ticket.expires_at <= time.time()
        or not hmac.compare_digest(ticket.token_hash, digest(form.reset_token.get_secret_value().strip()))
    ):
        raise HTTPException(400, INVALID_CODE)
    password = form.new_password.get_secret_value()
    try:
        validate_password(password)
    except Exception as error:
        raise HTTPException(400, str(error)) from None
    try:
        await Auths.update_user_password_by_id(user.id, await get_password_hash(password), current_auth=auth, db=db)
    except ValueError:
        raise HTTPException(409, INVALID_CODE) from None
    from open_webui.socket.main import disconnect_user_sessions

    await disconnect_user_sessions(user.id)
    await publish_event(request, EVENTS.AUTH_PASSWORD_CHANGED, actor=user, subject_id=user.id, subject_type='user')
    return True
