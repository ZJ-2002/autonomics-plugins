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
mkdir -p "$AUTONOMICS_WORKDIR/.autonomics"
PREFIX="$AUTONOMICS_WORKDIR/.autonomics/ldsc_h2"
if python /opt/cachexia-official-ldsc/ldsc.py --h2 "$INPUT" --ref-ld-chr /panels/ref_ld/LDscore. \
  --w-ld-chr /panels/w_ld/weights.hm3_noMHC. --n-blocks "$LDSC_N_BLOCKS" \
  "$@" --out "$PREFIX" > "$AUTONOMICS_OUTPUT0" 2> "$PREFIX.stderr"; then
  cat "$PREFIX.stderr" >&2
  if [ -s "$PREFIX.log" ]; then cat "$PREFIX.log" > "$AUTONOMICS_OUTPUT0"; fi
  if [ ! -s "$AUTONOMICS_OUTPUT0" ]; then
    echo 'Official LDSC produced neither a nonempty log nor stdout' >&2
    exit 2
  fi
else
  status=$?
  cat "$PREFIX.stderr" >> "$AUTONOMICS_OUTPUT0"
  if [ -f "$PREFIX.log" ]; then cat "$PREFIX.log" >> "$AUTONOMICS_OUTPUT0"; fi
  exit "$status"
fi
