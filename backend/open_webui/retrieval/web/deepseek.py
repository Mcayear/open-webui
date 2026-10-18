from __future__ import annotations

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

DEEPSEEK_SEARCH_URL = 'https://api.deepseek.com/v1/tools/search'


def search_deepseek(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str] | None = None,
) -> list[SearchResult]:
    """Search the web with DeepSeek's Search API."""

    request_count = max(1, min(int(count or 1), 50))
    response = requests.post(
        DEEPSEEK_SEARCH_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'query': query,
            'count': request_count,
            'need_content': True,
        },
        timeout=30,
    )
    response.raise_for_status()

    results = response.json().get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result.get('url', ''),
            title=result.get('title'),
            snippet=result.get('summary') or result.get('snippet') or result.get('content'),
        )
        for result in results[:request_count]
    ]
