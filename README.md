# Freelance Task Validator — GenLayer Project

A full-stack dApp for trustless freelance work verification, powered by GenLayer's AI consensus.

## Live Demo

**Try it now:** https://a200326.github.io/freelance-task-validator-app/

Requires MetaMask connected to GenLayer Studionet.

## What It Does

Freelance work verification usually depends on one party's word against another. This app removes that single point of trust: multiple AI validators independently fetch the submitted evidence URL, evaluate whether it satisfies the task description, and must agree before the contract changes state.

## How It Works

1. **Create Task** — a client defines a task and names a worker's wallet address.
2. **Submit Evidence** — the worker submits a URL pointing to their completed work (e.g. a GitHub Gist, a live demo, a document).
3. **Verify & Resolve** — the client triggers verification. GenLayer validators independently fetch the evidence and reach consensus on `approved` or `rejected`.
4. **Raise Dispute** — if the client disagrees with an approval, they can dispute it.
5. **Resolve Dispute** — a second round of AI consensus acts as arbitration, deciding `worker_wins` or `client_wins`.

Every state transition is enforced on-chain: only the registered worker can submit evidence, only the client can trigger verification or disputes.

## Tech Stack

- **Smart contract**: GenLayer Intelligent Contract (Python), using `gl.eq_principle.strict_eq` for deterministic AI consensus and `gl.nondet.web.request` for live evidence fetching.
- **Frontend**: Single-file static HTML/JS, no build step. Uses [genlayer-js](https://www.npmjs.com/package/genlayer-js) loaded directly from esm.sh, connected via MetaMask.
- **Hosting**: GitHub Pages (fully static, no backend server).

## Contract

Network: GenLayer Studionet
Contract Address: `0xD8d1c944eCE6f8E9381557aCc750De4a733946eb`
Explorer: https://explorer-studio.genlayer.com/address/0xD8d1c944eCE6f8E9381557aCc750De4a733946eb

## Trust Model & Limitations

- Evidence is trusted from a single URL provided by the worker. For stronger guarantees, use immutable sources (e.g. a pinned commit's raw file URL) rather than a branch URL that can change after submission.
- Evidence longer than 3000 characters is truncated; only the first 3000 characters are evaluated (exposed on-chain via `get_max_evidence_chars`).
- HTTP status codes are validated where available; explicit content-type validation was attempted but dropped after testing showed it was unreliable on the current GenVM runtime and caused false negatives. Non-text content is instead caught by the UTF-8 decode step, which fails safely into `fetch_failed`.
- On any fetch, status, or decode failure, task state is left unchanged (not incorrectly rejected) so the client can retry once the evidence is reachable.

## Testing Instructions

1. Open the [live demo](https://a200326.github.io/freelance-task-validator-app/).
2. Connect MetaMask (Studionet).
3. Create a task with your own address as the worker (so you can act as both roles for testing).
4. Submit an evidence URL — for example, a raw GitHub Gist link to a code file.
5. Click "Verify & Resolve" and confirm the transaction. Wait for AI consensus (may take up to a minute).
6. Observe the result: `approved` or `rejected`, or `fetch_failed` if the URL was unreachable (state remains unchanged, retry anytime).
7. If approved, try "Raise Dispute" to see the arbitration flow resolve to `resolved_worker_wins` or `resolved_client_wins`.

## Files

- `contract.py` — the GenLayer Intelligent Contract source.
- `index.html` — the complete frontend (deployed as-is to GitHub Pages).
