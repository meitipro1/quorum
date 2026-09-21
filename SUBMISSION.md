# Submission

One submission, under **Builder → Intelligent Contracts**. This repository is one
standalone primitive.

---

## Before you submit, in order

1. **Measure, do not estimate.**

   ```bash
   python scripts/measure.py --write
   ```

   Checks the house style, runs the suite, runs the full mutation pass, and
   writes both numbers into README.md. It refuses to write anything if the
   suite is red or a mutation escapes, so a number in the README is always one
   that was checked.

2. **Deploy and exercise.** Through the Studio web interface at
   studio.genlayer.com, following [DEPLOY.md](DEPLOY.md) step by step, with the
   four accounts it asks for. Never put a private key into a file.

3. **Put a refusal on chain, not only a success.** The story the run tells is
   the submission: three sources establish the answer, a fourth dissents and
   the same question comes back `contested`, the dissenter withdraws its own
   source and the fact is established again. Three readings, over three
   source sets, all on the record. A page showing only successes proves the
   file compiles and nothing else.

4. **Prove the address is evidence for this repository.**

   ```bash
   python scripts/verify_deployment.py 0xYourAddress
   ```

   Reads the source back out of the deploy transaction on chain, compares it
   with `contracts/quorum.py` (identical up to line endings, which pasting into
   a web editor rewrites and nothing runs), and runs `genvm-lint lint` on those
   bytes. **A submission is judged on the deployed source**, so a correct
   repository proves nothing on its own if the address points at an earlier
   draft. Exits non-zero if either check fails, or if `genvm-lint` is missing.

5. **Open the explorer page and check it.** It must show a Deploy transaction
   **and** method calls with a Consensus Result beside them, and no failed or
   abandoned transaction.

6. **Paste the address** into README.md and into this file where `{address}`
   appears, then push.

7. **Upload `brand/social.png`** under Settings → General → Social preview.
   GitHub has no API for this.

---

## On chain

Deployed and exercised on studionet at
[`0x5501059c9b300C6d3325F85061658Afc88b1824c`](https://explorer-studio.genlayer.com/address/0x5501059c9b300C6d3325F85061658Afc88b1824c).
Fourteen transactions, every one `FINALIZED`, none failed. Every value below was
read back from the chain with view calls afterwards, not copied from a local
run, and it is exactly what `tests/test_runbook.py` asserts for the same run.

| # | Transaction | Result |
|---|---|---|
| 1 | deploy | finalized |
| 2 | `open("Did the container arrive at the Rotterdam terminal before the 30 June cutoff?", "yes\|no", 2)` | question, answers and quorum frozen |
| 3 | `attest` (registrar) | the terminal gate log |
| 4-6 | `authorise` × 3 | three attesters may speak |
| 7 | `attest` (attester B) | the carrier notification |
| 8 | `attest` (attester C) | the freight invoice |
| 9 | `decide(0)` | `yes\|yes\|unstated` → **`established`, `yes`**, counts `2\|0`, sources `0, 1, 2` |
| 10 | `attest` (attester D) | the forwarder's rolled update |
| 11 | `decide(0)` | `yes\|yes\|unstated\|no` → **`contested`**, no answer, counts `2\|1` |
| 12 | `withdraw` (attester D, its own source) | the row kept and marked, the set changes |
| 13 | `decide(0)` | `yes\|yes\|unstated` → **`established`, `yes`** again |
| 14 | `revoke` (registrar, attester D) | deactivated, the row kept |

### Reproducing the check

```bash
python scripts/verify_deployment.py 0x5501059c9b300C6d3325F85061658Afc88b1824c
```

Reads the source out of the deploy transaction, compares it with
`contracts/quorum.py`, and runs `genvm-lint lint` on those bytes. It reports the
deployed source as identical up to line endings, which pasting into the Studio
editor rewrites and nothing runs.

---

## Title

```
Quorum: one question, several independent sources, one answer or none
```

## Notes (under 1000 characters, the box caps at 1000)

```
Quorum puts one closed question to several independent sources and establishes an answer only when enough of them give it and none gives another. The question, its answer set and the threshold are frozen before any source exists, each source is read on its own, and the block returns one token per source from the frozen set or unstated, so the thing crossing consensus is a vector over a list the contract already holds. It reads twice, in the stored order and reversed, and a source the two orders read differently counts as unstated, neither a vote nor a dissent, so position bias lands on the conservative value and nothing stores how unsure the model was. Agreement between nodes is exact on the whole vector. One live source per account, only the account that submitted a source may withdraw it, the registrar chooses who may attest and cannot remove what anybody said, and a reading is refused while the sources are the ones the last reading read.
```

## Links

```
GitHub:   https://github.com/meitipro/quorum
Contract: https://github.com/meitipro/quorum/blob/main/contracts/quorum.py
Spec:     https://github.com/meitipro/quorum/blob/main/CONTRACTS.md
Decisions https://github.com/meitipro/quorum/blob/main/DECISIONS.md
Tests:    https://github.com/meitipro/quorum/tree/main/tests
Explorer: https://explorer-studio.genlayer.com/address/0x5501059c9b300C6d3325F85061658Afc88b1824c
```

---

## What clears the bar, line by line

The category rejects "thin LLM wrappers" and "generic AI decides X demos".

- **The model never decides.** It answers the same multiple choice question
  about each source, twice. Which sources exist, what the threshold is, what
  counts as dissent, and what the verdict is are all deterministic.
- **Uncertainty is in the value, not the comparison.** A source the two orders
  read differently counts as `unstated`, and nothing stores how unsure the model
  was. There is no tolerance anywhere in the agreement rule, and the compared
  value is exactly the stored value.
- **The validator function is the contribution.** A free structural check before
  any prompt, then exact equality on the whole vector. Explained in
  [CONTRACTS.md](CONTRACTS.md) with the code.
- **The sources are independent by construction.** One live source per account,
  withdrawn only by its owner, never by the registrar. Tested against real
  signatures.
- **Refusing is designed.** `contested` and `insufficient` are the outputs this
  primitive exists to produce, and a reading cannot be retaken over the set the
  last reading read.
- **No attester can lock the others out.** Every chain is capped, each account
  has its own allowance, and the registrar keeps a reserve.
- **Every write is bound to an address.** A structural test asserts it for the
  methods nobody has written yet.
- **No global scans.** Every per-inquiry walk follows links the rows carry. A
  static test asserts there is no loop over a whole storage array.
- **The tests have teeth.** The mutation table in the README is generated by a
  script that refuses to emit a table if anything escapes, the simulator can
  model a leader that lies, and the deployment walkthrough is itself a test.
- **It runs with nothing installed.** `pip install pytest && pytest tests/ -q`.

## The one line worth putting first

**The judgment is hard and the thing crossing consensus is a vector of tokens
from a closed set, one per source.** Everything else in the design follows from
it.
