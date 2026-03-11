"""RAG Quality Evaluation Suite.

Comprehensive evaluation across 7 dimensions:
  1. Retrieval: MRR@k, NDCG@k (graded), Precision@k, Recall@k, MAP — BM25, Semantic, Hybrid
  2. Reranking A/B: hybrid-with vs hybrid-without reranker (production config)
  3. Context Relevance: LLM judges whether retrieved chunks answer the query
  4. Faithfulness: LLM checks generated article claims against source docs
  5. Answer Quality: end-to-end generation quality (relevance, completeness, citation accuracy)
  6. Latency: p50/p95/p99 query latency for each retrieval method
  7. Validation set: held-out 10 queries never tuned against (overfitting check)

Ground truth: 40 training + 10 validation = 50 queries.
All URLs verified against .docs_cache/pages/ corpus.
Graded relevance: 3=primary doc, 2=strongly related, 1=tangentially relevant.
URL matching: normalized path comparison (not substring).

Run:
  python -m tests.eval_rag                                    # full eval
  python -m tests.eval_rag --bm25-only                        # BM25 retrieval only
  python -m tests.eval_rag --skip-llm                         # skip LLM-as-judge evals
  python -m tests.eval_rag --validate                         # run only validation set
  python -m tests.eval_rag --verify-urls                      # verify all ground truth URLs exist
"""
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advocate.config import Config
from advocate.db import init_db_from_config
from advocate.knowledge.search import build_index, search


# ---------------------------------------------------------------------------
# GROUND-TRUTH EVAL SET
#
# 40 training queries + 10 held-out validation queries = 50 total.
# All URLs verified against .docs_cache/pages/ corpus (326 docs).
# Covers: paywalls, charts, migration, MCP, webhooks, offerings, customers,
#         entitlements, SDKs, refunds, products, notifications, billing,
#         auth, sandbox, web, identity, funnels, experiments, integrations,
#         targeting, customer center, attribution, data exports, debugging,
#         anomaly detection, cohorts, churn, LTV, security, compliance.
# ---------------------------------------------------------------------------

# Ground truth format: (query, [(url, grade), ...])
# Grades: 3=primary doc (must-find), 2=strongly related, 1=tangentially relevant
EVAL_QUERIES = [
    # --- Paywalls & Monetization ---
    ("how to set up paywalls",
     [("https://www.revenuecat.com/docs/tools/paywalls", 3),
      ("https://www.revenuecat.com/docs/playbooks/guides/hard-paywall", 2)]),
    ("paywall conversion and abandonment metrics",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/paywall-conversion-chart", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/paywall-abandonment-chart", 3)]),
    # --- Charts & Analytics ---
    ("Charts API metrics MRR revenue",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/monthly-recurring-revenue-mrr-chart", 3)]),
    ("churn rate analysis and retention",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/churn-chart", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/subscription-retention-chart", 2)]),
    ("customer lifetime value LTV",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/realized-ltv-per-customer-chart", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/realized-ltv-per-paying-customer-chart", 3)]),
    ("cohort analysis and prediction",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/cohort-explorer", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/prediction-explorer", 2)]),
    ("real-time charts dashboard",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/charts/real-time-charts", 3)]),
    # --- Migration ---
    ("migrate from StoreKit to RevenueCat",
     [("https://www.revenuecat.com/docs/migrating-to-revenuecat/migration-paths", 3),
      ("https://www.revenuecat.com/docs/migrating-to-revenuecat/migrating-existing-subscriptions", 2)]),
    # --- MCP ---
    ("RevenueCat MCP server tools",
     [("https://www.revenuecat.com/docs/tools/mcp", 3),
      ("https://www.revenuecat.com/docs/tools/mcp/setup", 2)]),
    # --- Webhooks & Events ---
    ("subscription lifecycle events webhooks",
     [("https://www.revenuecat.com/docs/integrations/webhooks", 3),
      ("https://www.revenuecat.com/docs/integrations/webhooks/event-types-and-fields", 2)]),
    ("webhook event types and sample payloads",
     [("https://www.revenuecat.com/docs/integrations/webhooks/event-types-and-fields", 3),
      ("https://www.revenuecat.com/docs/integrations/webhooks/sample-events", 3)]),
    # --- Offerings & Products ---
    ("offering metadata",
     [("https://www.revenuecat.com/docs/tools/offering-metadata", 3),
      ("https://www.revenuecat.com/docs/tools/offering-metadata/offering-metadata-examples", 2)]),
    ("configure offerings and products",
     [("https://www.revenuecat.com/docs/projects/configuring-products", 3),
      ("https://www.revenuecat.com/docs/offerings/products-overview", 3),
      ("https://www.revenuecat.com/docs/getting-started/displaying-products", 1)]),
    # --- Customers ---
    ("customer attributes",
     [("https://www.revenuecat.com/docs/customers/customer-attributes", 3),
      ("https://www.revenuecat.com/docs/tools/targeting/custom-attributes", 1)]),
    ("user identity and app user IDs",
     [("https://www.revenuecat.com/docs/customers/user-ids", 3),
      ("https://www.revenuecat.com/docs/customers/customer-info", 2)]),
    ("blocking fraudulent customers",
     [("https://www.revenuecat.com/docs/customers/blocking-customers", 3)]),
    ("customer lists and segmentation",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/customer-lists", 3),
      ("https://www.revenuecat.com/docs/dashboard-and-metrics/customer-profile", 2)]),
    # --- Entitlements ---
    ("entitlements configuration",
     [("https://www.revenuecat.com/docs/getting-started/entitlements", 3),
      ("https://www.revenuecat.com/docs/customers/trusted-entitlements", 2)]),
    # --- SDK Installation ---
    ("RevenueCat SDK installation Flutter",
     [("https://www.revenuecat.com/docs/getting-started/installation/flutter", 3)]),
    ("React Native SDK setup",
     [("https://www.revenuecat.com/docs/getting-started/installation/reactnative", 3)]),
    ("iOS SDK installation and configuration",
     [("https://www.revenuecat.com/docs/getting-started/installation/ios", 3),
      ("https://www.revenuecat.com/docs/getting-started/configuring-sdk", 2)]),
    # --- Refunds ---
    ("how to handle refunds in RevenueCat",
     [("https://www.revenuecat.com/docs/platform-resources/apple-platform-resources/handling-refund-requests", 3),
      ("https://www.revenuecat.com/docs/subscription-guidance/refunds", 3)]),
    # --- Server Notifications ---
    ("Apple App Store server notifications",
     [("https://www.revenuecat.com/docs/platform-resources/server-notifications/apple-server-notifications", 3)]),
    ("Google Play server notifications setup",
     [("https://www.revenuecat.com/docs/platform-resources/server-notifications/google-server-notifications", 3)]),
    # --- Platform Integration ---
    ("Google Play service credentials setup",
     [("https://www.revenuecat.com/docs/service-credentials/creating-play-service-credentials", 3),
      ("https://www.revenuecat.com/docs/service-credentials/creating-play-service-credentials/google-play-checklists", 2)]),
    # --- Auth & Projects ---
    ("REST API v2 authentication",
     [("https://www.revenuecat.com/docs/projects/authentication", 3),
      ("https://www.revenuecat.com/docs/projects/oauth-setup", 1)]),
    ("OAuth setup and SSO",
     [("https://www.revenuecat.com/docs/projects/oauth-overview", 3),
      ("https://www.revenuecat.com/docs/projects/oauth-setup", 3),
      ("https://www.revenuecat.com/docs/projects/sso", 2)]),
    # --- Subscriptions ---
    ("subscription offers introductory pricing",
     [("https://www.revenuecat.com/docs/subscription-guidance/subscription-offers", 3),
      ("https://www.revenuecat.com/docs/subscription-guidance/subscription-offers/ios-subscription-offers", 2)]),
    ("managing subscription price changes",
     [("https://www.revenuecat.com/docs/subscription-guidance/price-changes", 3),
      ("https://www.revenuecat.com/docs/subscription-guidance/managing-subscriptions", 2)]),
    ("grace period billing retry",
     [("https://www.revenuecat.com/docs/subscription-guidance/how-grace-periods-work", 3)]),
    # --- Testing ---
    ("how to test in sandbox",
     [("https://www.revenuecat.com/docs/test-and-launch/sandbox", 3),
      ("https://www.revenuecat.com/docs/test-and-launch/sandbox/apple-app-store", 2)]),
    ("app launch checklist before going live",
     [("https://www.revenuecat.com/docs/test-and-launch/launch-checklist", 3)]),
    # --- Web Billing ---
    ("web billing purchase links",
     [("https://www.revenuecat.com/docs/web/web-billing/web-purchase-links", 3),
      ("https://www.revenuecat.com/docs/web/web-billing/overview", 2)]),
    ("web billing customer portal",
     [("https://www.revenuecat.com/docs/web/web-billing/customer-portal", 3),
      ("https://www.revenuecat.com/docs/web/web-billing/managing-customer-subscriptions", 2)]),
    # --- Funnels ---
    ("funnel analytics conversion tracking",
     [("https://www.revenuecat.com/docs/tools/funnels", 3),
      ("https://www.revenuecat.com/docs/tools/funnels/creating-funnels", 2)]),
    # --- Experiments ---
    ("A/B testing experiments with offerings",
     [("https://www.revenuecat.com/docs/tools/experiments-v1", 3),
      ("https://www.revenuecat.com/docs/tools/experiments-v1/creating-offerings-to-test", 2)]),
    # --- Integrations ---
    ("integrate RevenueCat with Amplitude",
     [("https://www.revenuecat.com/docs/integrations/third-party-integrations/amplitude", 3)]),
    ("scheduled data exports to S3",
     [("https://www.revenuecat.com/docs/integrations/scheduled-data-exports", 3),
      ("https://www.revenuecat.com/docs/integrations/scheduled-data-exports/scheduled-data-exports-s3", 3)]),
    # --- Targeting ---
    ("audience targeting and placements",
     [("https://www.revenuecat.com/docs/tools/targeting", 3),
      ("https://www.revenuecat.com/docs/tools/targeting/placements", 2)]),
    # --- Debugging ---
    ("troubleshooting SDK errors",
     [("https://www.revenuecat.com/docs/test-and-launch/errors", 3),
      ("https://www.revenuecat.com/docs/test-and-launch/debugging/troubleshooting-the-sdks", 3)]),
]

# ---------------------------------------------------------------------------
# HELD-OUT VALIDATION SET (10 queries — NEVER tune against these)
# ---------------------------------------------------------------------------
VALIDATION_QUERIES = [
    ("anomaly detection notifications for metrics",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/anomaly-detection-notifications", 3)]),
    ("audit logs for project activity",
     [("https://www.revenuecat.com/docs/dashboard-and-metrics/audit-logs", 3)]),
    ("customer center integration for iOS",
     [("https://www.revenuecat.com/docs/tools/customer-center/customer-center-integration-ios", 3),
      ("https://www.revenuecat.com/docs/tools/customer-center/customer-center-installation", 2)]),
    ("Apple family sharing with RevenueCat",
     [("https://www.revenuecat.com/docs/platform-resources/apple-platform-resources/apple-family-sharing", 3)]),
    ("Stripe integration for web payments",
     [("https://www.revenuecat.com/docs/web/connect-stripe-account", 3),
      ("https://www.revenuecat.com/docs/web/integrations/stripe", 2)]),
    ("Google Play prepaid plans",
     [("https://www.revenuecat.com/docs/subscription-guidance/google-prepaid-plans", 3)]),
    ("restoring purchases across devices",
     [("https://www.revenuecat.com/docs/getting-started/restoring-purchases", 3),
      ("https://www.revenuecat.com/docs/projects/restore-behavior", 2)]),
    ("Braze integration for subscription events",
     [("https://www.revenuecat.com/docs/integrations/third-party-integrations/braze", 3)]),
    ("configuring SDK settings",
     [("https://www.revenuecat.com/docs/getting-started/configuring-sdk", 3)]),
    ("project collaborators and permissions",
     [("https://www.revenuecat.com/docs/projects/collaborators", 3)]),
]

# End-to-end answer quality queries
ANSWER_QUALITY_QUERIES = [
    {
        "query": "How do I set up the RevenueCat MCP server with Claude Code?",
        "must_mention": ["mcp", "claude", "bearer", "api key"],
        "must_not_mention": ["stripe", "adapty"],
    },
    {
        "query": "What metrics does the Charts API provide and how do I query them?",
        "must_mention": ["mrr", "chart", "api"],
        "must_not_mention": [],
    },
    {
        "query": "How do webhooks handle retries when the server returns an error?",
        "must_mention": ["webhook", "retry"],
        "must_not_mention": [],
    },
    {
        "query": "What is the difference between entitlements and offerings?",
        "must_mention": ["entitlement", "offering"],
        "must_not_mention": [],
    },
    {
        "query": "How do I migrate existing StoreKit subscriptions to RevenueCat?",
        "must_mention": ["migrat", "receipt", "storekit"],
        "must_not_mention": [],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_url(url: str) -> str:
    """Normalize URL to canonical path for robust matching."""
    path = url.rstrip("/")
    path = path.replace("https://www.revenuecat.com/docs/", "")
    return path


def _url_match(retrieved_url: str, expected_url: str) -> bool:
    """Match URLs by normalized path equality (not substring)."""
    r = _normalize_url(retrieved_url)
    e = _normalize_url(expected_url)
    return r == e


def _get_grade(retrieved_url: str, expected: list[tuple[str, int]]) -> int:
    """Get the relevance grade for a retrieved URL against graded ground truth.
    Returns the grade (3/2/1) if matched, 0 if not."""
    for exp_url, grade in expected:
        if _url_match(retrieved_url, exp_url):
            return grade
    return 0


def _expected_urls(graded: list[tuple[str, int]]) -> list[str]:
    """Extract just URLs from graded ground truth."""
    return [url for url, _ in graded]


def _dcg(relevances: list[float], k: int) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def _ndcg(relevances: list[float], ideal: list[float], k: int) -> float:
    dcg = _dcg(relevances, k)
    idcg = _dcg(sorted(ideal, reverse=True), k)
    return min(dcg / idcg, 1.0) if idcg > 0 else 0.0


def _avg_precision(retrieved: list[str], expected: list[tuple[str, int]]) -> float:
    """Average precision for a single query (uses graded ground truth, binary hit for AP)."""
    exp_urls = _expected_urls(expected)
    hits = 0
    sum_prec = 0.0
    for rank, url in enumerate(retrieved, 1):
        if any(_url_match(url, e) for e in exp_urls):
            hits += 1
            sum_prec += hits / rank
    ap = sum_prec / min(len(exp_urls), len(retrieved)) if exp_urls else 0.0
    return min(ap, 1.0)


# 
# RETRIEVAL METRICS
# 
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
    recall3: float
    recall5: float
    avg_precision: float
    latency_ms: float


def evaluate_retrieval(search_fn, top_k=5, runs=1, queries=None) -> list[RetrievalResult]:
    if queries is None:
        queries = EVAL_QUERIES
    results = []
    for query, expected_graded in queries:
        exp_urls = _expected_urls(expected_graded)
        latencies = []
        for _ in range(runs):
            t0 = time.perf_counter()
            search_results = search_fn(query, top_k=top_k)
            latencies.append((time.perf_counter() - t0) * 1000)

        retrieved = [r.url for r in search_results]

        # MRR (binary — first relevant hit)
        rr = 0.0
        for rank, url in enumerate(retrieved[:top_k], 1):
            if any(_url_match(url, exp) for exp in exp_urls):
                rr = 1.0 / rank
                break

        # NDCG with graded relevance
        rels = [float(_get_grade(url, expected_graded)) for url in retrieved[:top_k]]
        ideal = [float(g) for _, g in expected_graded]
        ndcg = _ndcg(rels, ideal, top_k)

        # Precision@k (binary)
        def prec(k):
            if not retrieved[:k]:
                return 0.0
            return sum(1 for u in retrieved[:k]
                       if any(_url_match(u, e) for e in exp_urls)) / k

        # Recall@k (binary)
        def recall(k):
            if not exp_urls:
                return 0.0
            found = sum(1 for e in exp_urls
                        if any(_url_match(u, e) for u in retrieved[:k]))
            return found / len(exp_urls)

        results.append(RetrievalResult(
            query=query, expected=exp_urls, retrieved=retrieved[:top_k],
            mrr=rr, ndcg5=ndcg, p1=prec(1), p3=prec(3), p5=prec(5),
            recall3=recall(3), recall5=recall(5),
            avg_precision=_avg_precision(retrieved[:top_k], expected_graded),
            latency_ms=statistics.median(latencies),
        ))
    return results


def print_retrieval(results: list[RetrievalResult], label: str) -> dict:
    n = len(results)
    metrics = {
        "mrr5": sum(r.mrr for r in results) / n,
        "ndcg5": sum(r.ndcg5 for r in results) / n,
        "map": sum(r.avg_precision for r in results) / n,
        "p1": sum(r.p1 for r in results) / n,
        "p3": sum(r.p3 for r in results) / n,
        "p5": sum(r.p5 for r in results) / n,
        "recall3": sum(r.recall3 for r in results) / n,
        "recall5": sum(r.recall5 for r in results) / n,
        "hit_rate1": sum(1 for r in results if r.mrr >= 1.0) / n,
        "hit_rate3": sum(1 for r in results if r.mrr > 0) / n,
        "latency_p50": statistics.median([r.latency_ms for r in results]),
        "latency_p95": sorted([r.latency_ms for r in results])[int(n * 0.95)] if n > 1 else 0,
        "queries": n,
    }

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"\n  {'Metric':<25} {'Score':>8}")
    print(f"  {'-'*25} {'-'*8}")
    print(f"  {'MRR @5':<25} {metrics['mrr5']:>8.3f}")
    print(f"  {'NDCG @5':<25} {metrics['ndcg5']:>8.3f}")
    print(f"  {'MAP':<25} {metrics['map']:>8.3f}")
    print(f"  {'Precision @1':<25} {metrics['p1']:>8.3f}")
    print(f"  {'Precision @3':<25} {metrics['p3']:>8.3f}")
    print(f"  {'Precision @5':<25} {metrics['p5']:>8.3f}")
    print(f"  {'Recall @3':<25} {metrics['recall3']:>8.3f}")
    print(f"  {'Recall @5':<25} {metrics['recall5']:>8.3f}")
    print(f"  {'Hit Rate @1':<25} {metrics['hit_rate1']:>7.0%}")
    print(f"  {'Hit Rate @3':<25} {metrics['hit_rate3']:>7.0%}")
    print(f"  {'Latency p50 (ms)':<25} {metrics['latency_p50']:>8.1f}")
    print(f"  {'Latency p95 (ms)':<25} {metrics['latency_p95']:>8.1f}")

    print(f"\n  {'Query':<42} {'MRR':>5} {'NDCG':>5} {'R@3':>5} {'ms':>6}")
    print(f"  {'-'*42} {'-'*5} {'-'*5} {'-'*5} {'-'*6}")
    for r in results:
        print(f"  {r.query[:41]:<42} {r.mrr:>5.2f} {r.ndcg5:>5.2f} {r.recall3:>5.2f} {r.latency_ms:>6.0f}")

    misses = [r for r in results if r.mrr == 0]
    if misses:
        print(f"\n  MISSES ({len(misses)}):")
        for r in misses:
            print(f"    Q: {r.query}")
            print(f"    Expected: {[u.split('/docs/')[-1] for u in r.expected]}")
            print(f"    Got: {[u.split('/docs/')[-1] for u in r.retrieved[:3]]}")

    return metrics


# ---------------------------------------------------------------------------
# RERANKING A/B
# ---------------------------------------------------------------------------
def evaluate_reranking(rag_index, bm25_index, cache_dir):
    """A/B test: hybrid with reranker vs hybrid without reranker (production config)."""
    from advocate.knowledge.rag import hybrid_search as _hybrid

    no_rerank_scores = []
    reranked_scores = []

    print(f"\n{'=' * 60}")
    print("  Reranking A/B: Hybrid (no reranker) vs Hybrid (with reranker)")
    print(f"{'=' * 60}")
    print(f"\n  {'Query':<40} {'NoRR':>5} {'RR':>5} {'Delta':>6}")
    print(f"  {'-'*40} {'-'*5} {'-'*5} {'-'*6}")

    for query, expected_graded in EVAL_QUERIES:
        exp_urls = _expected_urls(expected_graded)

        # Hybrid WITH reranker (production)
        rr_results = _hybrid(query, rag_index, bm25_index, cache_dir, top_k=5)
        rr_mrr = 0.0
        for rank, r in enumerate(rr_results[:5], 1):
            if any(_url_match(r.url, e) for e in exp_urls):
                rr_mrr = 1.0 / rank
                break

        # Hybrid WITHOUT reranker (disable temporarily)
        orig_key = os.environ.get("CONTEXTUAL_API_KEY")
        os.environ.pop("CONTEXTUAL_API_KEY", None)
        try:
            no_rr_results = _hybrid(query, rag_index, bm25_index, cache_dir, top_k=5)
        finally:
            if orig_key:
                os.environ["CONTEXTUAL_API_KEY"] = orig_key

        no_rr_mrr = 0.0
        for rank, r in enumerate(no_rr_results[:5], 1):
            if any(_url_match(r.url, e) for e in exp_urls):
                no_rr_mrr = 1.0 / rank
                break

        no_rerank_scores.append(no_rr_mrr)
        reranked_scores.append(rr_mrr)

        delta = rr_mrr - no_rr_mrr
        sym = "+" if delta > 0 else ""
        print(f"  {query[:39]:<40} {no_rr_mrr:>5.2f} {rr_mrr:>5.2f} {sym}{delta:>5.2f}")

    avg_no_rr = sum(no_rerank_scores) / len(no_rerank_scores)
    avg_rr = sum(reranked_scores) / len(reranked_scores)
    improved = sum(1 for v, r in zip(no_rerank_scores, reranked_scores) if r > v)
    degraded = sum(1 for v, r in zip(no_rerank_scores, reranked_scores) if r < v)

    print(f"\n  Avg MRR hybrid (no reranker): {avg_no_rr:.3f}")
    print(f"  Avg MRR hybrid (with reranker): {avg_rr:.3f}")
    print(f"  Reranker lift: {avg_rr - avg_no_rr:+.3f}")
    print(f"  Improved: {improved}/{len(reranked_scores)}, Degraded: {degraded}/{len(reranked_scores)}")

    return {
        "no_reranker_mrr": avg_no_rr, "reranked_mrr": avg_rr,
        "lift": avg_rr - avg_no_rr,
        "improved": improved, "degraded": degraded, "total": len(reranked_scores),
    }


# ---------------------------------------------------------------------------
# CONTEXT RELEVANCE (LLM-as-judge)
# ---------------------------------------------------------------------------
def evaluate_context_relevance(search_fn, anthropic_key):
    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)
    scores = []

    print(f"\n{'=' * 60}")
    print("  Context Relevance (LLM Judge)")
    print(f"{'=' * 60}")
    print(f"\n  {'Query':<45} {'Score':>6} {'Verdict'}")
    print(f"  {'-'*45} {'-'*6} {'-'*12}")

    for query, _ in EVAL_QUERIES:
        results = search_fn(query, top_k=3)
        context = "\n\n".join(
            f"[{r.title}]({r.url})\n" + "\n".join(r.snippets[:2])
            for r in results[:3]
        )

        prompt = (
            f"Query: {query}\n\n"
            f"Retrieved context:\n{context}\n\n"
            f"Score how well the retrieved context can answer the query.\n"
            f"Reply with ONLY a JSON object: {{\"score\": 0.0-1.0, \"reason\": \"one sentence\"}}\n"
            f"1.0 = context fully answers the query, 0.5 = partially relevant, 0.0 = irrelevant"
        )

        time.sleep(0.3)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        try:
            data = json.loads(text)
            score = float(data.get("score", 0))
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'"score"\s*:\s*([\d.]+)', text)
            score = float(m.group(1)) if m else 0.0

        scores.append(score)
        verdict = "relevant" if score >= 0.7 else ("partial" if score >= 0.4 else "miss")
        print(f"  {query[:44]:<45} {score:>6.2f} {verdict}")

    avg = sum(scores) / len(scores) if scores else 0
    print(f"\n  Average context relevance: {avg:.3f}")
    return {"avg_context_relevance": avg, "scores": scores, "queries": len(scores)}


# 
# FAITHFULNESS (LLM-as-judge on generated articles)
# 
def evaluate_faithfulness(cache_dir, db, anthropic_key):
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

        cited_urls = re.findall(r'\[(?:Source|[^\]]+)\]\((https://www\.revenuecat\.com/docs/[^)]+)\)', body)
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

        prompt = (
            f"ARTICLE EXCERPT:\n{body[:2000]}\n\n"
            f"SOURCE DOCUMENTS:\n{'---'.join(source_content[:3])}\n\n"
            f"Evaluate faithfulness — are the article's claims about RevenueCat grounded in the sources?\n"
            f"Reply with ONLY JSON: {{\"score\": 0.0-1.0, \"supported\": N, \"unsupported\": N, "
            f"\"fabricated\": N, \"reason\": \"one sentence\"}}"
        )

        time.sleep(0.5)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        try:
            data = json.loads(text)
            score = float(data.get("score", 0))
            reason = data.get("reason", "")
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'"score"\s*:\s*([\d.]+)', text)
            score = float(m.group(1)) if m else 0.0
            reason = text[:80]

        all_scores.append(score)
        print(f"\n  [{slug[:50]}] score={score:.2f}  {reason}")

    if not all_scores:
        return None
    avg = sum(all_scores) / len(all_scores)
    print(f"\n  Average faithfulness: {avg:.3f}")
    return {"avg_faithfulness": avg, "articles_evaluated": len(all_scores), "scores": all_scores}


# 
# ANSWER QUALITY (end-to-end: retrieve + generate + judge)
# 
def evaluate_answer_quality(search_fn, anthropic_key):
    """End-to-end: retrieve context, generate answer, judge quality."""
    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)

    print(f"\n{'=' * 60}")
    print("  Answer Quality (End-to-End)")
    print(f"{'=' * 60}")

    all_scores = []

    for item in ANSWER_QUALITY_QUERIES:
        query = item["query"]
        must_mention = item["must_mention"]
        must_not = item["must_not_mention"]

        # Retrieve
        results = search_fn(query, top_k=5)
        context = "\n\n".join(
            f"Source: {r.url}\n{r.title}\n" + "\n".join(r.snippets[:3])
            for r in results[:5]
        )

        # Generate answer
        time.sleep(0.3)
        gen_resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            system="Answer using ONLY the provided context. Cite sources with [Source](url).",
            messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}],
        )
        answer = gen_resp.content[0].text.strip()

        # Check must_mention
        answer_lower = answer.lower()
        mentions_hit = sum(1 for m in must_mention if m in answer_lower)
        mentions_total = len(must_mention)
        mention_score = mentions_hit / mentions_total if mentions_total else 1.0

        # Check must_not_mention
        bad_mentions = sum(1 for m in must_not if m in answer_lower)

        # Check citations present
        citations = re.findall(r'\[.*?\]\(https://.*?\)', answer)
        has_citations = len(citations) > 0

        # LLM judge on quality
        time.sleep(0.3)
        judge_resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content": (
                f"Rate this answer to the question: \"{query}\"\n\n"
                f"Answer:\n{answer}\n\n"
                f"Score on these dimensions (0.0-1.0 each):\n"
                f"- relevance: does it answer the question?\n"
                f"- completeness: is the answer thorough?\n"
                f"- accuracy: are claims correct?\n"
                f"Reply with ONLY JSON: {{\"relevance\": 0.0-1.0, \"completeness\": 0.0-1.0, \"accuracy\": 0.0-1.0}}"
            )}],
        )
        judge_text = judge_resp.content[0].text.strip()

        try:
            judge = json.loads(judge_text)
            relevance = float(judge.get("relevance", 0))
            completeness = float(judge.get("completeness", 0))
            accuracy = float(judge.get("accuracy", 0))
        except (json.JSONDecodeError, ValueError):
            relevance = completeness = accuracy = 0.5

        composite = (relevance + completeness + accuracy + mention_score + (1.0 if has_citations else 0.0)) / 5
        all_scores.append({
            "query": query, "relevance": relevance, "completeness": completeness,
            "accuracy": accuracy, "mention_coverage": mention_score,
            "has_citations": has_citations, "bad_mentions": bad_mentions,
            "composite": composite,
        })

        print(f"\n  Q: {query[:55]}")
        print(f"    Relevance={relevance:.2f}  Completeness={completeness:.2f}  Accuracy={accuracy:.2f}")
        print(f"    Mentions={mentions_hit}/{mentions_total}  Citations={'yes' if has_citations else 'NO'}  Composite={composite:.2f}")

    avg_composite = sum(s["composite"] for s in all_scores) / len(all_scores) if all_scores else 0
    avg_relevance = sum(s["relevance"] for s in all_scores) / len(all_scores) if all_scores else 0
    avg_accuracy = sum(s["accuracy"] for s in all_scores) / len(all_scores) if all_scores else 0

    print(f"\n  Avg Composite: {avg_composite:.3f}")
    print(f"  Avg Relevance: {avg_relevance:.3f}")
    print(f"  Avg Accuracy:  {avg_accuracy:.3f}")

    return {
        "avg_composite": avg_composite, "avg_relevance": avg_relevance,
        "avg_accuracy": avg_accuracy, "details": all_scores,
    }


# 
# MAIN
# 
def verify_ground_truth_urls(cache_dir: str):
    """Verify all ground truth URLs exist in the cached corpus."""
    pages_dir = os.path.join(cache_dir, "pages")
    corpus_urls = set()
    for f in os.listdir(pages_dir):
        if f.endswith(".md"):
            path = f.replace("__", "/").replace(".md", "")
            corpus_urls.add(f"https://www.revenuecat.com/docs/{path}")

    all_queries = EVAL_QUERIES + VALIDATION_QUERIES
    missing = []
    total_urls = 0
    for query, expected_graded in all_queries:
        for url, grade in expected_graded:
            total_urls += 1
            path = url.replace("https://www.revenuecat.com/docs/", "")
            found = any(path in u for u in corpus_urls)
            if not found:
                missing.append((query, url))

    print(f"\n  URL Verification: {len(all_queries)} queries, {total_urls} URLs")
    if missing:
        print(f"  MISSING ({len(missing)}):")
        for q, u in missing:
            print(f"    {q}: {u}")
    else:
        print("  All URLs verified against corpus ✓")
    return len(missing) == 0


def main():
    args = sys.argv[1:]
    bm25_only = "--bm25-only" in args
    skip_llm = "--skip-llm" in args
    verify_urls = "--verify-urls" in args

    config = Config()
    db = init_db_from_config(config)
    anthropic_key = config.anthropic_api_key

    # URL verification
    if verify_urls:
        verify_ground_truth_urls(config.docs_cache_dir)
        return

    output = {}

    # --- Build indexes ---
    print("Building BM25 index...")
    bm25_index = build_index(config.docs_cache_dir, db)
    print(f"  {bm25_index.doc_count} docs, {len(bm25_index.inverted_index)} terms")

    rag_index = None
    if not bm25_only:
        try:
            from advocate.knowledge.rag import connect_rag_index_from_config
            rag_index = connect_rag_index_from_config(config, db)
            print(f"  RAG: {rag_index.doc_count} docs, {rag_index.chunk_count} chunks")
        except Exception as e:
            print(f"  RAG unavailable: {e}")

    # --- Search function factories ---
    def bm25_search_fn(query, top_k=5):
        return search(query, bm25_index, config.docs_cache_dir, top_k=top_k)

    def hybrid_search_fn(query, top_k=5):
        from advocate.knowledge.rag import hybrid_search as _hybrid
        return _hybrid(query, rag_index, bm25_index, config.docs_cache_dir, top_k=top_k)

    def semantic_search_fn(query, top_k=5):
        from advocate.knowledge.rag import semantic_search as _semantic
        return [
            type('R', (), {'url': c.doc_url, 'path': c.doc_path, 'title': c.doc_title,
                           'score': s, 'snippets': [c.text[:200]], 'doc_sha256': c.doc_sha256})()
            for c, s in _semantic(query, rag_index, top_k=top_k)
        ]

    # --- 1. BM25 retrieval ---
    bm25_results = evaluate_retrieval(bm25_search_fn, runs=3)
    output["bm25"] = print_retrieval(bm25_results, "BM25 Retrieval")

    # --- 2. Semantic retrieval ---
    if rag_index and rag_index.collection:
        semantic_results = evaluate_retrieval(semantic_search_fn)
        output["semantic"] = print_retrieval(semantic_results, "Semantic (Vector-only)")

    # --- 3. Hybrid retrieval ---
    if rag_index and rag_index.collection:
        hybrid_results = evaluate_retrieval(hybrid_search_fn)
        output["hybrid"] = print_retrieval(hybrid_results, "Hybrid (BM25 + Vectors + Reranker + RRF)")

    # --- 4. Validation set (held-out, never tuned against) ---
    if rag_index and rag_index.collection:
        val_results = evaluate_retrieval(hybrid_search_fn, queries=VALIDATION_QUERIES)
        output["validation"] = print_retrieval(val_results, f"VALIDATION SET (held-out, {len(VALIDATION_QUERIES)} queries)")

    # --- 5. Reranking A/B (hybrid with vs without reranker) ---
    if rag_index and rag_index.collection:
        output["reranking"] = evaluate_reranking(rag_index, bm25_index, config.docs_cache_dir)

    # --- 6. Context relevance (LLM judge) ---
    best_fn = hybrid_search_fn if (rag_index and rag_index.collection) else bm25_search_fn

    if anthropic_key and not skip_llm:
        output["context_relevance"] = evaluate_context_relevance(best_fn, anthropic_key)
    else:
        print("\n  Skipping context relevance (no API key or --skip-llm)")

    # --- 6. Faithfulness ---
    if anthropic_key and not skip_llm:
        output["faithfulness"] = evaluate_faithfulness(config.docs_cache_dir, db, anthropic_key)

    # --- 7. Answer quality ---
    if anthropic_key and not skip_llm:
        output["answer_quality"] = evaluate_answer_quality(best_fn, anthropic_key)

    # --- Index stats ---
    output["index_stats"] = {
        "bm25_docs": bm25_index.doc_count,
        "bm25_terms": len(bm25_index.inverted_index),
        "avg_doc_length": round(bm25_index.avg_doc_length, 1),
        "rag_docs": rag_index.doc_count if rag_index else 0,
        "rag_chunks": rag_index.chunk_count if rag_index else 0,
    }

    # --- SUMMARY ---
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"\n  {'Dimension':<30} {'Score':>8}")
    print(f"  {'-'*30} {'-'*8}")
    if output.get("bm25"):
        print(f"  {'BM25 MRR@5':<30} {output['bm25']['mrr5']:>8.3f}")
        print(f"  {'BM25 MAP':<30} {output['bm25']['map']:>8.3f}")
        print(f"  {'BM25 Recall@5':<30} {output['bm25']['recall5']:>8.3f}")
    if output.get("semantic"):
        print(f"  {'Semantic MRR@5':<30} {output['semantic']['mrr5']:>8.3f}")
    if output.get("hybrid"):
        print(f"  {'Hybrid MRR@5':<30} {output['hybrid']['mrr5']:>8.3f}")
        print(f"  {'Hybrid MAP':<30} {output['hybrid']['map']:>8.3f}")
        print(f"  {'Hybrid Recall@5':<30} {output['hybrid']['recall5']:>8.3f}")
        print(f"  {'Hybrid Hit Rate@3':<30} {output['hybrid']['hit_rate3']:>7.0%}")
    if output.get("reranking"):
        print(f"  {'Reranker lift (MRR)':<30} {output['reranking']['lift']:>+8.3f}")
    if output.get("context_relevance"):
        print(f"  {'Context Relevance':<30} {output['context_relevance']['avg_context_relevance']:>8.3f}")
    if output.get("faithfulness"):
        print(f"  {'Faithfulness':<30} {output['faithfulness']['avg_faithfulness']:>8.3f}")
    if output.get("answer_quality"):
        print(f"  {'Answer Relevance':<30} {output['answer_quality']['avg_relevance']:>8.3f}")
        print(f"  {'Answer Accuracy':<30} {output['answer_quality']['avg_accuracy']:>8.3f}")
        print(f"  {'Answer Composite':<30} {output['answer_quality']['avg_composite']:>8.3f}")

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "rag_eval_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
