"""Run directly with the backend dependencies installed. No live mail or deployment DB."""

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class PasswordResetTest(unittest.IsolatedAsyncioTestCase):
    async def test_password_reset(self):
        if __name__ != '__main__':
            # Import-time backend settings must not pick up a runner's deployment database.
            subprocess.run([sys.executable, __file__], check=True)
            return
        import httpx
        from fastapi import FastAPI
        from open_webui.internal.db import Base, async_engine, engine, get_async_db
        from open_webui.models.auths import Auth, Auths, MfaData
        from open_webui.models.users import User
        from open_webui.routers import password_reset as reset
        from open_webui.utils.auth import get_password_hash, verify_password

        with patch.object(reset.smtplib, 'SMTP_SSL') as transport:
            reset.send_code('owner@example.com', 'test-code')
            self.assertEqual(transport.call_args.args, ('smtp.resend.com', 465))
            self.assertTrue(transport.call_args.kwargs['context'].check_hostname)
            smtp = transport.return_value.__enter__.return_value
            smtp.login.assert_called_once_with('resend', 'test-only')
            message = smtp.send_message.call_args.args[0]
            self.assertEqual(str(message['From']), 'Chat <no-replay@9991565.xyz>')
            self.assertIn('test-code', message.get_content())

        self.addAsyncCleanup(async_engine.dispose)
        self.addCleanup(engine.dispose)
        async with async_engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Auth.__table__, User.__table__]))
        email = 'owner@example.com'
        user = await Auths.insert_new_auth(email, await get_password_hash('before'), 'Owner')
        await Auths.insert_new_auth('ldap@example.com', 'ldap-placeholder', 'LDAP')
        await Auths.insert_new_auth('sso@example.com', await get_password_hash('random'), 'SSO', oauth={'idp': 'sub'})
        async with get_async_db() as db:
            auth = await Auths.get_auth_by_id(user.id, db=db)
            await Auths.update_mfa_by_id(auth, MfaData(secret='existing-factor'), db=db)
            await db.commit()
        app = FastAPI()
        app.state.redis = None
        app.include_router(reset.router)
        disconnect = AsyncMock()
        with (
            patch.object(reset.Config, 'get', AsyncMock(return_value=True)),
            patch.object(reset.Config, 'get_many', AsyncMock(return_value={})),
            patch.object(reset, 'send_code') as mail,
            patch.object(reset, 'publish_event', AsyncMock()),
            patch.dict(sys.modules, {'open_webui.socket.main': SimpleNamespace(disconnect_user_sessions=disconnect)}),
        ):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:

                async def request(email):
                    return await client.post('/request', json={'email': email})

                async def confirm(code):
                    return await client.post(
                        '/confirm', json={'email': email, 'reset_token': code, 'new_password': 'After-Password123!'}
                    )

                with patch.dict(os.environ, PASSWORD_RESET_SMTP_PASSWORD='re_xxxxxx'):
                    self.assertEqual((await request(email)).status_code, 403)
                for address in ('missing@example.com', 'sso@example.com', 'ldap@example.com'):
                    self.assertEqual((await request(address)).status_code, 202)
                mail.assert_not_called()
                self.assertEqual((await request(email.upper())).status_code, 202)
                self.assertEqual((await request(email)).status_code, 202)
                mail.assert_called_once()
                recipient, code = mail.call_args.args
                self.assertEqual(recipient, email)
                self.assertEqual((await confirm('wrong')).status_code, 400)
                ticket = (await Auths.get_auth_by_id(user.id)).mfa.password_reset
                self.assertEqual(ticket.token_hash, reset.digest(code))
                with patch.object(reset, 'time', SimpleNamespace(time=lambda: ticket.expires_at)):
                    self.assertEqual((await confirm(code)).status_code, 400)
                results = await asyncio.gather(confirm(code), confirm(code))
                self.assertIn(sorted(r.status_code for r in results), ([200, 400], [200, 409]))
                self.assertEqual((await confirm(code)).status_code, 400)
                disconnect.assert_awaited_once_with(user.id)
        after = await Auths.get_auth_by_id(user.id)
        self.assertNotEqual(after.session_stamp, auth.session_stamp)
        self.assertIsNone(after.mfa.password_reset)
        self.assertEqual(after.mfa.secret, 'existing-factor')
        self.assertTrue(await verify_password('After-Password123!', after.password))
        self.assertFalse(await verify_password('before', after.password))


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(
            DATA_DIR=tmp,
            DATABASE_URL=f'sqlite:///{Path(tmp).as_posix()}/test.db',
            STATIC_DIR=str(Path(tmp) / 'static'),
            ENABLE_DB_MIGRATIONS='false',
            USE_SLIM_DOCKER='true',
            WEBUI_SECRET_KEY='test-key',
            WEBUI_AUTH='true',
            PASSWORD_RESET_SMTP_PASSWORD='test-only',
        )
        unittest.main()
