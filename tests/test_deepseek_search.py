"""Regression checks for the DeepSeek web search provider."""

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch


class Requests:
    post = None


requests = Requests()


@dataclass
class SearchResult:
    link: str
    title: str | None
    snippet: str | None


filtered_calls = []


def get_filtered_results(results, filter_list):
    filtered_calls.append((results, filter_list))
    return results[:1]


provider_path = Path(__file__).resolve().parents[1] / 'backend/open_webui/retrieval/web/deepseek.py'
provider_source = ast.parse(provider_path.read_text(encoding='utf-8'))
provider_function = next(node for node in provider_source.body if isinstance(node, ast.FunctionDef))
namespace = {
    'requests': requests,
    'SearchResult': SearchResult,
    'get_filtered_results': get_filtered_results,
    'DEEPSEEK_SEARCH_URL': 'https://api.deepseek.com/v1/tools/search',
}
exec(compile(ast.Module(body=[provider_function], type_ignores=[]), str(provider_path), 'exec'), namespace)
search_deepseek = namespace['search_deepseek']


class DeepSeekSearchTest(unittest.TestCase):
    def setUp(self):
        filtered_calls.clear()

    def test_sends_deepseek_payload_and_normalizes_results(self):
        response = Mock()
        response.json.return_value = {
            'results': [
                {
                    'url': 'https://example.com/one',
                    'title': 'One',
                    'snippet': 'Short one',
                    'summary': 'Summary one',
                    'content': 'Content one',
                },
                {
                    'url': 'https://example.com/two',
                    'title': 'Two',
                    'snippet': 'Short two',
                },
            ]
        }

        with patch.object(requests, 'post', return_value=response) as post:
            results = search_deepseek('secret', 'latest news', 100, ['example.com'])

        post.assert_called_once_with(
            'https://api.deepseek.com/v1/tools/search',
            headers={
                'Authorization': 'Bearer secret',
                'Content-Type': 'application/json',
            },
            json={'query': 'latest news', 'count': 50, 'need_content': True},
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(filtered_calls[0][1], ['example.com'])
        self.assertEqual(results, [SearchResult('https://example.com/one', 'One', 'Summary one')])

    def test_uses_snippet_or_content_when_summary_is_missing(self):
        response = Mock()
        response.json.return_value = {
            'results': [
                {'url': 'https://example.com/one', 'title': 'One', 'snippet': 'Short one'},
                {'url': 'https://example.com/two', 'title': 'Two', 'content': 'Content two'},
            ]
        }

        with patch.object(requests, 'post', return_value=response):
            results = search_deepseek('secret', 'query', 2)

        self.assertEqual(
            results,
            [
                SearchResult('https://example.com/one', 'One', 'Short one'),
                SearchResult('https://example.com/two', 'Two', 'Content two'),
            ],
        )


if __name__ == '__main__':
    unittest.main()
