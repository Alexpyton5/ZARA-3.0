# ZARA Revenue Lab

Experimental revenue engine for ZARA.

## Mission

Generate verified revenue from zero starting capital by running small, measurable experiments. ZARA acts as the parent/orchestrator; experiments survive only when they produce evidence of demand or revenue.

## Economic rules

1. **Zero-capital default** — no paid APIs, ads, hosting, domains, wallets or subscriptions without explicit owner action.
2. **Evidence over optimism** — proposals, traffic and signups are not revenue.
3. **Kill rule** — every experiment has a time budget, success metric and termination condition.
4. **Replication means variants, not uncontrolled clones** — successful experiments may spawn controlled variants inside the project/repository only.
5. **Human custody** — identity, contracts, payment accounts, wallets and withdrawals remain under the owner's control.
6. **Auditability** — all experiment definitions and state changes are committed/versioned.

## Initial experiment portfolio

### EXP-001 — BountyRadar MCP
Build an MCP tool for coding agents that discovers and ranks paid/open-source bounty opportunities. Thesis: instead of competing manually for every bounty, sell the discovery/triage layer to other coding agents.

Revenue path: paid MCP calls / marketplace distribution.

### EXP-002 — Bounty Hunter
Use BountyRadar internally to select only high-EV software bounties that ZARA/Codex can solve and verify with tests.

Revenue path: accepted PR bounty payouts.

### EXP-003 — Pain Miner
Mine repeated public GitHub issues/discussions for narrow, deterministic developer pain points that can become paid MCP/API tools.

Revenue path: new MCP/API products.

## Parent loop

`DISCOVER -> SCORE -> BUILD -> TEST -> PUBLISH -> MEASURE -> KILL/SCALE`

No experiment is allowed to consume unlimited time simply because it is technically interesting.
