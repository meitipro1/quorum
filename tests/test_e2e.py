"""
End-to-end tests. The real contract file, executed.

tests/test_logic.py covers the pure rules. This file covers everything they
cannot reach: the linked walks, the two-pass block, the quorum arithmetic over
storage, the replay guard, the ownership of each source, the budgets, the
authority rules, and every branch that only fires when the leader and a
validator see different things.

    pytest tests/test_e2e.py -v
"""

import ast
import collections
import pathlib
import re

import pytest

import glsim as S

CONTRACT_PATH = "contracts/quorum.py"

Q = "Did the container arrive at the Rotterdam terminal before the 30 June cutoff?"
GATE = "Terminal gate log: container MSKU7712389 discharged and gated in at Rotterdam Maasvlakte II on 28 June, 14:02."
CARRIER = "Carrier notification: vessel berthed Rotterdam 28 June; MSKU7712389 available for pickup from 29 June."
INVOICE = "Invoice 4471 for freight charges on MSKU7712389, issued 2 July, payable within 30 days."
ROLLED = "Forwarder update: MSKU7712389 was rolled to the next sailing and did not discharge at Rotterdam until 4 July."
CORRECTED = "Corrected carrier notification: berthed 27 June, MSKU7712389 available for pickup from 28 June."


def passes(first_text, forward, last_text, reverse, because="read from the sources"):
    """Mock both presentation orders. The forward prompt opens with the oldest
    live source, the reversed one with the newest; a mock keys on that."""
    return {
        "[0] " + first_text: {"readings": forward, "because": because},
        "[0] " + last_text: {"readings": reverse, "because": because},
    }


def stable(texts, vector):
    """Both orders read every source the same way."""
    rev = "|".join(reversed(vector.split("|")))
    return passes(texts[0], vector, texts[-1], rev)


def addr(i):
    return "0x" + ("%02x" % (0x30 + i)) * 20


class TestQuorum:
    REGISTRAR = "0x" + "11" * 20
    W1 = "0x" + "22" * 20
    W2 = "0x" + "23" * 20
    W3 = "0x" + "24" * 20
    STRANGER = "0x" + "99" * 20

    def deploy(self, quorum=2):
        c = S.deploy(CONTRACT_PATH)
        S.call(c, "open", Q, "yes|no", quorum)
        return c

    def as_(self, c, who, method, *args):
        S.set_sender(who)
        try:
            return S.call(c, method, *args)
        finally:
            S.set_sender(self.REGISTRAR)

    def attest_as(self, c, who, text, inquiry=0):
        return self.as_(c, who, "attest", inquiry, text)

    def three(self, c):
        """Registrar plus two attesters, three live sources."""
        S.call(c, "attest", 0, GATE)
        S.call(c, "authorise", 0, self.W1)
        S.call(c, "authorise", 0, self.W2)
        self.attest_as(c, self.W1, CARRIER)
        self.attest_as(c, self.W2, INVOICE)

    def mocks(self, prompts, v_prompts=None):
        S.set_mocks(leader_pages={}, leader_prompts=prompts, validator_pages={},
                    validator_prompts=v_prompts if v_prompts is not None else prompts)

    # -- the inquiry --------------------------------------------------------

    def test_an_inquiry_opens_frozen(self):
        c = self.deploy()
        q = c.inquiry(0)
        assert q["answers"] == ["yes", "no"] and q["quorum"] == 2
        assert q["live"] == 0 and q["verdict"] == ""

    def test_sources_land_and_are_walked_in_order(self):
        c = self.deploy()
        self.three(c)
        rows = c.sources_of(0)["sources"]
        assert [r["text"] for r in rows] == [GATE, CARRIER, INVOICE]
        assert c.inquiry(0)["live"] == 3

    def test_caller_text_is_cleaned_on_the_way_into_storage(self):
        c = self.deploy()
        S.call(c, "attest", 0, "Terminal\tgate log:" + chr(0) + "gated in\non 28 June.")
        assert c.sources_of(0)["sources"][0]["text"] == "Terminal gate log: gated in on 28 June."

    # -- the quorum rule over storage ----------------------------------------

    def test_enough_agreeing_sources_establish_the_answer(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "established" and c.answer(0) == "yes"
        r = c.reading(0)
        assert r["counts"] == "2|0" and r["sources_read"] == 3

    def test_one_dissent_makes_it_contested(self):
        c = self.deploy()
        self.three(c)
        S.call(c, "authorise", 0, self.W3)
        self.attest_as(c, self.W3, ROLLED)
        self.mocks(stable([GATE, CARRIER, INVOICE, ROLLED], "yes|yes|unstated|no"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "contested" and c.answer(0) == ""
        assert c.reading(0)["counts"] == "2|1"

    def test_below_quorum_is_insufficient(self):
        c = self.deploy(quorum=3)
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "insufficient"

    # -- the two orders -------------------------------------------------------

    def test_a_source_the_two_orders_read_differently_is_neither_vote_nor_dissent(self):
        """Forward reads CARRIER as a dissent; reversed reads it as a yes. That
        source has not given a usable answer, so it is recorded as unstated and
        counts for nothing either way. With only one clear yes left, quorum 2
        is not reached."""
        c = self.deploy()
        self.three(c)
        # reversed order lists INVOICE first; "unstated|yes|yes" read back is
        # [yes, yes, unstated]
        self.mocks(passes(GATE, "yes|no|unstated", INVOICE, "unstated|yes|yes"))
        S.call(c, "decide", 0)
        assert c.reading(0)["vector"] == "yes|unstated|unstated"
        assert c.verdict(0) == "insufficient"

    def test_the_reading_stores_the_value_and_nothing_about_the_sampling(self):
        c = self.deploy()
        self.three(c)
        self.mocks(passes(GATE, "yes|yes|unstated", INVOICE, "yes|yes|yes"))
        S.call(c, "decide", 0)
        r = c.reading(0)
        assert r["vector"] == "yes|yes|unstated"
        assert "unclear" not in r and "unclear" not in r["vector"]

    def test_the_reversed_reading_is_read_back_into_stored_order(self):
        c = self.deploy(quorum=1)
        self.three(c)
        self.mocks(passes(GATE, "yes|unstated|unstated", INVOICE, "unstated|unstated|yes"))
        S.call(c, "decide", 0)
        assert c.reading(0)["vector"] == "yes|unstated|unstated"

    def test_an_unusable_pass_reads_nothing(self):
        c = self.deploy()
        self.three(c)
        self.mocks(passes(GATE, "yes|yes|unstated", INVOICE, "banana"))
        S.call(c, "decide", 0)
        assert c.reading(0)["vector"] == "unstated|unstated|unstated"
        assert c.verdict(0) == "insufficient"

    def test_a_prompt_answer_that_is_not_an_object_is_unusable_not_fatal(self):
        """json mode does not guarantee an object. A list or a bare string is
        an unusable answer and is recorded as one, rather than crashing the
        block and failing the transaction."""
        c = self.deploy()
        self.three(c)
        self.mocks({"[0] " + GATE: ["yes", "yes", "unstated"], "[0] " + INVOICE: "unstated|yes|yes"})
        S.call(c, "decide", 0)
        assert c.reading(0)["vector"] == "unstated|unstated|unstated"

    # -- consensus ----------------------------------------------------------

    def test_nodes_reading_a_source_differently_do_not_agree(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"),
                   v_prompts=stable([GATE, CARRIER, INVOICE], "yes|no|unstated"))
        with pytest.raises(S.UserError):
            S.call(c, "decide", 0)
        assert c.inquiry(0)["readings"] == 0

    def test_same_tally_different_rows_is_still_a_disagreement(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"),
                   v_prompts=stable([GATE, CARRIER, INVOICE], "unstated|yes|yes"))
        with pytest.raises(S.UserError):
            S.call(c, "decide", 0)

    def test_nodes_that_reach_the_same_vector_by_different_routes_agree(self):
        """The validator's two orders disagree about the invoice and it records
        unstated; the leader read the invoice as silent in both orders. Both
        store the same vector. A separate 'unclear' token would have split
        this vote over a difference no rule acts on."""
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"),
                   v_prompts=passes(GATE, "yes|yes|unstated", INVOICE, "yes|yes|yes"))
        S.call(c, "decide", 0)
        assert c.reading(0)["vector"] == "yes|yes|unstated"
        assert c.verdict(0) == "established"

    def test_the_free_layer_is_actually_free(self):
        """Mocks go in FIRST: set_mocks() resets the payload, and a test that
        did it the other way round passed with the layer deleted."""
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.set_leader_payload({"vector": "yes|maybe|no", "because": "x"})
        try:
            with pytest.raises(S.UserError):
                S.call(c, "decide", 0)
        finally:
            S.set_leader_payload(None)
        assert S.validator_prompt_calls() == 0

    def test_a_leader_payload_that_is_not_a_mapping_is_refused_for_free(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.set_leader_payload("yes|yes|unstated")
        try:
            with pytest.raises(S.UserError):
                S.call(c, "decide", 0)
        finally:
            S.set_leader_payload(None)
        assert S.validator_prompt_calls() == 0
        assert c.inquiry(0)["readings"] == 0

    def test_a_leader_that_rolled_back_is_refused_and_nothing_is_stored(self):
        """Only the forward prompt has an answer, so the leader's block fails.
        A validator must refuse a leader that produced no result at all."""
        c = self.deploy()
        self.three(c)
        self.mocks({"[0] " + GATE: {"readings": "yes|yes|unstated", "because": "x"}})
        with pytest.raises(S.UserError):
            S.call(c, "decide", 0)
        assert S.validator_prompt_calls() == 0
        assert c.inquiry(0)["readings"] == 0

    def test_a_lying_leader_s_reason_is_sanitised_on_the_way_in(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.set_leader_payload({"vector": "yes|yes|unstated", "because": "<b>{x}`y`" + chr(7)})
        try:
            S.call(c, "decide", 0)
        finally:
            S.set_leader_payload(None)
        assert c.reading(0)["why"] == "bxy"
        assert c.reading(0)["reason_is_leader_supplied"] is True

    # -- the replay guard and the recourse -----------------------------------

    def test_a_reading_cannot_be_retaken_over_the_same_sources(self):
        """Somewhere to go must not mean asking until the answer suits."""
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        with pytest.raises(S.UserError, match="nothing has changed"):
            S.call(c, "decide", 0)

    def test_a_reading_that_found_nothing_stands_until_the_set_changes(self):
        """An unusable answer on one node is disagreement, and the network
        rotates to another leader; only an answer no node can use is stored,
        and a stored reading is a reading. There is no retake door."""
        c = self.deploy()
        self.three(c)
        self.mocks(passes(GATE, "yes|yes|unstated", INVOICE, "banana"))
        S.call(c, "decide", 0)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        with pytest.raises(S.UserError, match="nothing has changed"):
            S.call(c, "decide", 0)

    def test_a_new_source_reopens_the_reading(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        S.call(c, "authorise", 0, self.W3)
        self.attest_as(c, self.W3, ROLLED)
        self.mocks(stable([GATE, CARRIER, INVOICE, ROLLED], "yes|yes|unstated|no"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "contested"
        assert c.inquiry(0)["readings"] == 2

    def test_withdrawing_and_re_attesting_the_same_words_is_not_a_change(self):
        """The replay guard compares the sources a reading read, not a counter
        of events: the same accounts saying the same words are the same
        evidence, whatever rows they sit in."""
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        self.as_(c, self.W1, "withdraw", 1)
        self.attest_as(c, self.W1, CARRIER)
        with pytest.raises(S.UserError, match="nothing has changed"):
            S.call(c, "decide", 0)
        # a genuinely corrected source is a change
        self.as_(c, self.W1, "withdraw", 3)
        self.attest_as(c, self.W1, CORRECTED)
        self.mocks(stable([GATE, INVOICE, CORRECTED], "yes|unstated|yes"))
        S.call(c, "decide", 0)
        assert c.inquiry(0)["readings"] == 2

    def test_the_same_words_from_another_account_are_a_different_source(self):
        c = self.deploy(quorum=1)
        S.call(c, "attest", 0, GATE)
        self.mocks({"[0] " + GATE: {"readings": "yes", "because": "x"}})
        S.call(c, "decide", 0)
        S.call(c, "withdraw", 0)
        S.call(c, "authorise", 0, self.W1)
        self.attest_as(c, self.W1, GATE)
        S.call(c, "decide", 0)
        assert c.inquiry(0)["readings"] == 2

    def test_a_reading_records_which_sources_it_read(self):
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        self.as_(c, self.W2, "withdraw", 2)
        S.call(c, "authorise", 0, self.W3)
        self.attest_as(c, self.W3, ROLLED)
        self.mocks(stable([GATE, CARRIER, ROLLED], "yes|yes|no"))
        S.call(c, "decide", 0)
        assert c.reading(0)["sources"] == [0, 1, 2]
        assert c.reading(1)["sources"] == [0, 1, 3]
        assert [r["sources"] for r in c.readings_of(0)["readings"]] == [[0, 1, 2], [0, 1, 3]]

    def test_the_dissenter_withdraws_and_the_fact_is_established(self):
        """The whole journey. A dissent blocks; the dissenter, and only the
        dissenter, can take it back; the next reading establishes."""
        c = self.deploy()
        self.three(c)
        S.call(c, "authorise", 0, self.W3)
        self.attest_as(c, self.W3, ROLLED)
        self.mocks(stable([GATE, CARRIER, INVOICE, ROLLED], "yes|yes|unstated|no"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "contested"
        self.as_(c, self.W3, "withdraw", 3)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "established" and c.answer(0) == "yes"
        assert [r["verdict"] for r in c.readings_of(0)["readings"]] == ["contested", "established"]

    def test_the_registrar_cannot_withdraw_somebody_else_s_source(self):
        """A registrar who could remove a dissent would be curating the
        quorum, and the sources are meant to be independent of the asker."""
        c = self.deploy()
        self.three(c)
        with pytest.raises(S.UserError, match="only the account that submitted"):
            S.call(c, "withdraw", 1)

    def test_a_withdrawn_source_stays_on_the_record_marked(self):
        c = self.deploy()
        self.three(c)
        self.as_(c, self.W1, "withdraw", 1)
        rows = c.sources_of(0)["sources"]
        assert rows[1]["withdrawn"] is True and rows[1]["text"] == CARRIER
        assert c.inquiry(0)["live"] == 2

    def test_a_withdrawn_source_is_not_read(self):
        c = self.deploy(quorum=1)
        self.three(c)
        self.as_(c, self.W2, "withdraw", 2)
        self.mocks(stable([GATE, CARRIER], "yes|yes"))
        S.call(c, "decide", 0)
        assert c.reading(0)["sources_read"] == 2

    def test_withdrawing_twice_is_refused(self):
        c = self.deploy()
        self.three(c)
        self.as_(c, self.W1, "withdraw", 1)
        with pytest.raises(S.UserError, match="already withdrawn"):
            self.as_(c, self.W1, "withdraw", 1)

    def test_a_withdrawn_attester_may_attest_again(self):
        """Withdrawing frees the one-per-account slot: the account has no LIVE
        source, so a corrected one may replace it."""
        c = self.deploy()
        self.three(c)
        self.as_(c, self.W1, "withdraw", 1)
        self.attest_as(c, self.W1, CORRECTED)
        assert c.inquiry(0)["live"] == 3

    # -- one source per account ----------------------------------------------

    def test_one_live_source_per_account(self):
        c = self.deploy()
        S.call(c, "attest", 0, GATE)
        with pytest.raises(S.UserError, match="already has a live source"):
            S.call(c, "attest", 0, CARRIER)

    # -- closing ------------------------------------------------------------

    def test_a_closed_inquiry_takes_no_more_sources_but_can_still_be_read(self):
        c = self.deploy()
        self.three(c)
        S.call(c, "close", 0)
        with pytest.raises(S.UserError, match="closed to new sources"):
            S.call(c, "attest", 0, ROLLED)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        S.call(c, "decide", 0)
        assert c.verdict(0) == "established"

    def test_a_closed_inquiry_s_sources_are_final(self):
        """Without this the holder of the last live source could empty a closed
        inquiry, which then could never be read again."""
        c = self.deploy()
        self.three(c)
        S.call(c, "close", 0)
        with pytest.raises(S.UserError, match="closed and its sources are final"):
            self.as_(c, self.W1, "withdraw", 1)
        assert c.inquiry(0)["live"] == 3

    def test_closing_twice_is_refused(self):
        c = self.deploy()
        S.call(c, "close", 0)
        with pytest.raises(S.UserError, match="already closed"):
            S.call(c, "close", 0)

    # -- budgets and caps ----------------------------------------------------
    #
    # Every chain is capped, and no attester can spend a budget the registrar
    # depends on: each account has its own allowance of rows, and the last rows
    # of an inquiry are its registrar's alone.

    def test_one_account_may_attest_at_most_four_times(self):
        """Without an allowance, one attester cycling attest and withdraw could
        spend every row the inquiry has and lock everybody else out."""
        c = self.deploy()
        S.call(c, "authorise", 0, self.W1)
        for k in range(4):
            self.attest_as(c, self.W1, "Version %d of the carrier notification, long enough." % k)
            self.as_(c, self.W1, "withdraw", c.source_count() - 1)
        with pytest.raises(S.UserError, match="at most 4 times"):
            self.attest_as(c, self.W1, CARRIER)
        S.call(c, "attest", 0, GATE)                  # nobody else is affected

    def test_the_last_four_rows_are_the_registrar_s_and_the_chain_stops_at_64(self):
        c = self.deploy()
        attesters = [addr(i) for i in range(15)]
        for a in attesters:
            S.call(c, "authorise", 0, a)
        for a in attesters:
            for k in range(4):
                self.attest_as(c, a, "Source %s, version %d, long enough to accept." % (a[2:6], k))
                self.as_(c, a, "withdraw", c.source_count() - 1)
        assert c.inquiry(0)["sources"] == 60
        S.call(c, "authorise", 0, addr(20))
        with pytest.raises(S.UserError, match="the last 4 source rows"):
            self.attest_as(c, addr(20), CARRIER)
        for k in range(4):
            S.call(c, "attest", 0, "Registrar source, version %d, long enough to accept." % k)
            S.call(c, "withdraw", c.source_count() - 1)
        with pytest.raises(S.UserError, match="capped at 64 source rows"):
            S.call(c, "attest", 0, GATE)
        assert c.inquiry(0)["sources"] == 64

    def test_the_source_cap_counts_live_rows(self):
        c = self.deploy()
        S.call(c, "attest", 0, GATE)
        for i in range(7):
            S.call(c, "authorise", 0, addr(i))
            self.attest_as(c, addr(i), "Source number %d, which is long enough to be accepted." % i)
        S.call(c, "authorise", 0, addr(10))
        with pytest.raises(S.UserError, match="capped at 8 live sources"):
            self.attest_as(c, addr(10), "A ninth source, which should be refused by the cap.")
        # a withdrawal frees a slot: the cap is on LIVE sources
        self.as_(c, addr(6), "withdraw", 7)
        self.attest_as(c, addr(10), "A ninth source, accepted now that a slot is free again.")
        assert c.inquiry(0)["live"] == 8

    def test_the_active_cap_survives_a_revoke_and_reauthorise_cycle(self):
        c = self.deploy()
        addrs = [addr(i) for i in range(16)]
        for a in addrs:
            S.call(c, "authorise", 0, a)
        with pytest.raises(S.UserError, match="capped at 16 active attesters"):
            S.call(c, "authorise", 0, addr(20))
        S.call(c, "revoke", 0, addrs[0])
        S.call(c, "authorise", 0, addr(21))
        with pytest.raises(S.UserError, match="capped at 16 active attesters"):
            S.call(c, "authorise", 0, addrs[0])

    def test_the_attester_chain_is_capped_at_32_rows_revoked_ones_included(self):
        c = self.deploy()
        first = [addr(i) for i in range(16)]
        second = [addr(i) for i in range(16, 32)]
        for a in first:
            S.call(c, "authorise", 0, a)
        for a in first:
            S.call(c, "revoke", 0, a)
        for a in second:
            S.call(c, "authorise", 0, a)
        S.call(c, "revoke", 0, second[0])
        with pytest.raises(S.UserError, match="at most 32 attester rows"):
            S.call(c, "authorise", 0, addr(40))
        S.call(c, "authorise", 0, first[0])           # reactivating adds no row
        assert len(c.delegation(0)["attesters"]) == 32

    # -- the linked walks ---------------------------------------------------

    def test_two_inquiries_never_see_each_other_s_sources(self):
        c = self.deploy()
        S.call(c, "open", "A second question that is long enough?", "yes|no", 1)
        S.call(c, "attest", 1, "A source that belongs to the second inquiry, nothing else.")
        S.call(c, "attest", 0, GATE)
        assert [r["id"] for r in c.sources_of(0)["sources"]] == [1]
        assert [r["id"] for r in c.sources_of(1)["sources"]] == [0]

    # -- authority ----------------------------------------------------------

    def test_a_stranger_cannot_attest(self):
        c = self.deploy()
        with pytest.raises(S.UserError, match="registrar or an authorised attester"):
            self.attest_as(c, self.STRANGER, GATE)

    def test_a_revoked_attester_cannot_attest_and_their_source_stays(self):
        c = self.deploy()
        self.three(c)
        S.call(c, "revoke", 0, self.W1)
        assert c.sources_of(0)["sources"][1]["withdrawn"] is False
        self.as_(c, self.W1, "withdraw", 1)
        with pytest.raises(S.UserError, match="registrar or an authorised attester"):
            self.attest_as(c, self.W1, ROLLED)

    def test_an_attester_may_not_authorise_revoke_or_close(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.W1)
        for call in (("authorise", 0, self.STRANGER), ("revoke", 0, self.W1), ("close", 0)):
            with pytest.raises(S.UserError, match="only the registrar"):
                self.as_(c, self.W1, *call)

    def test_attester_refusals_are_clean(self):
        c = self.deploy()
        with pytest.raises(S.UserError, match="registrar already attests"):
            S.call(c, "authorise", 0, self.REGISTRAR)
        S.call(c, "authorise", 0, self.W1)
        with pytest.raises(S.UserError, match="already authorised"):
            S.call(c, "authorise", 0, self.W1)
        with pytest.raises(S.UserError, match="not an attester on this inquiry"):
            S.call(c, "revoke", 0, self.STRANGER)
        S.call(c, "revoke", 0, self.W1)
        with pytest.raises(S.UserError, match="already revoked"):
            S.call(c, "revoke", 0, self.W1)

    def test_delegation_is_scoped_to_one_inquiry(self):
        c = self.deploy()
        S.call(c, "open", "A second question that is long enough?", "yes|no", 1)
        S.call(c, "authorise", 0, self.W1)
        self.attest_as(c, self.W1, CARRIER)
        with pytest.raises(S.UserError, match="registrar or an authorised attester"):
            self.attest_as(c, self.W1, CARRIER, inquiry=1)

    def test_a_malformed_attester_address_is_refused_cleanly(self):
        c = self.deploy()
        for bad in ("not-an-address", "0x1234", "", "0x" + "zz" * 20):
            with pytest.raises(S.UserError, match="not a 20 byte hex address"):
                S.call(c, "authorise", 0, bad)
            with pytest.raises(S.UserError, match="not a 20 byte hex address"):
                S.call(c, "revoke", 0, bad)

    def test_an_address_is_matched_by_value_not_by_spelling(self):
        c = self.deploy()
        S.call(c, "authorise", 0, "0x" + "AB" * 20)
        self.attest_as(c, "0x" + "ab" * 20, CARRIER)
        assert c.inquiry(0)["live"] == 1

    def test_anyone_may_decide_and_that_is_deliberate(self):
        """decide() adds no text, reaches only the verdict the sources imply,
        and is refused while nothing has changed, so it cannot be replayed."""
        c = self.deploy()
        self.three(c)
        self.mocks(stable([GATE, CARRIER, INVOICE], "yes|yes|unstated"))
        self.as_(c, self.STRANGER, "decide", 0)
        assert c.reading(0)["by"].lower() == self.STRANGER

    # -- may_attest asks the same question attest() asks ----------------------

    def test_may_attest_follows_authority(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.W1)
        assert c.may_attest(0, self.REGISTRAR) is True
        assert c.may_attest(0, self.W1) is True
        assert c.may_attest(0, self.STRANGER) is False
        assert c.may_attest(0, "not-an-address") is False
        S.call(c, "revoke", 0, self.W1)
        assert c.may_attest(0, self.W1) is False

    def test_may_attest_says_no_to_a_second_live_source_and_on_a_closed_inquiry(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.W1)
        self.attest_as(c, self.W1, CARRIER)
        assert c.may_attest(0, self.W1) is False           # already has a live source
        assert c.may_attest(0, self.REGISTRAR) is True
        S.call(c, "close", 0)
        assert c.may_attest(0, self.REGISTRAR) is False

    def test_may_attest_says_no_at_every_budget(self):
        c = self.deploy()
        S.call(c, "authorise", 0, self.W1)
        for k in range(4):
            self.attest_as(c, self.W1, "Version %d of the carrier notification, long enough." % k)
            self.as_(c, self.W1, "withdraw", c.source_count() - 1)
        assert c.may_attest(0, self.W1) is False           # its own allowance spent
        S.call(c, "attest", 0, GATE)
        for i in range(7):
            S.call(c, "authorise", 0, addr(i))
            self.attest_as(c, addr(i), "Source number %d, which is long enough to be accepted." % i)
        S.call(c, "authorise", 0, addr(10))
        assert c.may_attest(0, addr(10)) is False          # eight live sources

    def test_may_attest_raises_on_a_bad_id_like_every_read(self):
        c = self.deploy()
        for bad in (9, -1):
            with pytest.raises(S.UserError, match="no such inquiry"):
                c.may_attest(bad, "garbage")

    # -- validation ---------------------------------------------------------

    @pytest.mark.parametrize("q,ans,quorum,msg", [
        ("short", "yes|no", 1, "needs a question"),
        ("x" * 301, "yes|no", 1, "capped at 300 characters"),
        (Q, "yes", 1, "at least two possible answers"),
        (Q, "yes|yes", 1, "same wording"),
        (Q, "yes|unstated", 1, "is reserved"),
        (Q, "a|b|c|d|e|f", 1, "capped at 5 answers"),
        (Q, "yes|no", 0, "quorum must be between"),
        (Q, "yes|no", 9, "quorum must be between"),
    ])
    def test_bad_inquiries_are_refused_with_the_reason(self, q, ans, quorum, msg):
        c = S.deploy(CONTRACT_PATH)
        with pytest.raises(S.UserError, match=msg):
            S.call(c, "open", q, ans, quorum)
        assert c.count() == 0

    def test_question_bounds_at_both_edges(self):
        c = S.deploy(CONTRACT_PATH)
        with pytest.raises(S.UserError, match="needs a question"):
            S.call(c, "open", "x" * 9, "yes|no", 1)
        S.call(c, "open", "x" * 10, "yes|no", 1)
        S.call(c, "open", "x" * 300, "yes|no", 8)
        assert c.count() == 2

    def test_unclear_is_an_ordinary_answer_word(self):
        """The contract no longer uses the word itself, so a registrar may."""
        c = S.deploy(CONTRACT_PATH)
        S.call(c, "open", Q, "clear|unclear", 1)
        assert c.inquiry(0)["answers"] == ["clear", "unclear"]

    @pytest.mark.parametrize("text,msg", [
        ("x" * 19, "a sentence, not a fragment"),
        ("   ", "a sentence, not a fragment"),
        ("x" * 701, "capped at 700 characters"),
    ])
    def test_bad_sources_are_refused_with_the_reason(self, text, msg):
        c = self.deploy()
        with pytest.raises(S.UserError, match=msg):
            S.call(c, "attest", 0, text)

    def test_sources_at_both_edges_are_accepted(self):
        c = self.deploy()
        S.call(c, "attest", 0, "x" * 20)
        S.call(c, "authorise", 0, self.W1)
        self.attest_as(c, self.W1, "y" * 700)
        assert c.inquiry(0)["live"] == 2

    def test_deciding_with_no_live_sources_is_refused(self):
        c = self.deploy()
        with pytest.raises(S.UserError, match="no live sources"):
            S.call(c, "decide", 0)

    def test_a_read_with_a_bad_id_is_a_user_error(self):
        c = self.deploy()
        for m, arg in (("inquiry", 9), ("inquiry", -1), ("reading", 0), ("reading", -1),
                       ("sources_of", 9), ("readings_of", -1), ("delegation", 9),
                       ("verdict", 9), ("answer", -1), ("registrar", 9)):
            with pytest.raises(S.UserError, match="no such"):
                getattr(c, m)(arg)

    def test_writes_with_a_bad_id_are_refused_cleanly(self):
        c = self.deploy()
        for call in (("attest", 9, GATE), ("withdraw", 0), ("withdraw", -1),
                     ("authorise", 9, self.W1), ("close", -1), ("decide", 9)):
            with pytest.raises(S.UserError, match="no such"):
                S.call(c, *call)


# ===========================================================================
# GenVM storage and boundary rules, by static analysis.
# ===========================================================================

class TestStorageShape:
    def _tree(self):
        return ast.parse(pathlib.Path(CONTRACT_PATH).read_text(encoding="utf-8"))

    def _contract(self):
        return [x for x in self._tree().body if isinstance(x, ast.ClassDef)
                and any("gl.Contract" in ast.unparse(b) for b in x.bases)][0]

    def test_the_contract_imports_under_genvm_storage_rules(self):
        assert hasattr(S.load_contract(CONTRACT_PATH), "Contract")

    def test_no_storage_dataclass_holds_a_collection(self):
        for cls in [x for x in self._tree().body if isinstance(x, ast.ClassDef)]:
            if "allow_storage" not in " ".join(ast.unparse(d) for d in cls.decorator_list):
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    ann = ast.unparse(st.annotation)
                    assert "DynArray" not in ann and "TreeMap" not in ann

    def test_no_forbidden_storage_types(self):
        for cls in [x for x in self._tree().body if isinstance(x, ast.ClassDef)]:
            decs = " ".join(ast.unparse(d) for d in cls.decorator_list)
            is_contract = any("gl.Contract" in ast.unparse(b) for b in cls.bases)
            if "allow_storage" not in decs and not is_contract:
                continue
            for st in cls.body:
                if isinstance(st, ast.AnnAssign):
                    assert ast.unparse(st.annotation) not in ("int", "float", "list", "dict", "tuple")

    def test_no_storage_field_or_method_is_declared_twice(self):
        for cls in [x for x in self._tree().body if isinstance(x, ast.ClassDef)]:
            fields = [st.target.id for st in cls.body if isinstance(st, ast.AnnAssign)]
            meths = [m.name for m in cls.body if isinstance(m, ast.FunctionDef)]
            for names in (fields, meths):
                assert not [n for n, k in collections.Counter(names).items() if k > 1], cls.name

    def test_every_persistent_field_is_declared_in_the_class_body(self):
        cls = self._contract()
        declared = {st.target.id for st in cls.body if isinstance(st, ast.AnnAssign)}
        for m in [x for x in cls.body if isinstance(x, ast.FunctionDef)]:
            for node in ast.walk(m):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target] if isinstance(node, ast.AugAssign) else [])
                for tg in targets:
                    if isinstance(tg, ast.Attribute) and isinstance(tg.value, ast.Name) and tg.value.id == "self":
                        assert tg.attr in declared, f"self.{tg.attr} undeclared"

    def test_the_block_boundary_carries_flat_strings_only(self):
        for blk in [x for x in ast.walk(self._tree()) if isinstance(x, ast.FunctionDef) and x.name == "leader_fn"]:
            for r in [n for n in ast.walk(blk) if isinstance(n, ast.Return)]:
                assert isinstance(r.value, ast.Dict)
                for k, v in zip(r.value.keys, r.value.values):
                    assert isinstance(k, ast.Constant) and isinstance(k.value, str)
                    assert not isinstance(v, (ast.Dict, ast.List, ast.Set, ast.Tuple, ast.Compare, ast.BoolOp))

    def test_the_block_never_touches_storage(self):
        for blk in [x for x in ast.walk(self._tree()) if isinstance(x, ast.FunctionDef) and x.name in ("leader_fn", "validator_fn")]:
            for n in ast.walk(blk):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                    assert n.value.id != "self"

    def test_no_identity_comparison_on_storage(self):
        for n in ast.walk(self._tree()):
            if isinstance(n, ast.Compare) and any(isinstance(o, (ast.Is, ast.IsNot)) for o in n.ops):
                assert "self." not in ast.unparse(n)

    def test_every_gated_write_refuses_on_the_sender(self):
        """Not a substring search, which a bookkeeping line that merely
        records the sender would satisfy. Every write other than open and
        decide must contain an `if` whose test reads the sender, directly or
        through a local derived from it, and whose body raises. open() sets
        the registrar; decide() is deliberately open, reads the sender only to
        record who took the reading, and is guarded by the replay rule."""
        UNGATED = {"open", "decide"}
        for m in self._contract().body:
            if not (isinstance(m, ast.FunctionDef)
                    and any("gl.public.write" in ast.unparse(d) for d in m.decorator_list)):
                continue
            if m.name in UNGATED:
                continue
            derived = set()
            grew = True
            while grew:
                grew = False
                for node in ast.walk(m):
                    if not isinstance(node, ast.Assign):
                        continue
                    src = ast.unparse(node.value)
                    uses = "sender_address" in src or any(
                        re.search(r"\b%s\b" % re.escape(d), src) for d in derived)
                    if uses:
                        for tg in node.targets:
                            if isinstance(tg, ast.Name) and tg.id not in derived:
                                derived.add(tg.id)
                                grew = True
            gated = False
            for node in ast.walk(m):
                if isinstance(node, ast.If):
                    test = ast.unparse(node.test)
                    reads = "sender_address" in test or any(
                        re.search(r"\b%s\b" % re.escape(d), test) for d in derived)
                    raises = any(isinstance(x, ast.Raise)
                                 for stmt in node.body for x in ast.walk(stmt))
                    gated = gated or (reads and raises)
            assert gated, f"{m.name} has no refusal that depends on the sender"

    def test_no_global_scan_over_any_storage_array(self):
        scans = [n.lineno for n in ast.walk(self._tree())
                 if isinstance(n, ast.For) and "len(self." in ast.unparse(n.iter)]
        assert scans == [], scans
