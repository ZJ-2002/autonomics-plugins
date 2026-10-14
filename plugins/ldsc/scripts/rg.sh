set -eu
INPUT0=$AUTONOMICS_INPUT0
INPUT1=$AUTONOMICS_INPUT1
mkdir -p "$AUTONOMICS_WORKDIR/.autonomics"
for index in 0 1; do
  case "$index" in 0) input=$INPUT0 ;; 1) input=$INPUT1 ;; esac
  case "$input" in
    *.gz)
      destination="$AUTONOMICS_WORKDIR/.autonomics/input-${index}.tsv"
      gzip -dc -- "$input" > "$destination"
      case "$index" in 0) INPUT0=$destination ;; 1) INPUT1=$destination ;; esac
      ;;
  esac
done
set --
if [ -n "${LDSC_RG_CHISQ_MAX-}" ]; then set -- "$@" --chisq-max "$LDSC_RG_CHISQ_MAX"; fi
PREFIX="$AUTONOMICS_WORKDIR/.autonomics/ldsc_rg"
if python /opt/cachexia-official-ldsc/ldsc.py --rg "$INPUT0,$INPUT1" --ref-ld-chr /panels/ref_ld/LDscore. \
  --w-ld-chr /panels/w_ld/weights.hm3_noMHC. --n-blocks "$LDSC_RG_N_BLOCKS" \
  "$@" --out "$PREFIX" > "$AUTONOMICS_OUTPUT0" 2> "$PREFIX.stderr"; then
  cat "$PREFIX.stderr" >&2
  if [ -s "$PREFIX.log" ]; then cat "$PREFIX.log" > "$AUTONOMICS_OUTPUT0"; fi
  if [ ! -s "$AUTONOMICS_OUTPUT0" ]; then
    echo 'Official LDSC produced neither a nonempty log nor stdout' >&2
    exit 2
  fi
  # Upstream catches pair exceptions and can exit zero with a missing result.
  # Preserve its diagnostic log while refusing a successful method node.
  if grep -q 'ERROR computing rg for phenotype' "$AUTONOMICS_OUTPUT0"; then
    echo 'Official LDSC reported a failed genetic-correlation component' >&2
    exit 2
  fi
else
  status=$?
  cat "$PREFIX.stderr" >> "$AUTONOMICS_OUTPUT0"
  if [ -f "$PREFIX.log" ]; then cat "$PREFIX.log" >> "$AUTONOMICS_OUTPUT0"; fi
  exit "$status"
fi
