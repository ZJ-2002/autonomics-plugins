#!/bin/sh
# Every executable R source is a File dependency; no host paths are opened.
set -eu
test "$AUTONOMICS_INPUT_COUNT" = 4
test "$AUTONOMICS_OUTPUT_COUNT" = 3
test "$(sha256sum "$AUTONOMICS_INPUT3" | cut -d ' ' -f 1)" = bc9f4c4fdb0bd07615a1afa4c89ee2a33814254f064f3f4148b17b7aea30f79a
test "$(sha256sum "$AUTONOMICS_INPUT2" | cut -d ' ' -f 1)" = f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd
test ! -e "$AUTONOMICS_OUTPUT0"
test ! -e "$AUTONOMICS_OUTPUT1"
test ! -e "$AUTONOMICS_OUTPUT2"
Rscript --vanilla "$AUTONOMICS_INPUT3" "$AUTONOMICS_INPUT0" "$AUTONOMICS_INPUT1" "$AUTONOMICS_INPUT2" "$AUTONOMICS_WORKDIR/.real-official-output"
cp -n "$AUTONOMICS_WORKDIR/.real-official-output/real-adjusted.tsv" "$AUTONOMICS_OUTPUT0"
cp -n "$AUTONOMICS_WORKDIR/.real-official-output/real-adjustment.RDS" "$AUTONOMICS_OUTPUT1"
cp -n "$AUTONOMICS_WORKDIR/.real-official-output/real-adjustment.json" "$AUTONOMICS_OUTPUT2"
