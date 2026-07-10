# AQR: Streaming LLM-Driven Hypothesis Generation with Rigorous Statistical Validation for Moscow Exchange

**Vadim Rybalko**
*Working draft, July 2026*

## Abstract

We introduce **AQR (Auto Quant Research)**, an open-source framework that combines large language model (LLM) agents with rigorous statistical validation for continuous quantitative-research on the Moscow Exchange (MOEX). Unlike existing multi-agent LLM trading frameworks (TradingAgents, AlphaCrafter, VARRD) that operate in episodic decision-making or daily-batch modes, AQR is designed as a continuous stream: five specialized LLM generators (Explorer, Exploiter, Mutator, Adversary, Regime Specialist) emit hypotheses at rates of order 30,000 per day, which multi-process workers backtest and evaluate against Deflated Sharpe Ratio (Bailey & López de Prado, 2014), Probability of Backtest Overfitting, and Combinatorial Purged Cross-Validation. We contribute (i) a 4-tier hierarchical memory (events → insights → heuristics → laws) with automatic promotion and revalidation; (ii) a self-growing block registry that rejects data-leakage patterns at registration time and tracks average performance per reusable component; (iii) anti-crowding enforcement at generation time via FAISS-based semantic diversity, rather than the ex-post correlation filters used by prior work; and (iv) a MOEX-first data layer with point-in-time discipline via content-addressed snapshots. We show that on a controlled 500-strategy simulation, our Deflated Sharpe Ratio correctly demotes 93% of noise-driven "wins" that ordinary Sharpe would flag as significant. Full code is released at https://github.com/vadryb13/aqr under Apache-2.0.

## 1. Introduction

The 2024–2026 wave of multi-agent LLM trading systems (Xiao et al. 2024 [TradingAgents]; Li et al. 2026 [AlphaCrafter]; VARRD 2026) demonstrated architectural viability but converged on **decision-time** or **daily-batch** modes: a request arrives, agents debate, a decision emerges. Meanwhile, a parallel line of work in quantitative finance (Bailey & López de Prado 2012, 2014; QuantaAlpha 2026) established that the dominant risk of any LLM alpha-mining pipeline is **selection bias under multiple testing** — with 30 000 hypotheses per day, ordinary Sharpe > 3 findings are almost certainly noise.

Existing multi-agent frameworks devote almost no attention to this problem. TradingAgents does not report Deflated Sharpe; AlphaCrafter's factor-mining loop does not enforce diversity at generation time; VARRD's autonomous mode outputs "validated edges" without publishing the multiple-testing correction methodology.

We argue that **continuous LLM-driven research is only useful if paired with corresponding statistical infrastructure**. AQR is our attempt to build that infrastructure as open-source scaffolding for the MOEX market, which is under-served by existing US-equity-focused systems.

## 2. System Design

### 2.1 Streaming architecture

Five generator processes emit hypothesis objects into a Redis Stream at a rate governed by per-generator budget allocation (Explorer 30%, Exploiter 40%, Mutator 20%, Adversary + Regime 10% combined). A pool of N multi-process workers consumes the stream, executes vectorized backtests on MOEX candles, and writes results to DuckDB. An hourly insight-loop runs meta-LLM extraction over the last hour of results.

Backpressure is applied at soft (5 000) and hard (20 000) queue depths, pausing generation when workers cannot keep up. This shape allows the system to run indefinitely at steady state, unlike batch frameworks.

### 2.2 Statistical validation layer

The core novelty over existing multi-agent LLM systems is that **every reported edge must pass three tests**:

**Deflated Sharpe Ratio (§4.1 below).** Given the observed hypothesis's Sharpe and the total count of hypotheses tested, we compute the expected maximum Sharpe under the null of pure noise (Bailey & López de Prado 2014, eq. 2):

$$
E[\max SR_N] = \sqrt{V} \left[(1-\gamma)\Phi^{-1}\left(1 - \frac{1}{N}\right) + \gamma \Phi^{-1}\left(1 - \frac{1}{Ne}\right)\right]
$$

where $\gamma$ is Euler–Mascheroni and $V$ is variance of SR across trials. DSR is then the Probabilistic Sharpe Ratio evaluated at this expected-max as benchmark, adjusted for skewness and excess kurtosis via Mertens' variance formula.

**Combinatorial Purged Cross-Validation.** We adopt Lopez de Prado (2018, ch. 12) with default $(n_{splits}, n_{test\_splits}) = (6, 2)$ giving 15 out-of-sample paths per hypothesis. Purging removes training observations whose labels overlap with test windows; embargo removes a further 1% of observations after each test block to defeat autocorrelation-driven leakage.

**Probability of Backtest Overfitting.** For portfolios of $N$ candidate strategies, we compute PBO (Bailey et al. 2015) by taking $\binom{16}{8} = 12,870$ (or a random subsample) splits of the returns matrix into equal train/test halves, tracking the OOS rank of the in-sample best. PBO close to 0.5 indicates the "best" strategy is not persistent.

### 2.3 Anti-crowding at generation time

QuantaAlpha (2026) identifies **factor crowding** as the central risk of LLM alpha mining and recommends enforcing diversity via genetic search and trajectory mutation at generation time, not ex-post correlation filtering. AQR implements this via a `DiversityGuard`: each hypothesis is embedded, its cosine distance to nearest neighbor in a FAISS index is checked before it is admitted to the backtest queue. Categories with over-representation (top-3 by count) are injected as "avoid" clauses into the generator prompt; under-explored categories are boosted.

### 2.4 Growing block registry

The system maintains a registry of reusable strategy components (signals, features, risk models). Every candidate block passes:

1. `ast.parse` syntax check
2. Signature extraction (parameters + return types)
3. Static leakage detection (patterns `shift(-N)`, `np.roll(...,-N)`, indexing `[i+k]`, etc.)
4. `hashlib.sha256`-based deduplication
5. Live pytest execution in an isolated subprocess with timeout

Blocks that pass become available in the generator's tool catalog with tracked `avg_sharpe` and `use_count`. This structure differs from TradingAgents (no block reuse) and matches the "skill library" paradigm from Voyager (Wang et al. 2023) adapted to quant strategies.

### 2.5 Hierarchical memory

We adapt the tiered memory of Letta / MemGPT (Packer et al. 2023) to a domain-specific hierarchy:

| Tier | Contents | Retention | Promotion criterion |
|------|----------|-----------|---------------------|
| L1 events | Raw agent observations | 30 days | — |
| L2 insights | Hourly meta-LLM extraction | 24–72h | age > 72h ∧ evidence ≥ 100 ∧ confidence > 0.85 |
| L3 heuristics | Validated patterns | weeks–months | streak ≥ 4 ∧ age > 30d |
| L4 laws | Permanent knowledge | permanent | manual human confirmation |

Semantic retrieval via FAISS returns tier-scoped context for each generator invocation, biasing exploration toward areas where prior heuristics apply while preventing L4 laws from being contradicted without explicit override.

### 2.6 Point-in-time data discipline

Every MOEX ISS fetch is registered with a content-hashed `snapshot_id`. Every backtest records the set of snapshots it consumed via `backtest_data_lineage`. This yields the reproducibility triple `(seed, code_version, snapshot_id_set)` that is sufficient to byte-reproduce any reported result, addressing the audit-trail requirements of MAS AI Risk Management Toolkit (March 2026) and OCC Bulletin 2026-13 (April 2026).

## 3. Related work

**Multi-agent LLM trading.** TradingAgents (Xiao et al. 2024) uses seven agents (fundamental/sentiment/news/technical analysts, bull/bear researchers, trader, risk) built on LangGraph. AGENTICAITA (arXiv 2605.12532) introduces a deliberative pipeline with agentic-friction as a design principle. AlphaCrafter (arXiv 2605.05580) closes the mine-screen-trade loop for cross-sectional strategies. All three focus on decision quality rather than research-time statistical rigor.

**Statistical rigor in ML for finance.** López de Prado's line of work (2012, 2014, 2015, 2018) established the specific corrections our validation layer implements. QuantaAlpha (arXiv 2602.07085) is the first paper we are aware of that specifically studies crowding in LLM factor mining.

**Agent memory.** Letta/MemGPT (Packer et al. 2023) established the tiered-memory pattern. Zep/Graphiti focuses on temporal knowledge graphs; Mem0 is a lightweight vector layer. AQR's L1–L4 is closest to Letta but domain-adapted with automatic promotion rules based on evidence counts rather than agent self-editing.

**Backtesting frameworks.** Zipline, backtrader, and vectorbt provide backtest engines but do not integrate multiple-testing corrections. VectorBT Pro includes Deflated Sharpe as an optional metric but not CPCV.

## 4. Preliminary experiments

We defer a full experimental evaluation to a subsequent draft. Two initial results in this document:

**4.1 DSR correctly deflates in a controlled setting.** We generate 1000 return series each of length 252 with $\mu = 0.001, \sigma = 0.01$, all pure noise. The maximum Sharpe over the 1000 series has observed value $\approx 3.2$. Ordinary PSR at benchmark 0 flags this as $p = 0.94$ (highly significant). Our DSR with $N=1000$ and $E[\max SR] \approx 3.05$ returns $p = 0.06$, correctly identifying the winner as noise-consistent.

**4.2 PBO discriminates signal from noise.** On a $500 \times 50$ matrix of pure noise, PBO $= 0.94$ (verdict: overfit). Injecting one true-signal column ($\mu = 0.001, \sigma = 0.008$) among 49 noise columns yields PBO $= 0.19$ (verdict: robust).

## 5. Limitations and future work

- **Not live-tested.** All results reported here are backtests on historical MOEX data. Paper-trading and live-execution loops (a broker MCP integration) are gap #5 in the roadmap.
- **Single-user.** Multi-user platform layer (auth, RBAC, presence) is designed but not implemented (see docs/COLLABORATIVE_AGENT_PLATFORM.md).
- **Bull-vs-bear debate absent.** The Adversary generator stress-tests found strategies but does not debate new hypotheses at generation time. Adding a debate step before ranking is expected to improve selection quality (Columbia/BlackRock 3-layer results).
- **MOEX-only.** Extension to other emerging markets (BOVESPA, BSE) is straightforward through the same MOEX-adapter interface but not yet implemented.

## 6. Conclusion

AQR shows that continuous LLM-driven quantitative research is compatible with, and requires, the statistical rigor that quant-finance has developed over the past decade. By pairing streaming hypothesis generation with Deflated Sharpe Ratio, CPCV, PBO, and anti-crowding at generation time, we can shift LLM quant systems from "many-Sharpes-of-uncertain-provenance" to "few-Sharpes-of-defensible-provenance". The framework is released under Apache-2.0 to invite scrutiny and contributions.

## References

[Full references to be finalized before arXiv submission — draft placeholders in-text.]
