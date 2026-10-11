set -eu
INPUT=$AUTONOMICS_INPUT0
case "$INPUT" in
  *.gz)
    INPUT="$AUTONOMICS_WORKDIR/.autonomics/input-0.tsv"
    mkdir -p "$AUTONOMICS_WORKDIR/.autonomics"
    gzip -dc -- "$AUTONOMICS_INPUT0" > "$INPUT"
    ;;
esac
set --
if [ -n "${LDSC_INTERCEPT_H2-}" ]; then set -- "$@" --intercept-h2 "$LDSC_INTERCEPT_H2"; fi
if [ -n "${LDSC_CHISQ_MAX-}" ]; then set -- "$@" --chisq-max "$LDSC_CHISQ_MAX"; fi
PREFIX="$AUTONOMICS_WORKDIR/ldsc_h2"
if ldsc --h2 "$INPUT" --ref-ld-chr /panels/ref_ld/LDscore. \
  --w-ld-chr /panels/w_ld/weights.hm3_noMHC. --n-blocks "$LDSC_N_BLOCKS" \
  "$@" --out "$PREFIX" > "$AUTONOMICS_OUTPUT0" 2>&1; then
  # This pinned image's INFO logger writes the official summary only to .log.
  # Publish that log, preserving any separate process diagnostics in stderr.
  if [ -s "$AUTONOMICS_OUTPUT0" ]; then cat "$AUTONOMICS_OUTPUT0" >&2; fi
  cat "$PREFIX.log" > "$AUTONOMICS_OUTPUT0"
else
  status=$?
  if [ -f "$PREFIX.log" ]; then cat "$PREFIX.log" >> "$AUTONOMICS_OUTPUT0"; fi
  exit "$status"
fi
