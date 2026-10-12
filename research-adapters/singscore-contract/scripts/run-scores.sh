#!/bin/sh
set -eu
exec Rscript --vanilla /opt/autonomics/score.R \
    "$AUTONOMICS_INPUT0" "$AUTONOMICS_INPUT1" "$AUTONOMICS_INPUT2" \
    "$AUTONOMICS_OUTPUT0" "$AUTONOMICS_OUTPUT1" "$AUTONOMICS_OUTPUT2"
