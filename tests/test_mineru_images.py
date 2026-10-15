"""Regression checks for cloud ZIPs and the MinerU 4.x HTTP API."""

import base64
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import requests
from fastapi import HTTPException

spec = importlib.util.spec_from_file_location(
    'mineru_loader',
    Path(__file__).resolve().parents[1] / 'backend/open_webui/retrieval/loaders/mineru.py',
)
mineru = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mineru)

IMAGE_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l1sAAAAASUVORK5CYII='
)
IMAGE_URI = f'data:image/png;base64,{base64.b64encode(IMAGE_BYTES).decode()}'


def response(payload=None, content=None, status_code=200):
    result = requests.Response()
    result.status_code = status_code
    result._content = json.dumps(payload).encode() if content is None else content
    return result


class MinerUImagesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.pdf = Path(self.directory.name) / 'document.pdf'
        self.pdf.write_bytes(b'%PDF-1.7\n')

    def v1_loader(self, markdown):
        loader = mineru.MinerULoader(
            str(self.pdf),
            api_url='http://mineru.example',
            params={'tier': 'standard', 'enable_ocr': True, 'language': 'ch', 'page_ranges': '1-2'},
        )
        job = {
            'job_id': 'job-1',
            'status': 'completed',
            'tier': 'standard',
            'files': [
                {
                    'output_files': {'markdown': {'file_id': 'markdown-1'}},
                    'parse': {'parser_version': '4.0'},
                }
            ],
        }
        replies = [
            response({'id': 'upload-1'}),
            response({}),
            response({'file': {'id': 'file-1'}}),
            response({**job, 'status': 'queued'}),
            response(job),
            response(content=markdown.encode()),
        ]
        with (
            patch.object(mineru.requests, 'get', return_value=response({})),
            patch.object(mineru.requests, 'request', side_effect=replies) as request,
            patch.object(mineru.time, 'sleep'),
        ):
            documents = loader.load()

        self.assertEqual(request.call_args_list[0].args[:2], ('POST', 'http://mineru.example/v1/uploads'))
        self.assertEqual(
            request.call_args_list[3].kwargs['json'],
            {
                'files': [{'source': {'type': 'file_id', 'file_id': 'file-1'}, 'page_range': '1-2'}],
                'tier': 'standard',
                'ocr_mode': 'ocr',
            },
        )
        self.assertEqual(documents[0].metadata['version'], '4.0')
        return documents[0].page_content

    def test_v1_preserves_markdown_image_bytes_and_surrounding_text(self):
        markdown = f'# Document\n![chart]({IMAGE_URI})\nA caption.'
        self.assertEqual(self.v1_loader(markdown), markdown)

    def test_v1_converts_html_inline_images_to_retrievable_markdown(self):
        markdown = f'<IMG alt="chart [1] &amp; text" src="{IMAGE_URI}" />'
        self.assertEqual(self.v1_loader(markdown), f'![chart (1) & text]({IMAGE_URI})')

    def test_v1_does_not_convert_external_html_or_non_image_data(self):
        markdown = '<img src="https://example.com/image.png"><img src="data:text/html;base64,eA==">Text'
        self.assertEqual(self.v1_loader(markdown), 'Text')

    def test_v1_keeps_documents_that_contain_only_an_image(self):
        self.assertEqual(self.v1_loader(f'![]({IMAGE_URI})'), f'![]({IMAGE_URI})')

    def test_3x_server_uses_the_existing_file_parse_endpoint(self):
        loader = mineru.MinerULoader(str(self.pdf), api_url='http://mineru.example')
        with (
            patch.object(mineru.requests, 'get', return_value=response({}, status_code=404)),
            patch.object(
                mineru.requests,
                'post',
                return_value=response({'results': {'document': {'md_content': 'Legacy content'}}}),
            ) as post,
        ):
            self.assertEqual(loader.load()[0].page_content, 'Legacy content')
        self.assertEqual(post.call_args.args[0], 'http://mineru.example/file_parse')

    def test_v1_request_timeouts_keep_upstream_error_behavior(self):
        loader = mineru.MinerULoader(str(self.pdf))
        with patch.object(mineru.requests, 'request', side_effect=requests.Timeout):
            with self.assertRaises(HTTPException) as error:
                loader._request_v1_api('GET', '/v1/parse/jobs/job-1')
        self.assertEqual(error.exception.status_code, 504)

    def cloud_documents(self, markdown, max_markdown_bytes=None):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('document/full.md', markdown)
            archive.writestr('document/images/plot 1.png', IMAGE_BYTES)
        loader = mineru.MinerULoader(
            str(self.pdf), api_mode='cloud', api_key='test-key', max_markdown_bytes=max_markdown_bytes
        )
        with (
            patch.object(loader, '_request_upload_url', return_value=('batch-1', 'https://example.com/upload')),
            patch.object(loader, '_upload_to_presigned_url'),
            patch.object(
                loader, '_poll_batch_status', return_value={'full_zip_url': 'https://example.com/results.zip'}
            ),
            patch.object(mineru.requests, 'get', return_value=response(content=archive_bytes.getvalue())),
        ):
            return loader.load()

    def test_cloud_images_survive_zip_cleanup_with_url_encoded_paths(self):
        documents = self.cloud_documents('![chart](images/plot%201.png "caption")\nText')
        self.assertEqual(documents[0].page_content, f'![chart]({IMAGE_URI})\nText')

    def test_cloud_keeps_missing_external_and_outside_paths_unchanged(self):
        for path in ('missing.png', '../../outside.png', 'https://example.com/x.png', '/api/v1/files/id/content'):
            with self.subTest(path=path):
                markdown = f'![chart]({path})'
                self.assertEqual(self.cloud_documents(markdown)[0].page_content, markdown)

    def test_cloud_preserves_upstream_markdown_size_limit(self):
        with self.assertRaises(HTTPException) as error:
            self.cloud_documents('Content exceeding limit', max_markdown_bytes=4)
        self.assertEqual(error.exception.status_code, 502)


if __name__ == '__main__':
    unittest.main()
