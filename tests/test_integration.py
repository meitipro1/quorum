"""Integration tests, run against GenLayer Studio with gltest.

    pip install genlayer-test
    GENLAYER_STUDIO=1 gltest --network studionet tests/test_integration.py

They are opt in: without GENLAYER_STUDIO set they skip, so that
`pytest tests/ -q` stays clean on a machine that has genlayer-test
installed but no Studio to talk to.

These are slower than the other two suites and they prove something different:
that the contract deploys, that storage round-trips, that the linked walks hold
on a real runtime, and that the deterministic gates fire.

Everything here exercises the deterministic half, which needs no inference: an
inquiry opens frozen, sources land one per account, the ownership rule on
withdraw() holds against real signatures, the authority rules fire. The reading
costs two prompts and belongs in a manual Studio run; see DEPLOY.md.
"""

import os

import pytest

# gltest is only needed for this file. Skip cleanly when it is absent so that
# `pytest tests/` works out of the box on a machine with nothing installed but
# pytest, and still runs everything in test_logic.py and test_e2e.py.
gltest = pytest.importorskip(
    "gltest",
    reason="integration tests need genlayer-test and a running Studio: "
           "pip install genlayer-test, then GENLAYER_STUDIO=1 gltest",
)
from gltest import get_contract_factory, get_accounts        # noqa: E402
from gltest.assertions import tx_execution_succeeded         # noqa: E402


# The second half of the same guard, and it is the half that bites.
#
# importorskip above covers "genlayer-test is not installed". It does NOT cover
# "genlayer-test IS installed and there is no Studio to talk to", which is the
# common case for anybody who reviews GenLayer contracts: the plugin loads,
# collects this file, and every test in it fails on a connection error rather
# than skipping. `pytest tests/ -q` then reports a wall of ERRORs on a
# repository whose README promises a clean offline run, and the reader cannot
# tell an unreachable network from a broken contract.
#
# Detecting it does not work. A probe was tried first and thrown away: the
# transport failures here are INTERMITTENT rather than a clean threshold, so
# the probe passes and the deploy that follows it still dies. Something that
# answers correctly only most of the time is worse than no gate at all.
#
# So the gate is explicit. These tests need a live Studio, and you say so.
if not os.environ.get("GENLAYER_STUDIO"):
    pytest.skip(
        "integration tests run against a live GenLayer Studio and are opt in: "
        "set GENLAYER_STUDIO=1 to enable them. Everything else runs offline "
        "with pytest tests/ -q",
        allow_module_level=True,
    )


QUESTION = "Did the container arrive at the Rotterdam terminal before the 30 June cutoff?"
GATE = ("Terminal gate log: container MSKU7712389 discharged and gated in at "
        "Rotterdam Maasvlakte II on 28 June, 14:02.")
CARRIER = ("Carrier notification: vessel berthed Rotterdam 28 June; MSKU7712389 "
           "available for pickup from 29 June.")


class TestQuorum:
    @pytest.fixture
    def contract(self):
        factory = get_contract_factory(contract_file_path="quorum.py")
        return factory.deploy(args=[])

    def test_an_inquiry_opens_frozen(self, contract):
        tx = contract.open(args=[QUESTION, "yes|no", 2])
        assert tx_execution_succeeded(tx)
        q = contract.inquiry(args=[0])
        assert q["answers"] == ["yes", "no"] and q["quorum"] == 2
        assert q["live"] == 0 and q["verdict"] == ""

    def test_a_source_lands_and_bumps_the_version(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        assert tx_execution_succeeded(contract.attest(args=[0, GATE]))
        q = contract.inquiry(args=[0])
        assert q["live"] == 1 and q["version"] == 1
        assert contract.sources_of(args=[0])["sources"][0]["text"] == GATE

    def test_one_live_source_per_account(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.attest(args=[0, GATE])
        with pytest.raises(Exception):
            contract.attest(args=[0, CARRIER])

    def test_a_withdrawal_marks_the_row_keeps_it_and_frees_the_slot(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.attest(args=[0, GATE])
        assert tx_execution_succeeded(contract.withdraw(args=[0]))
        row = contract.sources_of(args=[0])["sources"][0]
        assert row["withdrawn"] is True and row["text"] == GATE
        assert contract.inquiry(args=[0])["live"] == 0
        assert tx_execution_succeeded(contract.attest(args=[0, CARRIER]))

    def test_withdrawing_twice_is_refused(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.attest(args=[0, GATE])
        contract.withdraw(args=[0])
        with pytest.raises(Exception):
            contract.withdraw(args=[0])

    def test_deciding_with_no_live_sources_is_refused(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        with pytest.raises(Exception):
            contract.decide(args=[0])

    @pytest.mark.parametrize("answers,quorum", [
        ("yes", 1), ("yes|yes", 1), ("yes|unstated", 1), ("<yes>|no", 1), ("yes|no", 0),
    ])
    def test_bad_inquiries_are_refused(self, contract, answers, quorum):
        with pytest.raises(Exception):
            contract.open(args=[QUESTION, answers, quorum])

    def test_the_walk_follows_the_links_across_two_inquiries(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.open(args=["A second question that is long enough?", "yes|no", 1])
        contract.attest(args=[1, "A source that belongs to the second inquiry, nothing else."])
        contract.attest(args=[0, GATE])
        assert [r["id"] for r in contract.sources_of(args=[0])["sources"]] == [1]
        assert [r["id"] for r in contract.sources_of(args=[1])["sources"]] == [0]

    def test_a_closed_inquiry_takes_no_more_sources(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        assert tx_execution_succeeded(contract.close(args=[0]))
        with pytest.raises(Exception):
            contract.attest(args=[0, GATE])

    def test_a_negative_id_does_not_return_the_newest_row(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        with pytest.raises(Exception):
            contract.inquiry(args=[-1])


class TestAuthority:
    """The authorisation rules, against a real runtime.

    These matter more than the rest of this file. tests/glsim.py models
    gl.message.sender_address with a variable a test can set; a node derives it
    from a signature. A rule that holds in the simulator and not on chain would
    be invisible to every other test here.
    """

    @pytest.fixture
    def two(self):
        accounts = get_accounts()
        if len(accounts) < 2:
            pytest.skip(
                "needs two configured accounts on this network, so that a "
                "refusal is a refusal and not an unfunded sender"
            )
        return accounts[0], accounts[1]

    @pytest.fixture
    def contract(self, two):
        owner, _ = two
        factory = get_contract_factory(contract_file_path="quorum.py")
        return factory.deploy(args=[], account=owner)

    def test_a_stranger_cannot_attest(self, contract, two):
        _, stranger = two
        contract.open(args=[QUESTION, "yes|no", 2])
        with pytest.raises(Exception):
            contract.connect(stranger).attest(args=[0, GATE])
        assert contract.inquiry(args=[0])["live"] == 0

    def test_an_attester_may_attest_and_the_record_names_them(self, contract, two):
        _, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        assert tx_execution_succeeded(contract.authorise(args=[0, attester.address]))
        assert tx_execution_succeeded(contract.connect(attester).attest(args=[0, CARRIER]))
        row = contract.sources_of(args=[0])["sources"][0]
        assert row["by"].lower() == attester.address.lower()

    def test_the_registrar_cannot_withdraw_somebody_else_s_source(self, contract, two):
        """The rule the whole primitive rests on, against real signatures."""
        _, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.authorise(args=[0, attester.address])
        contract.connect(attester).attest(args=[0, CARRIER])
        with pytest.raises(Exception):
            contract.withdraw(args=[0])
        assert contract.sources_of(args=[0])["sources"][0]["withdrawn"] is False
        assert tx_execution_succeeded(contract.connect(attester).withdraw(args=[0]))

    def test_a_revoked_attester_cannot_attest_and_their_source_stays(self, contract, two):
        _, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.authorise(args=[0, attester.address])
        contract.connect(attester).attest(args=[0, CARRIER])
        assert tx_execution_succeeded(contract.revoke(args=[0, attester.address]))
        assert contract.inquiry(args=[0])["live"] == 1
        contract.connect(attester).withdraw(args=[0])
        with pytest.raises(Exception):
            contract.connect(attester).attest(args=[0, GATE])

    def test_an_attester_may_not_authorise_revoke_or_close(self, contract, two):
        _, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.authorise(args=[0, attester.address])
        for call, args in (("authorise", [0, attester.address]),
                           ("revoke", [0, attester.address]),
                           ("close", [0])):
            with pytest.raises(Exception):
                getattr(contract.connect(attester), call)(args=args)

    def test_may_attest_answers_what_attest_enforces(self, contract, two):
        owner, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        assert contract.may_attest(args=[0, owner.address]) is True
        assert contract.may_attest(args=[0, attester.address]) is False
        contract.authorise(args=[0, attester.address])
        assert contract.may_attest(args=[0, attester.address]) is True

    def test_an_address_is_matched_by_value_not_by_spelling(self, contract, two):
        _, attester = two
        contract.open(args=[QUESTION, "yes|no", 2])
        contract.authorise(args=[0, attester.address.lower()])
        upper = "0x" + attester.address[2:].upper()
        assert contract.may_attest(args=[0, upper]) is True

    def test_a_malformed_attester_address_is_refused(self, contract):
        contract.open(args=[QUESTION, "yes|no", 2])
        with pytest.raises(Exception):
            contract.authorise(args=[0, "not-an-address"])
