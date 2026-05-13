from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import os
import sys
from typing import TypedDict

from dotenv import load_dotenv
from ollama import Client, ChatResponse
# from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import END, START, StateGraph

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY", "")
#os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ["OLLAMA_API_KEY"] = os.getenv("OLLAMA_API_KEY", "")

class NewsGraphState(TypedDict):
    query: str
    search_results: str
    curated_news: str
    final_digest: str

OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))
OLLAMA_RETRIES = int(os.getenv("OLLAMA_RETRIES", "2"))

OLLAMA_CLIENT = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"},
)

MAX_SEARCH_CHARS = 12000
MAX_CURATED_CHARS = 8000


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated for runtime stability]"


def _coerce_message_content(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in content if part is not None).strip()
    return str(content).strip()


def _invoke_llm_with_timeout(prompt: str) -> object:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(OLLAMA_CLIENT.chat, model="gemma3:4b", messages=[{"role": "user", "content": prompt}], stream=False)
    try:
        return future.result(timeout=OLLAMA_TIMEOUT_SECONDS)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise TimeoutError(
            f"model call exceeded {OLLAMA_TIMEOUT_SECONDS}s hard timeout"
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _invoke_llm_with_retries(prompt: str, stage: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, OLLAMA_RETRIES + 1):
        try:
            response = _invoke_llm_with_timeout(prompt)
            text = _coerce_message_content(response)
            if text:
                return text
            raise RuntimeError("model returned empty content")
        except Exception as exc:
            last_error = exc
            print(
                f"[{stage}] model attempt {attempt}/{OLLAMA_RETRIES} failed: "
                f"{type(exc).__name__}: {exc}"
            )
    raise RuntimeError(f"model invocation failed after {OLLAMA_RETRIES} attempts") from last_error


def _fallback_curated_news(search_results: str, max_items: int = 8) -> str:
    items: list[tuple[str, str]] = []
    current_title = ""
    current_url = ""

    for line in search_results.splitlines():
        line = line.strip()
        if line.startswith("Title: "):
            current_title = line.removeprefix("Title: ").strip()
        elif line.startswith("URL: "):
            current_url = line.removeprefix("URL: ").strip()
            if current_title:
                items.append((current_title, current_url))
                current_title = ""
                current_url = ""
        if len(items) >= max_items:
            break

    if not items:
        return "## Curated Tech Updates\n\nNo high-confidence items were extracted from the search results."

    lines = [
        "## Curated Tech Updates",
        "",
        "Fallback mode was used because the local model call timed out or failed.",
        "",
    ]
    for idx, (title, url) in enumerate(items, start=1):
        lines.append(f"### {idx}. {title}")
        lines.append("Why it matters: Relevant update for IT/AI monitoring.")
        lines.append(f"Source: {url or 'N/A'}")
        lines.append("")
    return "\n".join(lines).strip()


def _fallback_digest(curated_news: str) -> str:
    preview = _trim_text(curated_news, 1800)
    return (
        "## Executive Summary\n"
        "Model summarization was unavailable, so this digest includes a direct curated-news preview.\n\n"
        "## Top Updates\n"
        f"{preview}\n\n"
        "## Watchlist\n"
        "1. AI model release cadence and benchmark reliability\n"
        "2. Enterprise adoption signals for AI agents and copilots\n"
        "3. Semiconductor supply, cloud spend, and valuation pressure"
    )


def _tavily_search(query: str, max_results: int = 10) -> str:
    if not os.getenv("TAVILY_API_KEY"):
        raise ValueError("TAVILY_API_KEY is not set. Add it to your .env file.")

    tool = TavilySearch(max_results=max_results, topic="news")
    raw = tool.invoke(query)

    if isinstance(raw, dict):
        items = raw.get("results", [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        body = str(item.get("content", item.get("snippet", ""))).strip()
        lines.append(f"Title: {title}\nURL: {url}\nSnippet: {body}")

    if not lines:
        return "No search results found."
    return "\n\n".join(lines)

def collect_news_node(state: NewsGraphState) -> NewsGraphState:
    print("[collect_news] searching web...")

    query = state["query"]
    search_results = _tavily_search(query=query, max_results=10)
    search_results = _trim_text(search_results, MAX_SEARCH_CHARS)
    print(f"[collect_news] search complete ({len(search_results)} chars), calling model...")

    curation_prompt = f"""
[IMPORTANT] You MUST write ALL output in Korean. Only URLs and source names may remain in their original language. Do NOT use English anywhere else.

You are a content collector focused on IT, AI advancements, AI agents/frameworks,
and tech market news.

Use ONLY the search results below and produce a curated report in markdown.

Requirements:
- Keep only high-signal updates from the last 24-48 hours when possible.
- Prioritize credible sources.
- For each item provide:
  1) headline (Korean)
  2) why it matters (1-2 lines, Korean)
  3) source name + URL
- Return 5-10 items.
- 모든 내용은 한국어로 작성되어야 합니다.

Search query:
{query}

Search results:
{search_results}
"""

    try:
        curated_news = _invoke_llm_with_retries(curation_prompt, "collect_news")
    except Exception as exc:
        print(f"[collect_news] model unavailable, using fallback curation: {exc}")
        curated_news = _fallback_curated_news(search_results)

    curated_news = _trim_text(curated_news, MAX_CURATED_CHARS)
    print(f"[collect_news] model complete ({len(curated_news)} chars)")
    return {
        "query": query,
        "search_results": search_results,
        "curated_news": curated_news,
        "final_digest": "",
    }


def summarize_news_node(state: NewsGraphState) -> NewsGraphState:
    print("[summarize_news] generating final digest...")
    summary_prompt = f"""
[IMPORTANT] 모든 내용은 한국어로 작성되어야 합니다. Only URLs and source names may remain in their original language. Do NOT use English anywhere else.

You are preparing a daily tech digest for professionals.

Using the curated news below, create:
- A short executive summary (4-6 lines, Korean)
- Top 5 updates with concise takeaways (Korean)
- A final section called '주목할 트렌드' with 3 trends to monitor (Korean)
- 모든 내용은 한국어로 작성되어야 합니다.

Curated news:
{state['curated_news']}
"""

    try:
        final_digest = _invoke_llm_with_retries(summary_prompt, "summarize_news")
    except Exception as exc:
        print(f"[summarize_news] model unavailable, using fallback summary: {exc}")
        final_digest = _fallback_digest(state["curated_news"])

    print("[summarize_news] complete")
    return {
        "query": state["query"],
        "search_results": state["search_results"],
        "curated_news": state["curated_news"],
        "final_digest": final_digest,
    }


def build_graph():
    graph_builder = StateGraph(NewsGraphState)

    graph_builder.add_node("collect_news", collect_news_node)
    graph_builder.add_node("summarize_news", summarize_news_node)

    graph_builder.add_edge(START, "collect_news")
    graph_builder.add_edge("collect_news", "summarize_news")
    graph_builder.add_edge("summarize_news", END)

    return graph_builder.compile()


def run_news_graph(query: str | None = None) -> NewsGraphState:
    default_query = (
        "latest IT industry developments AI advancements AI agents frameworks "
        "tech market news past 48 hours"
    )

    workflow = build_graph()

    initial_state: NewsGraphState = {
        "query": query or default_query,
        "search_results": "",
        "curated_news": "",
        "final_digest": "",
    }

    return workflow.invoke(initial_state)


    
