"""Responses payload regressions without starting the backend or its database."""

import ast
import unittest
from pathlib import Path

router_path = Path(__file__).resolve().parents[1] / 'backend/open_webui/routers/openai.py'
router_source = ast.parse(router_path.read_text(encoding='utf-8'))
helpers = ast.Module(
    body=[
        node
        for node in router_source.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {'convert_to_responses_payload', 'openai_reasoning_model_handler'}
    ],
    type_ignores=[],
)
namespace = {}
exec(compile(helpers, str(router_path), 'exec'), namespace)
convert_to_responses_payload = namespace['convert_to_responses_payload']
openai_reasoning_model_handler = namespace['openai_reasoning_model_handler']


class ResponsesReasoningEffortTest(unittest.TestCase):
    def test_configured_effort_reaches_responses_for_streaming_and_non_streaming_chats(self):
        for stream in (True, False):
            with self.subTest(stream=stream):
                payload = openai_reasoning_model_handler(
                    {
                        'model': 'gpt-6.1-sol',
                        'messages': [{'role': 'user', 'content': 'Hello'}],
                        'reasoning_effort': 'xhigh',
                        'max_tokens': 256,
                        'stream': stream,
                    }
                )
                self.assertEqual(
                    convert_to_responses_payload(payload),
                    {
                        'model': 'gpt-6.1-sol',
                        'input': [
                            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Hello'}]}
                        ],
                        'reasoning': {'effort': 'xhigh'},
                        'max_output_tokens': 256,
                        'stream': stream,
                    },
                )

    def test_effort_is_not_limited_to_a_model_or_a_fixed_list(self):
        for effort in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'custom-effort'):
            with self.subTest(effort=effort):
                result = convert_to_responses_payload({'model': 'custom-model', 'reasoning_effort': effort})
                self.assertEqual(result['reasoning'], {'effort': effort})
                self.assertNotIn('reasoning_effort', result)

    def test_preserves_other_reasoning_options_without_mutating_the_original(self):
        reasoning = {'summary': 'auto'}
        result = convert_to_responses_payload({'reasoning_effort': 'xhigh', 'reasoning': reasoning})
        self.assertEqual(result['reasoning'], {'effort': 'xhigh', 'summary': 'auto'})
        self.assertEqual(reasoning, {'summary': 'auto'})
        self.assertNotIn('reasoning_effort', result)

    def test_explicit_native_effort_takes_precedence(self):
        result = convert_to_responses_payload(
            {'reasoning_effort': 'xhigh', 'reasoning': {'effort': 'low', 'summary': 'auto'}}
        )
        self.assertEqual(result['reasoning'], {'effort': 'low', 'summary': 'auto'})
        self.assertNotIn('reasoning_effort', result)

    def test_default_effort_does_not_add_reasoning(self):
        for params in ({}, {'reasoning_effort': None}):
            with self.subTest(params=params):
                self.assertEqual(convert_to_responses_payload(params), {'input': []})

    def test_native_reasoning_passes_through_when_effort_is_unset(self):
        result = convert_to_responses_payload({'reasoning_effort': None, 'reasoning': {'summary': 'auto'}})
        self.assertEqual(result, {'input': [], 'reasoning': {'summary': 'auto'}})

    def test_configured_effort_handles_null_native_reasoning(self):
        result = convert_to_responses_payload({'reasoning_effort': 'xhigh', 'reasoning': None})
        self.assertEqual(result, {'input': [], 'reasoning': {'effort': 'xhigh'}})

    def test_chat_completions_reasoning_effort_stays_flat(self):
        result = openai_reasoning_model_handler(
            {
                'model': 'gpt-6.1-sol',
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'reasoning_effort': 'xhigh',
            }
        )
        self.assertEqual(result['reasoning_effort'], 'xhigh')
        self.assertNotIn('reasoning', result)


if __name__ == '__main__':
    unittest.main()
