# Item 65: IBM VLDB 2026 RAG papers - what Noesek adopted

Sources (both read Sep 23 2026; workshop papers, full texts not yet publicly
posted - implementation grounded in the published abstracts):
- (a) Kashyap, DSouza, Mihindukulasooriya, Samulowitz, "How Much Structure
  Should Agentic Graph Memory Build for Text Retrieval?" (VLDB 2026,
  Agents+Graph workshop) - research.ibm.com publication page.
- (b) "Efficient Context Retrieval for Data-Centric Agents over Heterogeneous
  Sources" (VLDB 2026) - folded in per Ethan's pick.

## Paper findings applied
1. Structure-boundary recipe (a): light entity-centric graph beats both heavy
   schema-rich KG construction (>10x construction cost, abstraction tokens the
   retriever never uses) and flat baselines (no reliable multi-hop evidence
   composition). Noesek already had the winning shape (memory_graph.py);
   this item fixed two gaps the recipe exposes:
   - Common-noun bridge entities: extraction now always includes salient
     lowercase terms ("sister", "espresso"), not only when no proper nouns
     exist. Multi-hop chains need them.
   - Graph RECALL, not just re-rank: entity-linked memories outside the
     baseline top-k now join the candidate pool (context.py
     rank_memories_async). Before, multi-hop evidence the flat baseline
     missed was unreachable no matter how strong the boost.
   - Graph boost fused at full weight (was half): half weight could not lift
     multi-hop evidence above keyword-baseline noise.
2. Layer-utility measurement (a): tests/test_memory_frontier.py codifies the
   paper's recipe as a regression guard - fixed corpus, fixed stack, layered
   vs flat recall on multi-hop queries, determinism check, distractor
   control. Any future retrieval layer must pass this gate.
3. Semantic augmentation > retrieval-algorithm swaps (b): supports keeping
   the deterministic stack and improving write-time extraction quality
   rather than adding retrieval machinery.

## Rejected with reasons
- Heavy/schema-rich KG construction (a): construction cost without retrieval
  use; Noesek's co-occurrence edges are the measured sweet spot.
- Hierarchical LLM retrieval (b): a deterministic preselect + single rerank
  matched it in the paper at 66% fewer tokens; Noesek's memory pool is small
  enough that even the rerank buys little today - revisit if memory_limit
  grows past a few hundred active memories.
- LLM-augmented entity extraction at write time: plausible next step
  (paper a's prompt/model-optimized extraction), but the paper's own rule is
  "require each added layer to improve downstream utility" - it now has a
  measurement gate (test_memory_frontier.py) to prove itself against before
  landing. Tracked as roadmap item 66.
