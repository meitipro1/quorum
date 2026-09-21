#!/usr/bin/env bash
#
# deploy.sh - deploy Quorum from the command line and open the first inquiry.
#
#   ./scripts/deploy.sh studionet 0xAttesterB 0xAttesterC 0xAttesterD
#
# Quorum takes ONE live source per account, on purpose: a second source from
# the same account is the first one twice. So the demo needs four accounts, and
# the CLI signs with one key. This script does the registrar's half - lint,
# deploy, open, the registrar's own source, the three authorisations - and then
# prints exactly what the other accounts do. The recommended route is
# DEPLOY.md: the Studio web interface at studio.genlayer.com, where the account
# selector signs as each of the four in turn, and the on-chain table in
# SUBMISSION.md describes THAT run. Never put a private key into a file or hand
# one to a tool.
#
# Two things the CLI does that a script has to allow for:
#   - `genlayer write` exits 0 for a transaction that was rolled back, timed
#     out or never decided, so `set -e` does NOT stop on a refused call. Read
#     every receipt; the reads below exist for that.
#   - `genlayer deploy` prints the 64 character transaction hash before the
#     contract address, so a bare `0x[0-9a-fA-F]{40}` grep captures the first
#     40 characters of the hash. The address is taken from the line that names
#     it, bounded on both sides.
#
# Requires: npm i -g genlayer

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NETWORK="${1:-studionet}"
shift || true
ATTESTERS=("$@")
gold() { printf '\033[33m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

gold "Quorum -> $NETWORK"
# `network` is a command group, not a value: `genlayer network studionet`
# answers "unknown command" and exits 1.
genlayer network set "$NETWORK"

dim "linting"
# genvm-lint needs its subcommand, and utf-8 stdout: the linter prints a tick
# on success and dies encoding it under the cp1252 stdout Windows hands a child
# process, reporting a PASSING contract as failed.
PYTHONIOENCODING=utf-8 genvm-lint lint contracts/quorum.py

OUT=$(genlayer deploy --contract contracts/quorum.py)
printf '%s\n' "$OUT"
ADDR=$(printf '%s\n' "$OUT" | grep -i 'address' | grep -oE '\b0x[0-9a-fA-F]{40}\b' | head -1 || true)
if [ -z "$ADDR" ]; then
  echo "could not read a contract address from the deploy output above" >&2
  exit 1
fi
gold "deployed at $ADDR"

QUESTION="Did the container arrive at the Rotterdam terminal before the 30 June cutoff?"
GATE="Terminal gate log: container MSKU7712389 discharged and gated in at Rotterdam Maasvlakte II on 28 June, 14:02."

# --args is variadic. A JSON array is ONE argument, not the argument list, so
# every value below is a separate token.
dim "open()      the question, the answer set and the quorum, frozen here"
genlayer write "$ADDR" open --args "$QUESTION" "yes|no" 2

dim "attest()    the registrar's own source"
genlayer write "$ADDR" attest --args 0 "$GATE"

for who in "${ATTESTERS[@]}"; do
  dim "authorise() $who"
  genlayer write "$ADDR" authorise --args 0 "$who"
done
genlayer call "$ADDR" inquiry --args 0
genlayer call "$ADDR" delegation --args 0

cat <<TXT

  Contract:  $ADDR
  Explorer:  https://explorer-studio.genlayer.com/address/$ADDR

The registrar's half is on chain. The rest needs the other accounts, one
source each, and is written out step by step in DEPLOY.md (steps 6 to 13):

  attester B      attest(0, the carrier notification)        -> reads yes
  attester C      attest(0, the freight invoice)             -> reads unstated
  any account     decide(0)                                  -> established, yes
  attester D      attest(0, the forwarder's rolled update)   -> reads no
  any account     decide(0)                                  -> contested
  attester D      withdraw(3), its own source
  any account     decide(0)                                  -> established, yes
  registrar       revoke(0, D)

Before submitting, prove the address is evidence for THIS repository:

  python scripts/verify_deployment.py $ADDR

TXT
