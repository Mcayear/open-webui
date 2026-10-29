"""Exercise actual delegation and image replay with isolated persistence and model IO."""

import ast
import asyncio
import copy
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
namespace = {'asyncio': asyncio, 'copy': copy, 'JSONCodec': json, 'Request': object, 'time': time, 'uuid4': uuid4}
for relative, names in (
    ('utils/misc.py', {'is_raster_image_content_type'}),
    ('utils/subagents.py', {'delegate'}),
):
    path = ROOT / 'backend/open_webui' / relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
delegate = namespace['delegate']


class SubagentDelegationFilesTest(unittest.IsolatedAsyncioTestCase):
    async def run_delegation(self, *, metadata=None, messages=None, file_ids=None):
        recorded = {}

        class ConfigStub:
            @staticmethod
            async def get_many(*keys):
                return {
                    'subagents.background_enabled': False,
                    'subagents.max_concurrent': -1,
                    'subagents.max_async': -1,
                    'subagents.max_iterations': 30,
                    'subagents.max_output': 30_000,
                    'subagents.system_prompt': '',
                }

        class ChatsStub:
            @staticmethod
            async def get_chat_folder_id(chat_id, user_id):
                return None

            @staticmethod
            async def get_messages_map_by_chat_id(chat_id):
                return copy.deepcopy(messages or {})

            @staticmethod
            async def insert_new_chat(chat_id, user_id, form_data, internal_meta=None):
                recorded['chat'] = copy.deepcopy(form_data.chat)
                return SimpleNamespace(id=chat_id)

            @staticmethod
            async def get_message_by_id_and_message_id(chat_id, message_id):
                return {'content': 'Attachments reviewed'}

        class RequestStub:
            def __init__(self, app):
                self.app = app
                self.state = SimpleNamespace()

        async def completion_handler(request, form_data, user=None):
            recorded['completion'] = copy.deepcopy(form_data)

        async def build_request(source, user_id, *, internal):
            return RequestStub(source.app)

        async def create_task(redis, coroutine, id=None):
            return id, asyncio.create_task(coroutine)

        app = SimpleNamespace(state=SimpleNamespace(redis=None, CHAT_COMPLETION_HANDLER=completion_handler))
        namespace.update(
            {
                'Config': ConfigStub,
                'Chats': ChatsStub,
                'ChatForm': lambda **kwargs: SimpleNamespace(**kwargs),
                'UserModel': SimpleNamespace,
                'DEFAULT_SUBAGENT_SYSTEM_PROMPT': 'Sub-agent instructions',
                '_build_request': build_request,
                '_foreground_semaphore': None,
                'add_or_update_system_message': lambda system, messages, append=True: messages,
                'create_task': create_task,
            }
        )
        result = await delegate(
            'Review attachments',
            '',
            False,
            file_ids=file_ids,
            request=RequestStub(app),
            user_data={'id': 'user-1'},
            metadata={'model_id': 'vision-model', **(metadata or {})},
            parent_chat_id='parent-chat',
            parent_message_id='parent-message',
        )
        return result, recorded

    def assert_forwarded(self, recorded, files):
        saved = [m for m in recorded['chat']['history']['messages'].values() if m['role'] == 'user']
        self.assertEqual(saved[0].get('files', []), files)
        self.assertEqual(recorded['completion']['user_message'].get('files', []), files)
        documents = [
            f
            for f in files
            if f.get('type') != 'image' and not namespace['is_raster_image_content_type'](f.get('content_type'))
        ]
        self.assertEqual(recorded['chat']['files'], files)
        self.assertEqual(recorded['completion']['files'], documents)
        return saved[0]

    async def test_current_message_image_without_persisted_history_reaches_visual_replay(self):
        image = {'id': 'image-1', 'type': 'image', 'url': '/api/v1/files/image-1/content'}
        result, recorded = await self.run_delegation(
            metadata={'user_message': {'files': [image]}}, file_ids=['image-1']
        )
        self.assertEqual(result, 'Attachments reviewed')
        message = self.assert_forwarded(recorded, [image])

        # Execute the real image replay loop used by process_chat_payload for saved messages.
        path = ROOT / 'backend/open_webui/utils/middleware.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(
            n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process_chat_payload'
        )
        loop = next(
            n
            for n in ast.walk(function)
            if isinstance(n, ast.For)
            and isinstance(n.target, ast.Name)
            and n.target.id == 'message'
            and any(isinstance(c, ast.Name) and c.id == 'image_files' for c in ast.walk(n))
        )
        context = {
            'form_data': {'messages': [message]},
            'is_raster_image_content_type': namespace['is_raster_image_content_type'],
        }
        exec(compile(ast.Module(body=[loop], type_ignores=[]), str(path), 'exec'), context)
        self.assertEqual(message['content'][1], {'type': 'image_url', 'image_url': {'url': image['url']}})

    async def test_persisted_current_image_uses_upstream_lookup(self):
        image = {'id': 'image-1', 'type': 'image', 'url': '/api/v1/files/image-1/content'}
        result, recorded = await self.run_delegation(
            messages={'current': {'role': 'user', 'files': [image]}}, file_ids=['image-1']
        )
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [image])

    async def test_historical_image_recognized_by_content_type(self):
        image = {'id': 'old-image', 'content_type': 'image/png', 'url': '/api/v1/files/old-image/content'}
        result, recorded = await self.run_delegation(
            messages={'old': {'role': 'user', 'files': [image]}}, file_ids=['old-image']
        )
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [image])

    async def test_top_level_document_with_nested_file_id(self):
        document = {'file': {'id': 'document-1'}, 'type': 'file'}
        result, recorded = await self.run_delegation(metadata={'files': [document]}, file_ids=['document-1'])
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [document])

    async def test_deduplicates_metadata_current_message_and_persisted_image(self):
        image = {'id': 'image-1', 'type': 'image', 'url': '/api/v1/files/image-1/content'}
        metadata = {'files': [image], 'user_message': {'files': [copy.deepcopy(image)]}}
        result, recorded = await self.run_delegation(
            metadata=metadata,
            messages={'current': {'role': 'user', 'files': [image]}},
            file_ids=['image-1', image['url']],
        )
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [image])

    async def test_selects_only_requested_url(self):
        image = {'url': '/api/v1/files/image-1/content', 'type': 'image'}
        result, recorded = await self.run_delegation(
            metadata={'files': [image, {'id': 'unrequested', 'type': 'file'}]}, file_ids=[image['url']]
        )
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [image])

    async def test_reports_all_missing_ids_before_creating_child_chat(self):
        result, recorded = await self.run_delegation(
            metadata={'files': [{'id': 'available'}]}, file_ids=['missing-b', 'missing-a']
        )
        self.assertEqual(result, 'Error: file_ids not attached or unavailable: missing-a, missing-b')
        self.assertEqual(recorded, {})

    async def test_omitting_file_ids_forwards_no_attachments(self):
        result, recorded = await self.run_delegation(metadata={'files': [{'id': 'unrequested'}]})
        self.assertEqual(result, 'Attachments reviewed')
        self.assert_forwarded(recorded, [])


if __name__ == '__main__':
    unittest.main()
