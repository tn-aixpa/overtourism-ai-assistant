---
type: Framework
title: Digital Twin Agent knowledge bundle
tags: [index]
---

# Digital Twin Agent knowledge bundle

Curated domain knowledge for the Digital Twin Agent, in [Open Knowledge
Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
(OKF v0.1): one markdown file per concept, a `type` field in the
frontmatter, plain markdown links between concepts. No SDK or database is
required to read it — open any file in this directory in an editor.

This bundle is a single flat glossary — [glossary/](glossary/index.md) —
read by one agent tool, `lookup_glossary`
(`app.agent.nodes.tool_executor.execute_lookup_glossary`). Every concept is
a `GlossaryTerm`: platform concepts (Problem, Proposal, Scenario, ...) and
the territorial-indices framework's own vocabulary (currently just
Territorial Index) are treated identically and cross-link via
`related_terms`. Terms belonging to the territorial-indices framework carry
a `territorial-index` tag if you need to filter to just those.

The concrete, individual territorial indexes (e.g. "Indice di
ricettività") are NOT part of this glossary — they are backend data, not
static domain vocabulary, and are fetched live with the
`get_territorial_index_list` tool
(`app.agent.nodes.tool_executor.execute_get_territorial_index_list`)
instead.

`app.utils.knowledge.build_terminology_block` also consumes this bundle
automatically, to keep generated Italian text terminologically consistent.

Read by `app/utils/okf.py`, a small dependency-free bundle reader. Editing
a `.md` file here (fixing a formula, adding a new index, adding a new
glossary term) takes effect on the next process start — no other code
change is needed, the same way the old single-file `indici
territoriali.md` worked.
