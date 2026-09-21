# Deploying Quorum

Everything you need is on this page. Deploy through the Studio web interface at
**studio.genlayer.com** - paste the contract, deploy, and call the methods
through the form. Never put a private key into a file or hand one to a tool.

You need **four accounts** in Studio, because Quorum takes **one live source per
account** on purpose: the registrar, called **A** below, and three attesters,
**B**, **C** and **D**. The account selector in Studio's top bar lets you create
accounts and switch between them; studionet charges no gas, so nothing needs
funding. Write down the four addresses before you start. Every step says which
account it is run from.

`tests/test_runbook.py` replays this page step by step, with these exact
strings, and asserts every value it tells you to expect. If the page and the
contract ever disagree, that test fails before you do.

Do not try the refusals on the live contract - the registrar withdrawing D's
source, a second source from one account, a second reading over the same set.
They are refused, and each is tested, but a failed transaction on the explorer
page costs more than it shows.

---

## 1 - Get the contract

Open the raw file and copy all of it:

**https://raw.githubusercontent.com/meitipro/quorum/main/contracts/quorum.py**

Take it from that link, not from a local copy. What gets deployed has to be the
file in this repository - the reviewer reads the deployed source back off the
chain and compares it, and a submission has been rejected for nothing but a
stale address with the fix already sitting in the repo.

Paste it into Studio and deploy from **A**. **The constructor takes no
arguments.**

---

## 2 - Run the demo

Thirteen writes, in this order.

### Open the inquiry - from A

| # | Method | Field | Value |
|---|---|---|---|
| 1 | `open` | `question` | `Did the container arrive at the Rotterdam terminal before the 30 June cutoff?` |
| | | `answers` | `yes\|no` |
| | | `quorum` | `2` |

`answers` is **one string with a pipe separator** - two answers. The question,
the answer set and the threshold are frozen here and can never be edited.

### The registrar's own source, and the attesters - from A

| # | Method | Field | Value |
|---|---|---|---|
| 2 | `attest` | `inquiry_id` | `0` |
| | | `text` | `Terminal gate log: container MSKU7712389 discharged and gated in at Rotterdam Maasvlakte II on 28 June, 14:02.` |
| 3 | `authorise` | `inquiry_id` | `0` |
| | | `who` | *B's address* |
| 4 | `authorise` | `inquiry_id` | `0` |
| | | `who` | *C's address* |
| 5 | `authorise` | `inquiry_id` | `0` |
| | | `who` | *D's address* |

### Two more sources - from B, then from C

| # | Account | Method | Field | Value |
|---|---|---|---|---|
| 6 | **B** | `attest` | `inquiry_id` | `0` |
| | | | `text` | `Carrier notification: vessel berthed Rotterdam 28 June; MSKU7712389 available for pickup from 29 June.` |
| 7 | **C** | `attest` | `inquiry_id` | `0` |
| | | | `text` | `Invoice 4471 for freight charges on MSKU7712389, issued 2 July, payable within 30 days.` |

Three live sources: the gate log says yes, the carrier says yes, the invoice
says nothing about when the container arrived. `inquiry(0).version` is now `3`.

### The first reading - from any account

| # | Method | Field | Value |
|---|---|---|---|
| 8 | `decide` | `inquiry_id` | `0` |

> ### ⛔ Stop here and read `reading(0)`
>
> Look at `vector`, `verdict` and `answer`.
>
> - **`yes|yes|unstated`, `established`, `yes`** - every source was read the same
>   way in both orders, two yeses reach the quorum, and the invoice counts for
>   nothing. Carry on.
> - **`yes|yes|yes`** - the model read the invoice as answering the question.
>   The verdict is still `established`, so carry on, but tell me: the invoice is
>   meant to show a source that does not speak.
> - **a yes you expected reads `unstated`** - the two orders read that source
>   differently, so it counted for nothing. If the verdict is still
>   `established`, carry on. If it is `insufficient`, stop and send me the whole
>   `reading(0)` JSON, and do not call `decide` again: it is refused until the
>   source set changes, by design.
> - **anything with `no` in it** - stop and send me the JSON.

### The dissent - from D, then a reading from any account

| # | Account | Method | Field | Value |
|---|---|---|---|---|
| 9 | **D** | `attest` | `inquiry_id` | `0` |
| | | | `text` | `Forwarder update: MSKU7712389 was rolled to the next sailing and did not discharge at Rotterdam until 4 July.` |
| 10 | any | `decide` | `inquiry_id` | `0` |

Read `reading(1)`: `vector` = `yes|yes|unstated|no`, **`verdict` =
`contested`**, `answer` empty, `counts` = `2|1`. Two sources say yes and one says
no, and the contract refuses to call that agreement. That refusal is the
strongest single artifact on the page.

`decide` was accepted here only because the source set changed:
`reading(0).sources` is `[0, 1, 2]` and `reading(1).sources` is `[0, 1, 2, 3]`.
`inquiry(0).version` is now `4`.

### The dissenter withdraws its own source - from D

| # | Account | Method | Field | Value |
|---|---|---|---|---|
| 11 | **D** | `withdraw` | `source_id` | `3` |

Only D can do this. The registrar cannot remove D's source, and neither can B or
C; a registrar who could remove a dissent would be curating the quorum. Read
`sources_of(0)`: four rows, row 3 `withdrawn` = `true`, its text still there.
`inquiry(0).live` is `3` and `version` is `5`.

### The third reading, and the revocation

| # | Account | Method | Field | Value |
|---|---|---|---|---|
| 12 | any | `decide` | `inquiry_id` | `0` |
| 13 | **A** | `revoke` | `inquiry_id` | `0` |
| | | | `who` | *D's address* |

Read `reading(2)`: `yes|yes|unstated`, **`established`**, `yes`. It reads the
same three sources the first reading did, and that is allowed because the last
reading saw a different set. Read `readings_of(0)`: three readings,
`established`, `contested`, `established`, each with the version and the
sources it read. The path from contested to established is on the record as a
sequence of readings, not as a verdict that changed.

After step 13, `delegation(0)` lists D with `active: false`. A revoked attester
keeps its row, and D's withdrawn source stays on the record, still naming D.

---

## 3 - Reads - free, no transaction

| Call | Argument | Expect |
|---|---|---|
| `verdict` | `0` | `established` |
| `answer` | `0` | `yes` |
| `inquiry` | `0` | `sources 4`, `live 3`, `readings 3`, `version 5`, `verdict established` |
| `sources_of` | `0` | four rows with four different `by` addresses, row 3 `withdrawn` |
| `readings_of` | `0` | `established` at version 3 over `[0, 1, 2]`, `contested` at version 4 over `[0, 1, 2, 3]`, `established` at version 5 over `[0, 1, 2]` |
| `reading` | `1` | `vector yes\|yes\|unstated\|no`, `counts 2\|1`, `verdict contested` |
| `delegation` | `0` | the registrar, B and C active, D inactive |
| `may_attest` | `0`, *D's address* | `false` after the revoke |
| `may_attest` | `0`, *B's address* | `false` - B already has a live source |

---

## 4 - Before the portal

```bash
python scripts/verify_deployment.py 0xYourAddress
```

Reads the source back out of the deploy transaction, compares it with
`contracts/quorum.py`, and runs `genvm-lint lint` on those bytes. It must print
**"The address is evidence for this repository. Safe to submit."**

If it prints anything else, do not submit that address. It needs `genvm-lint`
installed (`pip install genvm-linter`), and says so if it is missing.

---

## 5 - Done

Paste the address into README.md and SUBMISSION.md where `{address}` appears,
replace the expected values in SUBMISSION.md with the ones read back from the
chain, and push.

One step stays manual: uploading `brand/social.png` under
Settings -> General -> Social preview. GitHub has no API for it.
