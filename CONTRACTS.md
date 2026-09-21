# Quorum - specification

One standalone GenLayer Intelligent Contract.
[`contracts/quorum.py`](contracts/quorum.py), deployed exactly as written, no
build step.

Runner pinned in the header:
`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`

---

## Purpose

Put **one closed question** to a set of independent sources, read each source's
answer separately, and establish a fact only when at least `quorum` sources give
the same answer **and no source gives any other**. The question, the answer set
and the threshold are frozen before any source exists.

The failure it catches is the confident answer over a curated pile: one model
call over four documents, no record of which document said what, and a different
answer when one document is quietly left out.

## Consensus

`gl.vm.run_nondet_unsafe`. **Two prompts in one block**, the live sources in
their stored order and then reversed and renumbered.

The block receives the frozen question, the frozen answer set, and the numbered
sources, and returns:

| Field | Type on the wire | Meaning |
|---|---|---|
| `vector` | pipe joined tokens, one per live source | what each source alone answers |
| `because` | short string | leader supplied, sanitised, **not** consensus |

A prompt may answer, per source, one of the frozen answers or `unstated`.
Anything else - a token outside the set, a vector of the wrong length, an answer
that is not a JSON object - makes that pass unusable as a whole.

### The two orders

The reversed pass lists the sources newest first, so its row `[0]` is the stored
row `n-1`. The contract reads the answer back into the stored order, then folds:

```python
def reconcile(forward, reverse_unreversed):
    if forward is None or reverse_unreversed is None:
        return None
    if len(forward) != len(reverse_unreversed):
        return None
    return [forward[i] if forward[i] == reverse_unreversed[i] else UNSTATED
            for i in range(len(forward))]
```

A source read the same way in both orders keeps that reading. A source the two
orders read differently is recorded as `unstated`, exactly as if it had said
nothing. An unusable pass makes the whole reading `unstated` on every source.
Nothing records that the orders disagreed: whether they did is a fact about the
sampling, not about the source, and it is never stored or compared.

With a single live source the two presentation orders are the same prompt. The
second call is then a plain self-consistency check rather than a position check.

### The prompt

The question and every source reach the model through `fence()`, which replaces
`<` `>` and `[` `]` with round brackets. Angle brackets would close a tagged
block; square brackets would forge a row number, because the contract numbers
the sources `[0]`, `[1]` and so on. `number()` fences each source before adding
its own brackets. The count of sources is taken from the list the contract
holds, never from text a party composed, and the answer shape uses placeholders
(`t0|t1|t2`) rather than a concrete vector, because a concrete example is itself
a valid answer a model can echo.

The answer set is the one caller string that reaches the prompt outside a fenced
block, as the list of permitted tokens. `open()` closes its alphabet to letters,
digits, spaces, hyphens and underscores, so it cannot carry a delimiter.

### The validator

1. **Structural honesty, free.** One token per live source, every token from
   the frozen set or `unstated`. Runs before any prompt is spent.
2. **Exact equality on the whole vector.** No tolerance on any source.

`quorum_agrees(a, b, n, answers) == quorum_agrees(b, a, n, answers)`, by
construction. The compared value is exactly the stored value, so agreement
implies the same write; a test sweeps every wire string a leader could send
against every vector a validator could compute to confirm it.

## The quorum rule

`tally(vector, answers, quorum)` is pure and total:

| Verdict | Condition |
|---|---|
| `contested` | two or more different answers from the frozen set appear |
| `established` | exactly one answer appears, from at least `quorum` sources |
| `insufficient` | otherwise |

`unstated` counts for nothing: it is neither a vote nor a dissent. `contested`
is checked first, so no majority overrides a dissent. The reading stores the
per-answer counts, the sources it read, the verdict, and the winning answer if
any.

## State

Every collection is a **top level contract field**. Children carry a parent id
**and the index of the next row with the same parent**, so a parent's rows are
walked by following links rather than by scanning the array.

| Field | Type | Note |
|---|---|---|
| `inquiries` | `DynArray[Inquiry]` | append only |
| `sources` | `DynArray[Source]` | flat; linked through `Source.next` |
| `readings` | `DynArray[Reading]` | flat; linked through `Reading.next` |
| `delegates` | `DynArray[Delegate]` | flat; linked through `Delegate.next` |
| `Inquiry.registrar` | `Address` | owns the inquiry. The identity, not the question text |
| `Inquiry.answers` | `str` | pipe joined, lower case, frozen at `open()` |
| `Inquiry.quorum` | `u256` | frozen at `open()`, `1..8` |
| `Inquiry.version` | `u256` | bumped by every `attest` and `withdraw`; a reading records it |
| `Inquiry.first_src / last_src / n_sources / n_withdrawn` | `u256` | the source chain and how many rows in it are withdrawn |
| `Inquiry.first_reading / last_reading / n_readings` | `u256` | the reading chain |
| `Inquiry.first_delegate / last_delegate / n_delegates` | `u256` | the attester chain |
| `Source.by` | `Address` | the **only** account that may withdraw it |
| `Source.withdrawn` | `bool` | set by `withdraw()`, the row is kept |
| `Reading.version` | `u256` | the inquiry's version when it was read |
| `Reading.sources` | `str` | pipe joined row ids of the sources it read |
| `Reading.vector` | `str` | pipe joined reconciled tokens |
| `Reading.counts` | `str` | pipe joined, aligned with `answers` |
| `Reading.by` | `Address` | who took the reading |
| `Reading.why` | `str` | leader supplied, sanitised, **not** consensus |
| `Delegate.active` | `bool` | cleared on revoke, the row is kept |

### The linked walks

Reading one inquiry's sources costs that inquiry's rows and nothing else on the
contract, however many other inquiries exist. There is no loop over
`len(self.<array>)` anywhere, and a static test asserts it.

### The frozen inquiry

`open()` freezes the question (10 to 300 characters), the answer set (2 to 5
answers, each at most 24 characters and refused rather than truncated, lower
cased, distinct, never the reserved word `unstated`, and drawn from the closed
alphabet above), and the quorum (1 to 8). Caller text has control characters
replaced by spaces and its whitespace collapsed on the way into storage.

### Caps and budgets

| Constant | Value |
|---|---|
| `MAX_SOURCES` | 8 live per inquiry; also bounds the prompt |
| `MIN_SOURCE` / `MAX_SOURCE` | 20 / 700 characters |
| `MIN_QUESTION` / `MAX_QUESTION` | 10 / 300 characters |
| `MAX_ANSWERS` | 5 |
| `MAX_ANSWER` | 24 characters |
| `MAX_SOURCE_ROWS` | 64 per inquiry, withdrawn rows included |
| `MAX_ROWS_PER_ACCOUNT` | 4 attestations per account per inquiry, withdrawn ones included; also the size of the registrar's reserve, the last 4 of the 64 rows |
| `MAX_DELEGATES` | 16 active per inquiry |
| `MAX_DELEGATE_ROWS` | 32 per inquiry, revoked ones included |
| `MAX_REASON` | 140 |

A cap on a chain bounds the cost of walking it. A budget stops one party from
spending what another depends on.

## Sources

- **One live source per account per inquiry.** The registrar is bound by it
  too. A second source from the same account is the first one twice.
- **Only the account that submitted a source may withdraw it.** Not the
  registrar. The row is kept and marked, and `version` moves.
- **The live cap counts live rows.** A withdrawal frees a slot, so a corrected
  source can replace a withdrawn one.
- **Each account may attest at most 4 times on one inquiry**, withdrawn sources
  included, and a non-registrar may not attest once 60 rows exist. One attester
  cycling attest and withdraw can spend only its own allowance.
- **Revoking an attester** stops future attestations and leaves what they
  already said standing, still theirs to withdraw.
- **Closing makes the set final.** No source is added or withdrawn after
  `close()`, so a closed inquiry can always still be read.

## Readings

`decide()` reads the live sources, in stored order, and applies the quorum rule.
It is refused when the inquiry has no live source, and when the live set is the
set the last reading read: the same (account, words) pairs, compared as a sorted
list, whatever row numbers they sit in. So withdrawing a source and re-attesting
the identical text is no change, while any real change - a new source, a
withdrawal, a corrected text, the same words from a different account - reopens
the reading. The guard compares with the last reading, which is what lets the
recourse work: after a dissenter withdraws, the set is the one an earlier
reading saw, and it may be read again because something changed in between.

Every reading is appended and kept, with the row ids it read, so the history of
verdicts over changing source sets is on the record. `verdict()` and `answer()`
report the **latest** reading.

## Authority

| Call | Who | Why |
|---|---|---|
| `open` | anyone | no earlier owner to check against |
| `attest` | registrar or active attester, within the budgets | a planted source would be read like any other |
| `withdraw` | the source's own submitter, while the inquiry is open | a registrar who could remove a dissent would be curating the quorum |
| `authorise` / `revoke` | registrar | the registrar chooses who speaks, never what they say |
| `close` | registrar | stops attestation and withdrawal; a reading may still be taken |
| `decide` | anyone | adds no text, reaches only the verdict the sources imply, and is refused while nothing has changed |

`attest()` and `may_attest()` share one helper, `_attest_refusal()`, which
returns the reason `attest()` would refuse an address or an empty string, so the
view cannot drift from the rule the write enforces.

## API

```python
open(question: str, answers: str, quorum: u256)   # answers pipe joined
attest(inquiry_id: u256, text: str)
withdraw(source_id: u256)
authorise(inquiry_id: u256, who: str)
revoke(inquiry_id: u256, who: str)
close(inquiry_id: u256)
decide(inquiry_id: u256)

verdict(inquiry_id)               -> str
answer(inquiry_id)                -> str
inquiry(inquiry_id)               -> dict
sources_of(inquiry_id)            -> dict
reading(reading_id)               -> dict
readings_of(inquiry_id)           -> dict
registrar(inquiry_id)             -> str
may_attest(inquiry_id, who: str)  -> bool
delegation(inquiry_id)            -> dict
count() / source_count()          -> u256
```

`verdict()` and `answer()` return an empty string for an inquiry nobody has read
yet rather than raising, so a consuming contract has one branch to handle
instead of two. Every read and every write with an out-of-range **or negative**
id raises a `UserError`: Python list indexing accepts `-1` and returns the newest
row, which would hand a caller a different record with nothing failing anywhere.
`may_attest()` looks the inquiry up before it looks at the address, so a bad id
raises there too.

Every address a view returns is the EIP-55 checksummed string on chain. Compare
addresses case-insensitively.

## Reuse

[`lib/quorum_consensus.py`](lib/quorum_consensus.py) holds the pure rules with
no storage and no contract around them. It is **generated** by
`scripts/lift.py` from the contract, and `tests/test_logic.py` compares the two
parsed trees function by function, so a copied rule is always one a deployed
contract actually runs.

Two ideas are worth lifting. `reconcile()`: ask in both presentation orders
inside the leader's own block, and let a source the orders disagree on count for
nothing, storing nothing about the disagreement. `tally()`: make "the sources
agree" mean no source disagrees, and let silence count for nothing.
