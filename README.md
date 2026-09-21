<p align="left"><img src="brand/lockup.svg" alt="quorum" height="64"></p>

# Quorum - one question, several independent sources, one answer or none

A reusable GenLayer primitive that puts **one closed question** to a set of
independent sources - documents, reports, attestations - reads each source's
answer separately, and establishes a fact only when enough of them agree and
**none of them dissent**. Nobody decides the fact. The sources do, and the
contract counts them.

- **Contract:** [`contracts/quorum.py`](contracts/quorum.py)
- **Tests:** `pip install pytest && pytest tests/ -q` - nothing else to install
- **Deployed:** [`0x5501059c9b300C6d3325F85061658Afc88b1824c`](https://explorer-studio.genlayer.com/address/0x5501059c9b300C6d3325F85061658Afc88b1824c) on studionet
- **Deploying it yourself:** [DEPLOY.md](DEPLOY.md) - the contract, the demo, and the check to run before submitting
- **Verify a deployment:** `python scripts/verify_deployment.py 0x...` - compares the
  on-chain source with this file and lints it
- **Specification:** [CONTRACTS.md](CONTRACTS.md)
- **Decisions:** [DECISIONS.md](DECISIONS.md)
- **License:** MIT. Copy the agreement rule; that is what it is for.

---

## It is live, and every outcome is on chain

One question, four accounts, four sources and three readings. Every value below
was read back from the chain with view calls, not copied from a local run.

> Did the container arrive at the Rotterdam terminal before the 30 June cutoff?

**Reading 0**, over the gate log, the carrier notification and the freight
invoice:

```
yes | yes | unstated  ->  established, yes      sources 0, 1, 2
```

The invoice mentions the container and says nothing about when it arrived, so
it counts for nothing. Two yeses reach the quorum and no source dissents.

**Reading 1**, after a fourth account attested that the container was rolled to
the next sailing:

```
yes | yes | unstated | no  ->  contested, no answer      counts 2|1
```

Two sources say yes and one says no, and the contract refuses to call that
agreement. **One dissent blocks establishment**, whatever the numbers. That
refusal is the strongest single thing on the explorer page.

**Reading 2**, after the dissenting account withdrew its own source:

```
yes | yes | unstated  ->  established, yes      sources 0, 1, 2
```

The registrar could not remove that source. Only the account that submitted it
could, which is what makes the sources independent rather than curated. The
withdrawn row stays on the record, still naming its author, and the reading it
blocked stays on the record too.

`inquiry(0)`:

```json
{"question": "Did the container arrive at the Rotterdam terminal before the 30 June cutoff?",
 "answers": ["yes", "no"], "quorum": 2, "sources": 4, "live": 3, "readings": 3,
 "version": 5, "verdict": "established", "answer": "yes", "closed": false}
```

Each of the four sources carries a different `by` address, and after the
revocation `delegation(0)` still lists the revoked attester with `active: false`.

Fourteen transactions, every one `FINALIZED`, none failed.

---

## The problem

> Did the container arrive at the Rotterdam terminal before the 30 June cutoff?

A terminal gate log, a carrier notification, a freight invoice and a forwarder's
update all bear on it, and they do not always say the same thing. Ask a model
the question with all four in front of it and it returns one confident answer
with **no record of which source said what**, and a different answer when one
source is quietly dropped from the pile.

Two things are wrong with that. The answer cannot be audited, because nobody can
see how each document was read. And the pile can be curated, because whoever
assembles it decides what the model sees.

## How consensus is used

Quorum never asks the question of the pile. The question, its answer set and its
threshold are frozen when the inquiry is opened and belong to the contract. The
block sees the numbered sources and answers **one token per source**: which of
the frozen answers *that source alone* gives, or `unstated` if it does not speak
to the question.

> The judgment is hard. Read a terminal log and decide whether it actually
> answers "before the 30 June cutoff", rather than merely mentioning Rotterdam.
>
> **The thing that crosses consensus is a vector of tokens from a closed set,
> one per source.**

"Established" is then arithmetic the contract does over that vector against a
threshold frozen in advance.

### The leader resolves its own uncertainty first

The block reads the sources **twice** - once in their stored order and once
reversed and renumbered - and the two readings of each source must match.

```python
def reconcile(forward, reverse_unreversed):
    if forward is None or reverse_unreversed is None:
        return None
    if len(forward) != len(reverse_unreversed):
        return None
    return [forward[i] if forward[i] == reverse_unreversed[i] else UNSTATED
            for i in range(len(forward))]
```

A source the two orders read differently is recorded as `unstated`, exactly as
if it had said nothing: it is not a vote for any answer and it is not a
dissent. Nothing records that the leader was unsure. That would be a fact about
the sampling rather than the source, and a separate token carrying it would
split two nodes that both ended up counting the source for nothing - one because
its two orders disagreed, one because it read the source as silent twice - over
a difference no rule acts on.

**Uncertainty belongs in the value, never in the comparison.** The alternative -
keep a precise stored vector and let the agreement rule forgive a source -
produces a verdict that reads decisive while the nodes privately disagreed.

### The validator, in two layers

```python
# LAYER 1 -- structural honesty. Costs nothing, runs before any prompt.
#   One token per live source, every token from the frozen answer set or
#   `unstated`. Checked against data the validator already holds. A malformed
#   proposal dies before any inference is spent on it.

# LAYER 2 -- exact equality on the whole vector.
#   Not "we both found enough yeses". The same reading of every source. Two
#   nodes that both counted two yeses while reading different sources as the
#   yeses have agreed about nothing worth recording, because which source said
#   what is the record.
```

There is deliberately **no tolerance** anywhere in layer 2, and the thing
compared is exactly the thing stored.

## The quorum rule

Derived deterministically from the agreed vector:

| Verdict | Condition |
|---|---|
| `established` | some answer is given by at least `quorum` sources **and no source gives any other answer** |
| `contested` | two or more different answers appear, whatever the numbers |
| `insufficient` | neither: not enough sources speak to the question |

`unstated` counts for nothing. **One dissenting source blocks establishment**,
because a primitive whose job is to say "the sources agree" must not say it
while one of them disagrees. Strict on purpose.

## Each source belongs to whoever submitted it

This is the rule the whole primitive rests on. The registrar controls **who**
may attest. Each attester controls **their own words**:

- one live source per account per inquiry - a second from the same account is
  the first one twice;
- only the account that submitted a source may withdraw it. **Not the
  registrar.** A registrar who could remove a dissenting source would be
  curating the quorum;
- revoking an attester stops future attestations and leaves what they already
  said standing, still theirs to withdraw.

That is what makes the sources independent rather than curated, and it is
tested against real signatures in the integration suite, not only in the
simulator.

## A reading is a snapshot of one source set

`decide()` is open to anyone. Every reading records exactly which sources it
read, and `decide()` is refused while the live sources are the ones the last
reading read - the same accounts saying the same words. A caller cannot ask
until the answer suits, and withdrawing a source and re-attesting the identical
text is recognised as no change at all. Adding a source, withdrawing one, or
correcting one reopens the reading, and every reading ever taken stays on the
record with the sources it saw.

If one node's model returns an unusable answer, the other nodes disagree with it
and the network rotates to another leader. Only an answer no node could use is
stored, and then as a reading that found nothing, which is what it was.

## Closing makes the source set final

`close()` stops attestation **and withdrawal**. A closed inquiry's sources are
final, so it can always still be read: without that, the holder of the last live
source could empty a closed inquiry and nobody could ever read it again.

## Why this is not a thin LLM wrapper

The model never decides whether the fact is established. **It answers the same
multiple choice question about each source, twice.** Which sources exist, what
the threshold is, what counts as dissent, whether the answer is established,
contested, or insufficient - all deterministic, all computed from storage the
block never sees.

Swap in a worse model and the mechanism still works. It reads fewer sources
consistently, so fewer count, which establishes less, which is the correct
response to a worse model.

## Who may write to an inquiry

| Call | Who |
|---|---|
| `open` | anyone. The caller becomes the registrar of the new inquiry |
| `attest` | the registrar, or an address the registrar has authorised, within the budgets below |
| `withdraw` | the account that submitted that source, and not once the inquiry is closed |
| `authorise` / `revoke` | the registrar alone |
| `close` | the registrar alone. Stops attestation and withdrawal; a reading may still be taken |
| `decide` | anyone, deliberately, and refused while nothing has changed |

Every source stores the address that submitted it, and every reading stores the
address that took it and the sources it read.

### Budgets, so no attester can lock the others out

| Budget | Value |
|---|---|
| live sources per inquiry | 8 |
| source rows per inquiry, withdrawn ones included | 64 |
| of those, reserved for the registrar alone | the last 4 |
| attestations one account may make on one inquiry, withdrawn ones included | 4 |
| active attesters per inquiry | 16 |
| attester rows per inquiry, revoked ones included | 32 |

A withdrawal keeps its row, so the chain every walk follows grows with each
attestation. Without an allowance, one attester cycling attest and withdraw
could spend all 64 rows and lock everybody else out, the registrar included.

## The API

```python
open(question, answers, quorum)    # anyone. answers pipe joined, frozen here
attest(inquiry_id, text)           # registrar or authorised attester, one live each
withdraw(source_id)                # the source's own submitter, while open
authorise(inquiry_id, who)         # registrar only
revoke(inquiry_id, who)            # registrar only
close(inquiry_id)                  # registrar only
decide(inquiry_id)                 # anyone. refused while nothing has changed

verdict(inquiry_id)      -> str    # established | contested | insufficient | ""
answer(inquiry_id)       -> str    # the established answer, or ""
inquiry(inquiry_id)      -> dict   # question, answers, quorum, live sources, latest verdict
sources_of(inquiry_id)   -> dict   # every source, withdrawn ones too, each with its owner
reading(reading_id)      -> dict   # the vector, the counts, who took it, which sources it read
readings_of(inquiry_id)  -> dict   # every reading ever taken, oldest first
registrar(inquiry_id)    -> str
may_attest(id, who)      -> bool   # would attest() accept that address right now
delegation(inquiry_id)   -> dict
count() / source_count()
```

`may_attest()` asks the same question `attest()` asks, through the same helper:
authority, the closed flag, the caps, the registrar's reserve, the account's own
allowance and the one-live-source rule. It cannot see the text, which is the one
thing `attest()` checks that a view could not.

## Using it from another contract

```python
@gl.contract_interface
class Quorum:
    class View:
        def verdict(self, inquiry_id: int) -> str: ...
        def answer(self, inquiry_id: int) -> str: ...
        def registrar(self, inquiry_id: int) -> str: ...

q = Quorum(QUORUM_ADDR).view()

# bind to the address, never to the question text. On chain every address a
# view returns is the EIP-55 checksummed string, so compare case-insensitively.
if q.registrar(iid).lower() != str(expected_asker).lower():
    raise ...

# act only on a fact the sources actually established
if q.verdict(iid) == "established" and q.answer(iid) == "yes":
    self._release_payment()
```

`verdict()` and `answer()` return an empty string rather than raising for an
inquiry nobody has read yet, so the caller has one branch to handle instead of
two.

---

## Running the tests

```bash
pip install pytest
pytest tests/ -q
```

Nothing else is needed. `tests/glsim.py` is a small GenVM stand-in, so the unit,
end-to-end and runbook suites run with no Studio and no network.
`tests/test_runbook.py` replays [DEPLOY.md](DEPLOY.md) step by step and asserts
every value it tells you to expect, so the walkthrough is tested like the code.

The integration suite is **opt in**, and deliberately so. It skips when
`genlayer-test` is absent, and it also skips when `genlayer-test` is present
without a Studio to talk to - otherwise anybody who reviews GenLayer contracts,
and therefore has the plugin installed, would see a wall of connection errors on
a repository that promises an offline run. To run it against a live Studio:

```bash
pip install genlayer-test
GENLAYER_STUDIO=1 gltest --network studionet tests/test_integration.py
```

<!-- measured:tests -->
`pytest tests/ -q` reports **155 passed, 1 skipped**, and every one of the **106** mutations below is caught.
<!-- /measured:tests -->

### The tests have teeth

A passing count is a claim. The table below is evidence: every row is a real edit
to the contract that removes a defence, and the test named beside it is the one
that failed. It is generated by `scripts/mutate.py`, which regenerates the
lifted library from each mutant before the suite runs, so no parity check can
stand in for a behavioural test, and which refuses to emit a table if anything
escapes.

<!-- measured:mutations -->
| Mutation | Caught by |
|---|---|
| a source the two orders read differently keeps the forward reading | `test_a_source_the_two_orders_read_differently_is_neither_vote_nor_dissent` |
| a source the two orders read differently keeps the reversed reading | `test_a_source_the_two_orders_read_differently_is_neither_vote_nor_dissent` |
| the second pass never runs, so nothing is mirrored | `test_a_source_the_two_orders_read_differently_is_neither_vote_nor_dissent` |
| the reversed reading is not read back into the stored order | `test_enough_agreeing_sources_establish_the_answer` |
| an unusable pass falls back on the forward reading alone | `test_an_unusable_pass_reads_nothing` |
| an unusable pass read as a unanimous first answer | `test_an_unusable_pass_reads_nothing` |
| a non-object answer crashes the block instead of being unusable | `test_a_prompt_answer_that_is_not_an_object_is_unusable_not_fatal` |
| any token a model returns is accepted | `test_only_a_frozen_answer_or_unstated_survives` |
| a partly unusable answer read as silence | `test_the_free_layer_is_actually_free` |
| a vector of the wrong length parsed anyway | `test_parse_vector_is_all_or_nothing` |
| a dissent no longer blocks establishment: the majority wins | `test_one_dissent_makes_it_contested` |
| the quorum threshold ignored | `test_below_quorum_is_insufficient` |
| an established answer reported with no winner | `test_enough_agreeing_sources_establish_the_answer` |
| silence counted as a vote for the first answer | `test_enough_agreeing_sources_establish_the_answer` |
| one source forgiven, the Winnow defect | `test_nodes_reading_a_source_differently_do_not_agree` |
| agreement loosened to the same tally over different sources | `test_same_tally_different_rows_is_still_a_disagreement` |
| the validator's own reading ignored | `test_nodes_reading_a_source_differently_do_not_agree` |
| the free structural layer removed | `test_the_free_layer_is_actually_free` |
| a leader that rolled back is read as if it had answered | `test_a_leader_that_rolled_back_is_refused_and_nothing_is_stored` |
| a leader payload that is not a mapping is read anyway | `test_a_leader_payload_that_is_not_a_mapping_is_refused_for_free` |
| a wrong length vector passes the structural check | `test_the_free_layer_checks_length_and_tokens` |
| a token outside the frozen set passes the structural check | `test_the_free_layer_checks_length_and_tokens` |
| a reading can be retaken over the same sources | `test_a_reading_cannot_be_retaken_over_the_same_sources` |
| the replay guard compares row numbers, not what the sources say | `test_withdrawing_and_re_attesting_the_same_words_is_not_a_change` |
| the replay guard ignores who said it | `test_the_same_words_from_another_account_are_a_different_source` |
| a reading does not record which sources it read | `test_a_reading_cannot_be_retaken_over_the_same_sources` |
| an attestation does not move the version | `test_the_thirteen_writes_produce_what_the_page_promises` |
| a withdrawal does not move the version | `test_the_thirteen_writes_produce_what_the_page_promises` |
| the registrar allowed to withdraw anybody's source | `test_the_registrar_cannot_withdraw_somebody_else_s_source` |
| withdraw left unauthenticated | `test_the_registrar_cannot_withdraw_somebody_else_s_source` |
| a withdrawn source is still read | `test_withdrawing_and_re_attesting_the_same_words_is_not_a_change` |
| withdrawing twice allowed, so the count drifts | `test_withdrawing_twice_is_refused` |
| the withdrawn count not kept | `test_a_withdrawn_source_stays_on_the_record_marked` |
| a closed inquiry's sources can still be withdrawn | `test_a_closed_inquiry_s_sources_are_final` |
| a second live source from the same account accepted | `test_one_live_source_per_account` |
| a withdrawn source still blocks a corrected one | `test_withdrawing_and_re_attesting_the_same_words_is_not_a_change` |
| an account's allowance of rows removed | `test_one_account_may_attest_at_most_four_times` |
| an account's withdrawn rows not counted against its allowance | `test_one_account_may_attest_at_most_four_times` |
| the registrar's reserve removed | `test_the_last_four_rows_are_the_registrar_s_and_the_chain_stops_at_64` |
| the registrar held to its own reserve | `test_the_last_four_rows_are_the_registrar_s_and_the_chain_stops_at_64` |
| the source row cap removed | `test_the_last_four_rows_are_the_registrar_s_and_the_chain_stops_at_64` |
| the live source cap removed, so an unbounded prompt is built | `test_the_source_cap_counts_live_rows` |
| the live source cap counts withdrawn rows | `test_the_last_four_rows_are_the_registrar_s_and_the_chain_stops_at_64` |
| a closed inquiry still accepts sources | `test_a_closed_inquiry_takes_no_more_sources_but_can_still_be_read` |
| the attester row cap removed, so the chain grows forever | `test_the_attester_chain_is_capped_at_32_rows_revoked_ones_included` |
| the active cap not checked for a new attester | `test_the_active_cap_survives_a_revoke_and_reauthorise_cycle` |
| the active cap not re-checked when a revoked attester is reactivated | `test_the_active_cap_survives_a_revoke_and_reauthorise_cycle` |
| the active cap counted in the same pass that finds the row | `test_the_active_cap_survives_a_revoke_and_reauthorise_cycle` |
| a stranger's source accepted | `test_a_stranger_cannot_attest` |
| a revoked attester still counted as authorised | `test_a_revoked_attester_cannot_attest_and_their_source_stays` |
| the source's owner not recorded | `test_withdrawing_and_re_attesting_the_same_words_is_not_a_change` |
| the reading does not record who took it | `test_anyone_may_decide_and_that_is_deliberate` |
| delegation not scoped to the inquiry it was granted on | `test_delegation_is_scoped_to_one_inquiry` |
| an attester allowed to appoint further attesters | `test_an_attester_may_not_authorise_revoke_or_close` |
| an attester allowed to revoke | `test_an_attester_may_not_authorise_revoke_or_close` |
| an attester allowed to close the inquiry | `test_an_attester_may_not_authorise_revoke_or_close` |
| may_attest() drifting from the rule attest() enforces | `test_may_attest_follows_authority` |
| may_attest() checks the address before the inquiry exists | `test_may_attest_raises_on_a_bad_id_like_every_read` |
| a malformed attester address passed to Address() by authorise | `test_a_malformed_attester_address_is_refused_cleanly` |
| a malformed attester address passed to Address() by revoke | `test_a_malformed_attester_address_is_refused_cleanly` |
| the registrar authorised as its own attester | `test_attester_refusals_are_clean` |
| authorising twice allowed | `test_attester_refusals_are_clean` |
| revoking an address that was never an attester silently succeeds | `test_attester_refusals_are_clean` |
| revoking twice allowed | `test_attester_refusals_are_clean` |
| closing twice allowed | `test_closing_twice_is_refused` |
| duplicate answers allowed | `test_bad_inquiries_are_refused_with_the_reason` |
| the reserved token allowed as an answer | `test_bad_inquiries_are_refused_with_the_reason` |
| the answer alphabet left open, so an answer can carry a delimiter | `test_open_refuses_an_answer_that_could_carry_a_delimiter` |
| an over-long answer accepted | `test_an_answer_is_never_truncated` |
| the answer cap removed | `test_bad_inquiries_are_refused_with_the_reason` |
| an inquiry allowed with a single answer | `test_bad_inquiries_are_refused_with_the_reason` |
| a quorum above the live source cap allowed, so nothing can establish | `test_bad_inquiries_are_refused_with_the_reason` |
| a zero quorum allowed | `test_bad_inquiries_are_refused_with_the_reason` |
| a question too short to be one accepted | `test_bad_inquiries_are_refused_with_the_reason` |
| the question length cap removed | `test_bad_inquiries_are_refused_with_the_reason` |
| an over-long question silently cut instead of refused | `test_bad_inquiries_are_refused_with_the_reason` |
| a fragment accepted as a source | `test_bad_sources_are_refused_with_the_reason` |
| the source length cap removed | `test_bad_sources_are_refused_with_the_reason` |
| the source walk replaced by a scan of every inquiry's rows | `test_two_inquiries_never_see_each_other_s_sources` |
| the previous last source not linked to the new one | `test_sources_land_and_are_walked_in_order` |
| the previous reading not linked to the new one | `test_a_reading_records_which_sources_it_read` |
| the previous attester not linked to the new one | `test_sources_land_and_are_walked_in_order` |
| the inquiry bounds check removed | `test_may_attest_raises_on_a_bad_id_like_every_read` |
| negative inquiry ids allowed through to Python list indexing | `test_may_attest_raises_on_a_bad_id_like_every_read` |
| negative source ids allowed through to Python list indexing | `test_writes_with_a_bad_id_are_refused_cleanly` |
| negative reading ids allowed through to Python list indexing | `test_a_read_with_a_bad_id_is_a_user_error` |
| the reason sanitiser disabled | `test_a_lying_leader_s_reason_is_sanitised_on_the_way_in` |
| control characters left in reasons | `test_a_lying_leader_s_reason_is_sanitised_on_the_way_in` |
| control characters left in caller text | `test_caller_text_is_cleaned_on_the_way_into_storage` |
| the stored reason taken raw from the leader | `test_a_lying_leader_s_reason_is_sanitised_on_the_way_in` |
| the prompt fence removed, so a source can forge a block | `test_number_separates_sources_by_a_blank_line_and_fences_each` |
| the fence deletes instead of replacing | `test_number_separates_sources_by_a_blank_line_and_fences_each` |
| only the tag brackets fenced, so a source can forge a row number | `test_number_separates_sources_by_a_blank_line_and_fences_each` |
| a source reaches the model unfenced | `test_number_separates_sources_by_a_blank_line_and_fences_each` |
| the question reaches the model unfenced | `test_the_question_is_fenced_too` |
| the count read from composed text instead of the list | `test_the_count_comes_from_the_list_not_from_the_text` |
| the answer example is itself a valid answer | `test_the_example_is_sized_to_the_list_and_is_not_itself_an_answer` |
| unstated not offered as a choice | `test_the_prompt_lists_the_frozen_answers_and_unstated` |
| the read-each-source-alone instruction dropped from the prompt | `test_the_prompt_tells_the_model_to_read_each_source_alone` |
| the data framing dropped from the prompt | `test_the_prompt_frames_the_blocks_as_data` |
| a nested mapping returned from the block | `test_enough_agreeing_sources_establish_the_answer` |
| a bool returned from the block | `test_enough_agreeing_sources_establish_the_answer` |
| a collection nested back into a storage dataclass | `TypeError at import` |
| an int storage field | `TypeError at import` |
| a storage field declared twice | `test_no_storage_field_or_method_is_declared_twice` |
| a prompt moved outside the block, which genvm-lint refuses | `test_enough_agreeing_sources_establish_the_answer` |
<!-- /measured:mutations -->

The simulator can also model **a leader that lies**: `set_leader_payload()` puts
a value on the wire that `leader_fn` would never return, which is the only way to
exercise the checks a validator runs against a peer it does not trust. Without
it, every one of those checks is unreachable in testing and a defence that cannot
be exercised looks identical to one that is not there.

## Design rules

- **The block returns tokens, never an outcome.** One token per source, from a
  set the contract froze.
- **Uncertainty enters the stored value, and only the value.** A source the two
  orders read differently counts as `unstated`. Nothing stores how unsure the
  model was.
- **Exact equality between nodes, on exactly what is stored.** No tolerance, on
  any source.
- **Each source belongs to whoever submitted it.** One live source per account,
  withdrawn only by its owner, never by the registrar.
- **A reading is a snapshot of one source set** and cannot be retaken over the
  set the last reading read.
- **No attester can spend a budget another depends on.** Every chain is capped,
  each account has its own allowance, and the registrar keeps a reserve.
- **Every write is bound to an address**, and a structural test asserts it for
  the methods nobody has written yet.
- **Untrusted text is fenced at the prompt boundary.** `fence()` neutralises `<`
  `>`, which close a tag, and `[` `]`, which number a row, so a source can forge
  neither. Replace, never delete, and at the boundary only. The answer set is
  the one caller string that reaches the prompt outside a fenced block, so its
  alphabet is closed at `open()` instead.
- **No global scans.** Every per-inquiry walk follows links the rows carry.
- **Refusing is designed.** `contested` and `insufficient` are the outputs this
  contract exists to produce.
- **No web access.** Every input is text the caller supplies, which removes an
  entire class of deployment failure.

## Further reading in this repository

- [CONTRACTS.md](CONTRACTS.md) - the full specification: purpose, consensus,
  state model, API, reuse
- [DECISIONS.md](DECISIONS.md) - engineering decisions, what they cost, and what
  an audit found
- [lib/quorum_consensus.py](lib/quorum_consensus.py) - the agreement rules on
  their own, to be copied. Generated by `scripts/lift.py` and checked for drift
  by the suite
- [brand/](brand/) - the mark, the lockup, the palette, and the social card

## Related work

Separate primitives, built to the same standard and submitted independently:
[Accrue](https://github.com/meitipro/accrue) - a credential that can only be
earned.
[Assent](https://github.com/meitipro/assent) - an agreement forms only when the
acceptance matches the offer.
[Covenant](https://github.com/meitipro/covenant) - a breach is cured within the
window or it becomes a default.
[Ratchet](https://github.com/meitipro/ratchet) - a published commitment that can
only ever be tightened.
[Keystone](https://github.com/meitipro/keystone) - an ordering built one pair at
a time that cannot contradict itself.
[Recant](https://github.com/meitipro/recant) - self-consistency across a record
of statements.

They share an author and a discipline, not a codebase. Each deploys, tests and is
used entirely on its own.

---

Published by [InferNode](https://x.com/Infer_node).
