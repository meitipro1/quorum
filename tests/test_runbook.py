"""
DEPLOY.md, replayed.

The deployment walkthrough tells an operator which transactions to send, from
which of four accounts, and what each read should return. A wrong id or a wrong
expectation there costs a transaction on a live page, so the walkthrough is
tested like the code: this file drives the real contract through the same
thirteen writes, with the same strings - checked against DEPLOY.md itself, so
the two cannot drift apart - and asserts every value the page and
SUBMISSION.md's table tell the operator to expect, down to the version each
reading records.

If you change DEPLOY.md, change this file with it.

    pytest tests/test_runbook.py -v
"""

import pathlib
import re

import glsim as S

CONTRACT_PATH = "contracts/quorum.py"
DOC = pathlib.Path("DEPLOY.md").read_text(encoding="utf-8")
SUBMISSION = pathlib.Path("SUBMISSION.md").read_text(encoding="utf-8")

A = "0x" + "a1" * 20          # the registrar
B = "0x" + "b2" * 20
C = "0x" + "c3" * 20
D = "0x" + "d4" * 20

QUESTION = "Did the container arrive at the Rotterdam terminal before the 30 June cutoff?"
ANSWERS = "yes|no"
GATE = ("Terminal gate log: container MSKU7712389 discharged and gated in at Rotterdam "
        "Maasvlakte II on 28 June, 14:02.")
CARRIER = ("Carrier notification: vessel berthed Rotterdam 28 June; MSKU7712389 available "
           "for pickup from 29 June.")
INVOICE = "Invoice 4471 for freight charges on MSKU7712389, issued 2 July, payable within 30 days."
ROLLED = ("Forwarder update: MSKU7712389 was rolled to the next sailing and did not discharge "
          "at Rotterdam until 4 July.")


def in_doc(text, doc=DOC):
    """A value quoted in a markdown table has its pipes escaped."""
    return ("`%s`" % text) in doc or ("`%s`" % text.replace("|", "\\|")) in doc


def stable(texts, vector):
    rev = "|".join(reversed(vector.split("|")))
    return {"[0] " + texts[0]: {"readings": vector, "because": "x"},
            "[0] " + texts[-1]: {"readings": rev, "because": "x"}}


def mock(texts, vector):
    m = stable(texts, vector)
    S.set_mocks(leader_pages={}, leader_prompts=m, validator_pages={}, validator_prompts=m)


def as_(who, c, method, *args):
    S.set_sender(who)
    try:
        return S.call(c, method, *args)
    finally:
        S.set_sender(A)


class TestTheWalkthrough:
    def test_every_string_the_test_sends_is_the_one_the_page_shows(self):
        for text in (QUESTION, ANSWERS, GATE, CARRIER, INVOICE, ROLLED):
            assert in_doc(text), "DEPLOY.md no longer shows: %s" % text

    def test_the_thirteen_writes_produce_what_the_page_promises(self):
        S.set_sender(A)
        c = S.deploy(CONTRACT_PATH)

        # 1  open
        as_(A, c, "open", QUESTION, ANSWERS, 2)
        assert c.inquiry(0)["version"] == 0

        # 2-5  the registrar's source and three attesters
        as_(A, c, "attest", 0, GATE)
        for who in (B, C, D):
            as_(A, c, "authorise", 0, who)
        assert c.inquiry(0)["version"] == 1

        # 6-7  two more sources
        as_(B, c, "attest", 0, CARRIER)
        as_(C, c, "attest", 0, INVOICE)
        assert c.inquiry(0)["version"] == 3

        # 8  the first reading
        mock([GATE, CARRIER, INVOICE], "yes|yes|unstated")
        as_(A, c, "decide", 0)
        r0 = c.reading(0)
        assert (r0["vector"], r0["verdict"], r0["answer"]) == ("yes|yes|unstated", "established", "yes")
        assert r0["counts"] == "2|0" and r0["sources"] == [0, 1, 2] and r0["version"] == 3

        # 9-10  the dissent
        as_(D, c, "attest", 0, ROLLED)
        mock([GATE, CARRIER, INVOICE, ROLLED], "yes|yes|unstated|no")
        as_(B, c, "decide", 0)
        r1 = c.reading(1)
        assert (r1["vector"], r1["verdict"], r1["answer"]) == ("yes|yes|unstated|no", "contested", "")
        assert r1["counts"] == "2|1" and r1["sources"] == [0, 1, 2, 3] and r1["version"] == 4
        assert c.inquiry(0)["version"] == 4

        # 11  the dissenter withdraws its own source
        as_(D, c, "withdraw", 3)
        rows = c.sources_of(0)["sources"]
        assert rows[3]["withdrawn"] is True and rows[3]["text"] == ROLLED
        q = c.inquiry(0)
        assert q["live"] == 3 and q["version"] == 5

        # 12-13  the third reading, and the revocation
        mock([GATE, CARRIER, INVOICE], "yes|yes|unstated")
        as_(C, c, "decide", 0)
        as_(A, c, "revoke", 0, D)
        r2 = c.reading(2)
        assert (r2["vector"], r2["verdict"], r2["answer"]) == ("yes|yes|unstated", "established", "yes")
        assert r2["sources"] == [0, 1, 2] and r2["version"] == 5

        # section 3, the reads table
        assert c.verdict(0) == "established" and c.answer(0) == "yes"
        q = c.inquiry(0)
        assert (q["sources"], q["live"], q["readings"], q["version"], q["verdict"]) == \
            (4, 3, 3, 5, "established")
        assert [r["by"].lower() for r in c.sources_of(0)["sources"]] == [A, B, C, D]
        history = c.readings_of(0)["readings"]
        assert [(h["verdict"], h["version"], h["sources"]) for h in history] == [
            ("established", 3, [0, 1, 2]),
            ("contested", 4, [0, 1, 2, 3]),
            ("established", 5, [0, 1, 2]),
        ]
        d = c.delegation(0)
        assert d["registrar"].lower() == A
        assert d["attesters"] == [{"who": B, "active": True}, {"who": C, "active": True},
                                  {"who": D, "active": False}]
        assert c.may_attest(0, D) is False
        assert c.may_attest(0, B) is False

    def test_the_submission_table_describes_this_run(self):
        for cell in ("`yes\\|yes\\|unstated`", "counts `2\\|0`", "`yes\\|yes\\|unstated\\|no`",
                     "counts `2\\|1`", "sources `0, 1, 2`"):
            assert cell in SUBMISSION, cell

    def test_the_page_names_the_ids_the_contract_assigns(self):
        assert "| 11 | **D** | `withdraw` | `source_id` | `3` |" in DOC

    def test_the_portal_notes_fit_the_box(self):
        m = re.search(r"## Notes.*?```\n(.*?)\n```", SUBMISSION, re.S)
        assert m and len(m.group(1)) <= 1000, len(m.group(1)) if m else "no notes block"
