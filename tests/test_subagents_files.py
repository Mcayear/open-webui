"""Sub-agent attachment selection regressions without loading the application."""

import ast
import asyncio
import copy
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

source_path = Path(__file__).resolve().parents[1] / 'backend/open_webui/utils/subagents.py'
source = ast.parse(source_path.read_text(encoding='utf-8'))
helpers = ast.Module(
    body=[
        node
        for node in source.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {'_file_reference_values', '_get_attached_files', '_select_requested_files', 'delegate'}
    ],
    type_ignores=[],
)
namespace = {'asyncio': asyncio, 'copy': copy, 'JSONCodec': json, 'Request': object, 'time': time, 'uuid4': uuid4}
exec(compile(helpers, str(source_path), 'exec'), namespace)
select_requested_files = namespace['_select_requested_files']
delegate = namespace['delegate']


class SubagentFilesTest(unittest.TestCase):
    def test_keeps_support_for_files_present_only_in_request_metadata(self):
        document = {'id': 'document-1', 'type': 'file'}

        files, missing = select_requested_files({'files': [document]}, {'document-1'})

        self.assertEqual(files, [document])
        self.assertEqual(missing, [])

    def test_selects_image_attached_to_the_current_user_message(self):
        image = {
            'id': 'image-1',
            'type': 'image',
            'content_type': 'image/png',
            'url': '/api/v1/files/image-1/content',
        }

        files, missing = select_requested_files({'user_message': {'files': [image]}}, {'image-1'})

        self.assertEqual(files, [image])
        self.assertEqual(files[0]['type'], 'image')
        self.assertEqual(missing, [])
        self.assertIsNot(files[0], image)

    def test_selects_only_requested_files_using_supported_reference_forms(self):
        files_by_message = [
            {'id': 'image-1', 'type': 'image', 'url': '/api/v1/files/image-1/content'},
            {'url': '/api/v1/files/image-2/content', 'type': 'image'},
            {'file': {'id': 'document-1'}, 'type': 'file'},
            {'id': 'unrequested', 'type': 'image'},
        ]

        selected, missing = select_requested_files(
            {'user_message': {'files': files_by_message}},
            {'image-1', '/api/v1/files/image-2/content', 'document-1', 'missing'},
        )

        self.assertEqual(selected, files_by_message[:3])
        self.assertEqual(missing, ['missing'])

    def test_deduplicates_the_same_attachment_from_both_metadata_sources(self):
        image = {'id': 'image-1', 'type': 'image', 'url': '/api/v1/files/image-1/content'}

        selected, missing = select_requested_files(
            {'files': [image], 'user_message': {'files': [copy.deepcopy(image)]}},
            {'image-1'},
        )

        self.assertEqual(selected, [image])
        self.assertEqual(missing, [])

    def test_reports_all_requested_ids_missing_from_both_sources(self):
        selected, missing = select_requested_files(
            {'files': [{'id': 'available'}], 'user_message': {'files': []}},
            {'not-attached-b', 'not-attached-a'},
        )

        self.assertEqual(selected, [])
        self.assertEqual(missing, ['not-attached-a', 'not-attached-b'])


class SubagentDelegationFilesTest(unittest.IsolatedAsyncioTestCase):
    async def test_message_image_reaches_created_chat_and_completion_request(self):
        image = {
            'id': 'image-1',
            'type': 'image',
            'content_type': 'image/png',
            'url': '/api/v1/files/image-1/content',
        }
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
            async def insert_new_chat(chat_id, user_id, form_data, internal_meta=None):
                recorded['chat'] = form_data.chat
                return SimpleNamespace(id=chat_id)

            @staticmethod
            async def get_message_by_id_and_message_id(chat_id, message_id):
                return {'content': 'Image reviewed'}

        class ChatFormStub:
            def __init__(self, *, chat):
                self.chat = chat

        async def completion_handler(request, form_data, user=None):
            recorded['completion'] = copy.deepcopy(form_data)

        async def build_request(source, user_id, *, internal):
            return RequestStub(source.app)

        async def create_task(redis, coroutine, id=None):
            return id, asyncio.create_task(coroutine)

        class RequestStub:
            def __init__(self, app):
                self.app = app
                self.state = SimpleNamespace()

        app = SimpleNamespace(state=SimpleNamespace(redis=None, CHAT_COMPLETION_HANDLER=completion_handler))
        namespace.update(
            {
                'Config': ConfigStub,
                'Chats': ChatsStub,
                'ChatForm': ChatFormStub,
                'UserModel': SimpleNamespace,
                'DEFAULT_SUBAGENT_SYSTEM_PROMPT': 'Sub-agent instructions',
                '_build_request': build_request,
                '_foreground_semaphore': None,
                'add_or_update_system_message': lambda system, messages, append=True: messages,
                'create_task': create_task,
            }
        )

        result = await delegate(
            'Describe the image',
            '',
            False,
            file_ids=['image-1'],
            request=RequestStub(app),
            user_data={'id': 'user-1'},
            metadata={
                'model_id': 'vision-model',
                'user_message': {'files': [image]},
            },
            parent_chat_id='parent-chat',
            parent_message_id='parent-message',
        )

        self.assertEqual(result, 'Image reviewed')
        self.assertEqual(recorded['chat']['files'], [image])
        saved_user_messages = [
            message for message in recorded['chat']['history']['messages'].values() if message['role'] == 'user'
        ]
        self.assertEqual(saved_user_messages[0]['files'], [image])
        self.assertEqual(recorded['completion']['files'], [image])
        self.assertEqual(recorded['completion']['user_message']['files'], [image])


if __name__ == '__main__':
    unittest.main()
