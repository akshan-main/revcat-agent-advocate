"""RAG Quality Evaluation Suite.

Measures retrieval, reranking, faithfulness, and context relevance.

Run:
  python -m tests.eval_rag                           # BM25 retrieval only
  HF_TOKEN=hf_... python -m tests.eval_rag           # + hybrid/reranking comparison
  ANTHROPIC_API_KEY=sk-ant-... python -m tests.eval_rag  # + faithfulness & context relevance (LLM judge)

Evaluation dimensions:
  1. Retrieval: MRR@5, NDCG@5, Precision@k against ground-truth queries
  2. Reranking: A/B comparison — vector-only vs vector+reranker
  3. Context relevance: LLM judges whether retrieved chunks answer the query
  4. Faithfulness: LLM checks whether generated articles' claims are grounded in source docs
"""
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advocate.config import Config
from advocate.db import init_db_from_config
from advocate.knowledge.search import build_index, search


# ---------------------------------------------------------------------------
# 1. GROUND-TRUTH QUERIES (retrieval eval)
# ---------------------------------------------------------------------------
EVAL_QUERIES = [
    ("MCP server setup authentication",
     ["https://www.revenuecat.com/docs/tools/mcp",
      "https://www.revenuecat.com/docs/tools/mcp/setup"]),
    ("Charts API metrics MRR revenue",
     ["https://www.revenuecat.com/docs/dashboard-and-metrics/charts"]),
    ("webhook events subscription lifecycle",
     ["https://www.revenuecat.com/docs/integrations/webhooks",
      "https://www.revenuecat.com/docs/integrations/webhooks/event-types-and-fields"]),
    ("offerings paywalls configuration products",
     ["https://www.revenuecat.com/docs/getting-started/entitlements",
      "https://www.revenuecat.com/docs/getting-started/displaying-products"]),
    ("SDK installation getting started iOS Android",
     ["https://www.revenuecat.com/docs/getting-started/installation",
      "https://www.revenuecat.com/docs/getting-started/configuring-sdk"]),
    ("subscription offers introductory offer code redemption",
     ["https://www.revenuecat.com/docs/subscription-guidance/subscription-offers",
      "https://www.revenuecat.com/docs/subscription-guidance/subscription-offers/ios-subscription-offers"]),
    ("migration existing subscriptions import receipts",
     ["https://www.revenuecat.com/docs/migrating-to-revenuecat/migrating-existing-subscriptions"]),
    ("customer attributes subscriber info",
     ["https://www.revenuecat.com/docs/customers/customer-attributes"]),
    ("grace period billing retry",
     ["https://www.revenuecat.com/docs/subscription-guidance/how-grace-periods-work"]),
    ("REST API v2 authentication",
     ["https://www.revenuecat.com/docs/projects/authentication"]),
    ("StoreKit 2 purchase error troubleshooting",
     ["https://www.revenuecat.com/docs/known-store-issues/storekit"]),
    ("entitlements",
     ["https://www.revenuecat.com/docs/getting-started/entitlements",
      "https://www.revenuecat.com/docs/customers/trusted-entitlements"]),
    ("React Native Flutter SDK paywalls",
     ["https://www.revenuecat.com/docs/tools/paywalls/installation",
      "https://www.revenuecat.com/docs/tools/paywalls-legacy/installation"]),
    ("funnel analytics conversion tracking",
     ["https://www.revenuecat.com/docs/tools/funnels"]),
    ("web billing purchase links",
     ["https://www.revenuecat.com/docs/web/web-billing"]),
]

# Faithfulness eval queries — used to generate short answers then check grounding
FAITHFULNESS_QUERIES = [
    "How do I set up the RevenueCat MCP server with Claude Code?",
    "What metrics does the Charts API provide?",
    "How do webhooks handle retries when a server returns an error?",
    "What is the difference between entitlements and offerings?",
    "How do I migrate existing subscriptions to RevenueCat?",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _url_match(retrieved_url: str, expected_url: str) -> bool:
    r = retrieved_url.rstrip("/")
    e = expected_url.rstrip("/")
    return r == e or r.startswith(e) or e.startswith(r)


def _dcg(relevances: list[float], k: int) -> float:
    """Discounted cumulative gain."""
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def _ndcg(relevances: list[float], ideal: list[float], k: int) -> float:
    """Normalized discounted cumulative gain."""
    dcg = _dcg(relevances, k)
    idcg = _dcg(sorted(ideal, reverse=True), k)
    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# 2. RETRIEVAL METRICS
# ---------------------------------------------------------------------------
@dataclass
class RetrievalResult:
    query: str
    expected: list[str]
    retrieved: list[str]
    mrr: float
    ndcg5: float
    p1: float
    p3: float
    p5: float


def evaluate_retrieval(search_fn, index, cache_dir, top_k=5) -> list[RetrievalResult]:
    results = []
    for query, expected_urls in EVAL_QUERIES:
        search_results = search_fn(query, index, cache_dir, top_k=top_k)
        retrieved = [r.url for r in search_results]

        # MRR
        rr = 0.0
        for rank, url in enumerate(retrieved[:top_k], 1):
            if any(_url_match(url, exp) for exp in expected_urls):
                rr = 1.0 / rank
                break

        # Binary relevance vector for NDCG
        rels = [1.0 if any(_url_match(url, exp) for exp in expected_urls) else 0.0
                for url in retrieved[:top_k]]
        ideal = [1.0] * min(len(expected_urls), top_k)
        ndcg = _ndcg(rels, ideal, top_k)

        # Precision@k
        def prec(k):
            if not retrieved[:k]:
                return 0.0
            return sum(1 for u in retrieved[:k]
                       if any(_url_match(u, e) for e in expected_urls)) / k

        results.append(RetrievalResult(
            query=query, expected=expected_urls, retrieved=retrieved[:top_k],
            mrr=rr, ndcg5=ndcg, p1=prec(1), p3=prec(3), p5=prec(5),
        ))
    return results


def print_retrieval(results: list[RetrievalResult], label: str) -> dict:
    n = len(results)
    metrics = {
        "mrr5": sum(r.mrr for r in results) / n,
        "ndcg5": sum(r.ndcg5 for r in results) / n,
        "p1": sum(r.p1 for r in results) / n,
        "p3": sum(r.p3 for r in results) / n,
        "p5": sum(r.p5 for r in results) / n,
        "queries": n,
    }

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"\n  MRR@5:        {metrics['mrr5']:.3f}")
    print(f"  NDCG@5:       {metrics['ndcg5']:.3f}")
    print(f"  Precision@1:  {metrics['p1']:.3f}")
    print(f"  Precision@3:  {metrics['p3']:.3f}")
    print(f"  Precision@5:  {metrics['p5']:.3f}")
    print(f"  Queries:      {n}")

    print(f"\n  {'Query':<45} {'MRR':>5} {'NDCG':>5} {'P@1':>5}")
    print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*5}")
    for r in results:
        print(f"  {r.query[:44]:<45} {r.mrr:>5.2f} {r.ndcg5:>5.2f} {r.p1:>5.2f}")

    misses = [r for r in results if r.mrr == 0]
    if misses:
        print(f"\n  MISSES ({len(misses)}):")
        for r in misses:
            print(f"    Q: {r.query}")
            print(f"    Expected: {r.expected}")
            print(f"    Got: {r.retrieved[:3]}")

    return metrics


# ---------------------------------------------------------------------------
# 3. RERANKING A/B
# ---------------------------------------------------------------------------
def evaluate_reranking(bm25_index, cache_dir, db, hf_token):
    """Compare vector-only vs vector+reranker retrieval quality."""
    from advocate.knowledge.rag import (
        build_rag_index, semantic_search, _rerank_hf
    )

    print("\nBuilding RAG index for reranking eval...")
    rag_index = build_rag_index(cache_dir, db, hf_token=hf_token)
    print(f"  {rag_index.doc_count} docs, {rag_index.chunk_count} chunks")

    vector_scores = []
    reranked_scores = []

    print(f"\n{'=' * 60}")
    print("  Reranking A/B: Vector-only vs Vector+Reranker")
    print(f"{'=' * 60}")
    print(f"\n  {'Query':<40} {'Vec MRR':>8} {'Rnk MRR':>8} {'Delta':>7}")
    print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*7}")

    for query, expected_urls in EVAL_QUERIES:
        # Vector-only (no reranking)
        vec_results = semantic_search(query, rag_index, top_k=10)

        # With reranking
        reranked = _rerank_hf(query, vec_results[:10], top_k=5, hf_token=hf_token)

        def mrr_from_chunks(chunks_scores, expected):
            for rank, (chunk, _) in enumerate(chunks_scores[:5], 1):
                if any(_url_match(chunk.doc_url, e) for e in expected):
                    return 1.0 / rank
            return 0.0

        v_mrr = mrr_from_chunks(vec_results, expected_urls)
        r_mrr = mrr_from_chunks(reranked, expected_urls)
        delta = r_mrr - v_mrr

        vector_scores.append(v_mrr)
        reranked_scores.append(r_mrr)

        symbol = "+" if delta > 0 else (" " if delta == 0 else "")
        print(f"  {query[:39]:<40} {v_mrr:>8.2f} {r_mrr:>8.2f} {symbol}{delta:>6.2f}")

    avg_vec = sum(vector_scores) / len(vector_scores)
    avg_rnk = sum(reranked_scores) / len(reranked_scores)
    improved = sum(1 for v, r in zip(vector_scores, reranked_scores) if r > v)
    degraded = sum(1 for v, r in zip(vector_scores, reranked_scores) if r < v)

    print(f"\n  Avg MRR vector-only: {avg_vec:.3f}")
    print(f"  Avg MRR reranked:   {avg_rnk:.3f}")
    print(f"  Improved: {improved}/{len(vector_scores)}, Degraded: {degraded}/{len(vector_scores)}")

    return {
        "vector_mrr": avg_vec,
        "reranked_mrr": avg_rnk,
        "improved": improved,
        "degraded": degraded,
        "total": len(vector_scores),
    }


# ---------------------------------------------------------------------------
# 4. CONTEXT RELEVANCE (LLM-as-judge)
# ---------------------------------------------------------------------------
def evaluate_context_relevance(search_fn, index, cache_dir, anthropic_key):
    """For each query, ask an LLM: do the retrieved chunks contain the answer?"""
    import anthropic

    client = anthropic.Anthropic(api_key=anthropic_key)
    scores = []

    print(f"\n{'=' * 60}")
    print("  Context Relevance (LLM Judge)")
    print(f"{'=' * 60}")
    print(f"\n  {'Query':<45} {'Score':>6} {'Verdict'}")
    print(f"  {'-'*45} {'-'*6} {'-'*20}")

    for query, _ in EVAL_QUERIES:
        results = search_fn(query, index, cache_dir, top_k=3)
        context = "\n\n".join(
            f"[{r.title}]({r.url})\n" + "\n".join(r.snippets[:2])
            for r in results[:3]
        )

        prompt = (
            f"Query: {query}\n\n"
            f"Retrieved context:\n{context}\n\n"
            f"Score how well the retrieved context can answer the query.\n"
            f"Reply with ONLY a JSON object: {{\"score\": 0.0-1.0, \"reason\": \"one sentence\"}}\n"
            f"1.0 = context fully answers the query\n"
            f"0.5 = context partially relevant\n"
            f"0.0 = context irrelevant"
        )

        time.sleep(0.3)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        try:
            data = json.loads(text)
            score = float(data.get("score", 0))
        except (json.JSONDecodeError, ValueError):
            score_match = re.search(r'"score"\s*:\s*([\d.]+)', text)
            score = float(score_match.group(1)) if score_match else 0.0
            _ = text[:60]

        scores.append(score)
        verdict = "relevant" if score >= 0.7 else ("partial" if score >= 0.4 else "irrelevant")
        print(f"  {query[:44]:<45} {score:>6.2f} {verdict:<20}")

    avg = sum(scores) / len(scores) if scores else 0
    print(f"\n  Average context relevance: {avg:.3f}")
    return {"avg_context_relevance": avg, "scores": scores, "queries": len(scores)}


# ---------------------------------------------------------------------------
# 5. FAITHFULNESS (LLM-as-judge on generated articles)
# ---------------------------------------------------------------------------
def evaluate_faithfulness(cache_dir, db, anthropic_key):
    """Check if claims in generated articles are grounded in source docs.

    Extracts claims from articles in the DB, retrieves the cited source docs,
    and asks an LLM to verify each claim against the source material.
    """
    import anthropic
    from advocate.db import query_rows

    client = anthropic.Anthropic(api_key=anthropic_key)

    articles = query_rows(db, "content_pieces", where={"status": "verified"}, limit=5)
    if not articles:
        articles = query_rows(db, "content_pieces", limit=3)

    if not articles:
        print("\n  No articles in DB to evaluate faithfulness")
        return None

    print(f"\n{'=' * 60}")
    print(f"  Faithfulness (LLM Judge on {len(articles)} articles)")
    print(f"{'=' * 60}")

    all_scores = []

    for article in articles:
        body = article.get("body_md", "")
        slug = article.get("slug", "")

        if not body or len(body) < 100:
            continue

        # Extract cited URLs from the article
        cited_urls = re.findall(r'\[(?:Source|[^\]]+)\]\((https://www\.revenuecat\.com/docs/[^)]+)\)', body)

        # Load source doc content for cited URLs
        pages_dir = os.path.join(cache_dir, "pages")
        source_content = []
        for url in cited_urls[:5]:
            doc_path = url.replace("https://www.revenuecat.com/docs/", "").replace("/", "__") + ".md"
            fpath = os.path.join(pages_dir, doc_path)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    source_content.append(f"[Source: {url}]\n{f.read()[:2000]}")

        if not source_content:
            continue

        sources_text = "\n\n---\n\n".join(source_content[:3])

        # Take a representative excerpt (not the whole article)
        excerpt = body[:2000]

        prompt = (
            f"You are evaluating whether an article's claims are faithful to its source documentation.\n\n"
            f"ARTICLE EXCERPT:\n{excerpt}\n\n"
            f"SOURCE DOCUMENTS:\n{sources_text}\n\n"
            f"Evaluate faithfulness. For each factual claim about RevenueCat in the article:\n"
            f"- Is it supported by the source documents?\n"
            f"- Is anything fabricated or contradicted by the sources?\n\n"
            f"Reply with ONLY a JSON object:\n"
            f'{{"score": 0.0-1.0, "supported_claims": N, "unsupported_claims": N, '
            f'"fabricated_claims": N, "reason": "one sentence summary"}}\n'
            f"1.0 = all claims grounded, 0.0 = mostly fabricated"
        )

        time.sleep(0.5)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        try:
            data = json.loads(text)
            score = float(data.get("score", 0))
            supported = data.get("supported_claims", "?")
            unsupported = data.get("unsupported_claims", "?")
            fabricated = data.get("fabricated_claims", "?")
            reason = data.get("reason", "")
        except (json.JSONDecodeError, ValueError):
            score_match = re.search(r'"score"\s*:\s*([\d.]+)', text)
            score = float(score_match.group(1)) if score_match else 0.0
            supported = unsupported = fabricated = "?"
            reason = text[:80]

        all_scores.append(score)
        print(f"\n  [{slug[:50]}]")
        print(f"    Score: {score:.2f}  |  Supported: {supported}  |  Unsupported: {unsupported}  |  Fabricated: {fabricated}")
        print(f"    {reason}")

    if not all_scores:
        return None

    avg = sum(all_scores) / len(all_scores)
    print(f"\n  Average faithfulness: {avg:.3f}")
    return {
        "avg_faithfulness": avg,
        "articles_evaluated": len(all_scores),
        "scores": all_scores,
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    config = Config()
    db = init_db_from_config(config)
    anthropic_key = config.anthropic_api_key
    hf_token = os.environ.get("HF_TOKEN")

    output = {}

    # --- 1. BM25 retrieval ---
    print("Building BM25 index...")
    bm25_index = build_index(config.docs_cache_dir, db)
    print(f"  {bm25_index.doc_count} docs, {len(bm25_index.inverted_index)} terms")

    bm25_results = evaluate_retrieval(search, bm25_index, config.docs_cache_dir)
    output["bm25"] = print_retrieval(bm25_results, "BM25 Retrieval")

    # --- 2. Hybrid retrieval + reranking ---
    output["hybrid"] = None
    output["reranking"] = None
    try:
        from advocate.knowledge.rag import build_rag_index, hybrid_search as rag_hybrid

        if hf_token:
            rag_index = build_rag_index(config.docs_cache_dir, db, hf_token=hf_token)

            def hybrid_fn(query, _idx, cache_dir, top_k=5):
                return rag_hybrid(query, rag_index, bm25_index, cache_dir, top_k=top_k)

            hybrid_results = evaluate_retrieval(hybrid_fn, bm25_index, config.docs_cache_dir)
            output["hybrid"] = print_retrieval(hybrid_results, "Hybrid (BM25 + Vectors + Reranker)")

            # --- Reranking A/B ---
            output["reranking"] = evaluate_reranking(bm25_index, config.docs_cache_dir, db, hf_token)
        else:
            print("\n  Skipping hybrid/reranking eval (HF_TOKEN not set)")
    except ImportError as e:
        print(f"\n  Skipping hybrid/reranking eval ({e})")

    # --- 3. Context relevance (LLM judge) ---
    output["context_relevance"] = None
    if anthropic_key:
        output["context_relevance"] = evaluate_context_relevance(
            search, bm25_index, config.docs_cache_dir, anthropic_key,
        )
    else:
        print("\n  Skipping context relevance eval (ANTHROPIC_API_KEY not set)")

    # --- 4. Faithfulness (LLM judge) ---
    output["faithfulness"] = None
    if anthropic_key:
        output["faithfulness"] = evaluate_faithfulness(
            config.docs_cache_dir, db, anthropic_key,
        )
    else:
        print("\n  Skipping faithfulness eval (ANTHROPIC_API_KEY not set)")

    # --- Index stats ---
    output["index_stats"] = {
        "doc_count": bm25_index.doc_count,
        "vocabulary_size": len(bm25_index.inverted_index),
        "avg_doc_length": round(bm25_index.avg_doc_length, 1),
    }

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"\n  {'Dimension':<30} {'Score':>8}")
    print(f"  {'-'*30} {'-'*8}")
    if output["bm25"]:
        print(f"  {'BM25 MRR@5':<30} {output['bm25']['mrr5']:>8.3f}")
        print(f"  {'BM25 NDCG@5':<30} {output['bm25']['ndcg5']:>8.3f}")
    if output.get("hybrid"):
        print(f"  {'Hybrid MRR@5':<30} {output['hybrid']['mrr5']:>8.3f}")
        print(f"  {'Hybrid NDCG@5':<30} {output['hybrid']['ndcg5']:>8.3f}")
    if output.get("reranking"):
        print(f"  {'Reranker lift (MRR)':<30} {output['reranking']['reranked_mrr'] - output['reranking']['vector_mrr']:>+8.3f}")
    if output.get("context_relevance"):
        print(f"  {'Context Relevance':<30} {output['context_relevance']['avg_context_relevance']:>8.3f}")
    if output.get("faithfulness"):
        print(f"  {'Faithfulness':<30} {output['faithfulness']['avg_faithfulness']:>8.3f}")

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "rag_eval_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
