"""Architecture tab: what this is, why it exists, and how a question flows through the
system - for technical viewers evaluating the project.
"""
import json

import streamlit as st

_DIAGRAM_SOURCE = r"""flowchart TD
    Q["User question"] --> CACHE{"Asked verbatim<br/>before?"}
    CACHE -->|"yes - exact match"| A["Plain-English answer +<br/>confidence + reasoning trace"]
    CACHE -->|"no"| CQ["classify_query<br/>(LLM: routes the question)"]
    CQ -->|"graph_traversal /<br/>compound_multi_hop"| QN["query_neo4j<br/>(LLM writes Cypher)"]
    CQ -->|"inventory / cost /<br/>contract_status / sales"| QP["query_postgres<br/>(LLM writes SQL)"]
    CQ -->|"disruption / capacity /<br/>cost_impact"| SIM["simulate_scenario<br/>(deterministic Python)"]
    QN -->|"compound_multi_hop<br/>needs both stores"| QP
    QN -->|"else"| VR
    QP --> VR["validate_results<br/>(Corrective-RAG-style check)"]
    SIM --> VR
    VR -->|"invalid, retries left"| CQ
    VR -->|"valid, or gave up"| SY["synthesize<br/>(LLM writes the final answer)"]
    SY --> A
    SY -.-> QC[("query_cache<br/>(Postgres)")]

    QN -.-> N4J[("Neo4j AuraDB<br/>(relationships)")]
    QP -.-> PG[("PostgreSQL / Neon<br/>(transactions)")]

    classDef llm fill:#E8ECFE,stroke:#4F6EF7,color:#0F172A;
    classDef det fill:#FEF3C7,stroke:#F59E0B,color:#0F172A;
    classDef store fill:#F1F5F9,stroke:#94A3B8,color:#0F172A;
    classDef cache fill:#DCFCE7,stroke:#16A34A,color:#0F172A;
    class CQ,QN,QP,SY llm;
    class SIM det;
    class N4J,PG store;
    class CACHE,QC cache;
"""

# This diagram lives inside a Streamlit tab panel, and Streamlit renders every tab's
# content immediately (inactive ones are just display:none, not unrendered) - this
# iframe's document loads and this script runs right away even while its tab is
# hidden. mermaid.render()'s dagre layout needs to measure real text/node dimensions,
# and a display:none container measures everything as zero-size, so layout fails with
# geometry errors ("Could not find a suitable point for the given distance") - this is
# nothing to do with the CDN load or parse timing (the same source parses and renders
# fine in an always-visible page). Fix: don't attempt to render until this document's
# own body actually has non-zero dimensions, i.e. its tab has actually become visible.
_MERMAID_HTML = f"""
<div id="scdt-mermaid-target">Loading diagram...</div>
<script type="module">
  const diagramSource = {json.dumps(_DIAGRAM_SOURCE)};

  function whenVisible(callback) {{
    if (document.body.offsetWidth > 0 && document.body.offsetHeight > 0) {{
      callback();
    }} else {{
      requestAnimationFrame(() => whenVisible(callback));
    }}
  }}

  import("https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs").then((mod) => {{
    const mermaid = mod.default;
    mermaid.initialize({{ startOnLoad: false, theme: "neutral" }});

    function renderDiagram(attempt) {{
      // mermaid.render() can leave temporary DOM artifacts behind on a failed attempt;
      // reusing the same target id across retries can collide with that leftover state,
      // so each attempt gets its own unique id.
      mermaid.render("scdt-mermaid-svg-" + attempt, diagramSource)
        .then(({{ svg }}) => {{ document.getElementById("scdt-mermaid-target").innerHTML = svg; }})
        .catch((err) => {{
          if (attempt < 3) {{
            setTimeout(() => whenVisible(() => renderDiagram(attempt + 1)), 300);
          }} else {{
            document.getElementById("scdt-mermaid-target").innerText =
              "Diagram failed to render after several attempts: " + err.message;
          }}
        }});
    }}
    whenVisible(() => renderDiagram(0));
  }});
</script>
"""


def render_architecture_tab() -> None:
    st.markdown("### About this project")
    st.markdown(
        """
This is a **decision-support layer**, not an ERP replacement — it complements existing
systems (like SAP) by answering conversational, cross-system questions in seconds
instead of requiring someone to write SQL or Cypher, dig through multiple screens, or
wait on a report.

**Why not just ask an LLM directly?** A general-purpose LLM has no access to this
company's actual live data, so it would either refuse to answer or — worse — confidently
make up plausible-sounding numbers. Every answer here is grounded in a real Cypher or SQL
query against real data, shown in the "Show reasoning" panel on every answer, and passed
through a self-correction step before being trusted.
        """
    )

    st.markdown("### How a question is answered")
    st.markdown(
        """
Every question first checks an **exact-match answer cache** (green, above) - if this
literal question (case/whitespace aside) has been asked before, the cached answer comes
back instantly with no LLM call at all. This is deliberately **exact-match only, never
semantic/fuzzy** - a similarity match can conflate two different questions (e.g. "price
of RM1" vs "price of RM2") and hand back a confidently wrong answer, which this app must
never do. The cache is cleared automatically the moment the underlying graph data
changes (a Neo4j import via Graph Explorer), so a cached answer can never go stale.
        """
    )
    st.iframe(_MERMAID_HTML, height=600)

    st.markdown("### Tech stack")
    st.markdown(
        """
- **LangGraph** for the agent's control flow (routing, retries, the graph shown above)
- **Neo4j** (AuraDB) for supplier/product/contract relationships
- **PostgreSQL** (Neon) for transactional data — inventory, billing, shipments, invoices,
  sales, and the exact-match answer cache
- **Groq / OpenRouter / Anthropic / Gemini** as swappable LLM providers, tried in order
  with automatic fallback (or picked manually via the sidebar), so the app runs on
  free-tier models by default
- **Streamlit** for this UI, `streamlit-agraph` for the graph visualizations
        """
    )
