"""DeepSeek Fetch regressions without starting the backend or its database."""

import ast
import asyncio
import datetime as dt
import json
import logging
import math
import time
import typing
import unittest
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import requests
from fastapi.concurrency import run_in_threadpool
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

root = Path(__file__).resolve().parents[1]
loader_path = root / 'backend/open_webui/retrieval/web/utils.py'
loader_source = ast.parse(loader_path.read_text(encoding='utf-8'))
namespace = {
    'AsyncIterator': AsyncIterator,
    'BaseLoader': BaseLoader,
    'DEFAULT_CONFIG': {
        'web.loader.engine': '',
        'web.loader.timeout': '',
        'web.search.deepseek_search_api_key': '',
    },
    'Document': Document,
    'ERROR_MESSAGES': SimpleNamespace(INVALID_URL='Invalid URL'),
    'Iterator': Iterator,
    'Optional': typing.Optional,
    'Sequence': Sequence,
    'Union': typing.Union,
    'datetime': dt.datetime,
    'log': logging.getLogger('deepseek-fetch-test'),
    'math': math,
    'requests': requests,
    'run_in_threadpool': run_in_threadpool,
    'time': time,
    'timedelta': dt.timedelta,
    'validate_url': Mock(return_value=True),
}
loader_nodes = [
    node
    for node in loader_source.body
    if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    and node.name in {'RateLimitMixin', 'SafeDeepSeekLoader', 'get_web_loader', 'safe_validate_urls'}
]
exec(compile(ast.Module(body=loader_nodes, type_ignores=[]), str(loader_path), 'exec'), namespace)
SafeDeepSeekLoader = namespace['SafeDeepSeekLoader']
get_web_loader = namespace['get_web_loader']


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


class DeepSeekFetchTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            'web.loader.engine': 'deepseek',
            'web.loader.timeout': '12.5',
            'web.loader.ssl_verification': False,
            'web.loader.concurrent_requests': 10,
            'web.search.trust_env': True,
            'web.search.deepseek_search_api_key': 'test-key',
            'web.search.engine': 'searxng',
        }
        namespace['validate_url'].reset_mock(side_effect=True)
        self.session = Mock()
        self.session.headers = {}
        self.session.post.return_value = response({'title': 'Article', 'content': '# Article\n\n正文。'})
        session_patch = patch.object(requests, 'Session')
        self.session_factory = session_patch.start()
        self.addCleanup(session_patch.stop)
        self.session_factory.return_value.__enter__.return_value = self.session
        rate_patch = patch.object(SafeDeepSeekLoader, '_sync_wait_for_rate_limit')
        self.rate_wait = rate_patch.start()
        self.addCleanup(rate_patch.stop)

    def test_factory_loads_markdown_with_title_and_original_source(self):
        documents = get_web_loader('https://example.com/article', self.config).load()

        self.session.post.assert_called_once_with(
            'https://api.deepseek.com/v1/tools/fetch',
            json={'url': 'https://example.com/article'},
            timeout=12.5,
            allow_redirects=False,
        )
        self.assertEqual(self.session.headers['Authorization'], 'Bearer test-key')
        self.assertTrue(self.session.trust_env)
        self.assertFalse(self.session.verify)
        self.assertEqual(
            documents,
            [
                Document(
                    page_content='# Article\n\n正文。',
                    metadata={'source': 'https://example.com/article', 'title': 'Article'},
                )
            ],
        )

    def test_async_search_result_loading_preserves_url_order(self):
        urls = ['https://example.com/one', 'https://example.com/two']
        loader = get_web_loader(urls, self.config)
        documents = asyncio.run(loader.aload())

        self.assertEqual([document.metadata['source'] for document in documents], urls)
        self.assertEqual(self.rate_wait.call_count, 2)

    def test_missing_title_is_optional(self):
        self.session.post.return_value = response({'content': 'Body'})

        documents = get_web_loader('https://example.com', self.config).load()

        self.assertEqual(documents[0].metadata, {'source': 'https://example.com'})

    def test_factory_filters_urls_before_sending_them_to_deepseek(self):
        namespace['validate_url'].side_effect = [ValueError('Blocked URL'), True]
        urls = ['http://127.0.0.1', 'https://example.com/article']

        documents = get_web_loader(urls, self.config).load()

        self.assertEqual(len(documents), 1)
        self.assertEqual(self.session.post.call_args.kwargs['json'], {'url': urls[1]})

    def test_all_blocked_urls_do_not_create_a_session(self):
        namespace['validate_url'].side_effect = ValueError('Blocked URL')

        with self.assertRaisesRegex(ValueError, 'Invalid URL'):
            get_web_loader('http://127.0.0.1', self.config)

        self.session_factory.assert_not_called()

    def test_missing_api_key_fails_before_network_access(self):
        for api_key in ('', None, '   '):
            with self.subTest(api_key=api_key), self.assertRaisesRegex(ValueError, 'DEEPSEEK_SEARCH_API_KEY'):
                get_web_loader('https://example.com', {**self.config, 'web.search.deepseek_search_api_key': api_key})
        self.session_factory.assert_not_called()

    def test_timeout_fallback_and_api_rate_limit(self):
        for timeout in ('', None, 'invalid', '0', '-1', 'inf', 'nan'):
            with self.subTest(timeout=timeout):
                loader = get_web_loader('https://example.com', {**self.config, 'web.loader.timeout': timeout})
                self.assertEqual(loader.timeout, 60)
        for rate, expected in ((0, 5), (None, 5), (10, 5), (2, 2)):
            with self.subTest(rate=rate):
                loader = get_web_loader('https://example.com', {**self.config, 'web.loader.concurrent_requests': rate})
                self.assertEqual(loader.requests_per_second, expected)

    def test_partial_failure_keeps_successful_pages(self):
        self.session.post.side_effect = [
            response({'error': {'message': 'Not available'}}, status=404),
            response({'title': '', 'content': 'Body'}),
        ]

        documents = get_web_loader(['https://example.com/missing', 'https://example.com/article'], self.config).load()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata['source'], 'https://example.com/article')

    def test_authentication_billing_and_policy_errors_stop_loading(self):
        for status in (401, 402, 403):
            with self.subTest(status=status):
                self.session.post.reset_mock()
                self.session.post.return_value = response({'error': {'message': 'Denied'}}, status=status)
                with self.assertRaisesRegex(PermissionError, f'HTTP {status}'):
                    get_web_loader(['https://example.com/one', 'https://example.com/two'], self.config).load()
                self.session.post.assert_called_once()

    def test_empty_and_malformed_responses_fail_instead_of_yielding_empty_documents(self):
        for payload in ([], {}, {'content': None}, {'content': ''}, {'content': '  '}, {'content': 123}):
            with self.subTest(payload=payload):
                self.session.post.return_value = response(payload)
                with self.assertRaisesRegex(ValueError, 'could not load any page content'):
                    get_web_loader('https://example.com', self.config).load()

    def test_network_errors_do_not_leak_response_details_into_logs(self):
        self.session.post.side_effect = requests.Timeout('sensitive-provider-details')

        with self.assertLogs(namespace['log'], level='WARNING') as logs:
            with self.assertRaisesRegex(ValueError, 'could not load any page content'):
                get_web_loader('https://example.com', self.config).load()

        self.assertNotIn('sensitive-provider-details', '\n'.join(logs.output))

    def test_strict_mode_reports_failed_page(self):
        self.session.post.return_value = response({}, status=504)
        loader = get_web_loader('https://example.com', self.config)
        loader.continue_on_failure = False

        with self.assertRaisesRegex(ValueError, 'DeepSeek web loader request failed'):
            loader.load()

    def test_chat_url_fetch_loads_the_shared_api_key_from_config(self):
        retrieval_path = root / 'backend/open_webui/retrieval/utils.py'
        retrieval_source = ast.parse(retrieval_path.read_text(encoding='utf-8'))
        fetch_function = next(
            node
            for node in retrieval_source.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'get_content_from_url'
        )
        config_store = SimpleNamespace(
            get_many=AsyncMock(side_effect=lambda *keys: {key: self.config.get(key) for key in keys})
        )

        def fetch_sync(request, url, config):
            documents = get_web_loader(url, config).load()
            return ' '.join(document.page_content for document in documents), documents

        fetch_namespace = {
            'Config': config_store,
            '_get_content_from_url_sync': fetch_sync,
            'asyncio': asyncio,
        }
        exec(
            compile(ast.Module(body=[fetch_function], type_ignores=[]), str(retrieval_path), 'exec'),
            fetch_namespace,
        )

        content, documents = asyncio.run(fetch_namespace['get_content_from_url'](None, 'https://example.com/article'))

        self.assertIn('web.search.deepseek_search_api_key', config_store.get_many.call_args.args)
        self.assertEqual(content, '# Article\n\n正文。')
        self.assertEqual(documents[0].metadata['source'], 'https://example.com/article')


if __name__ == '__main__':
    unittest.main()
