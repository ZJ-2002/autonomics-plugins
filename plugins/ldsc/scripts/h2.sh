set -eu

# Gzip inputs are decompressed into the private workspace so the official
# LDSC reader sees a plain sumstats table (mirrors the legacy wrapper's
# prepare_input helper).
case "$AUTONOMICS_INPUT0" in
  *.gz)
    INPUT="$AUTONOMICS_WORKDIR/.autonomics/input-0.tsv"
    gzip -dc -- "$AUTONOMICS_INPUT0" > "$INPUT"
    ;;
  *)
    INPUT="$AUTONOMICS_INPUT0"
    ;;
esac

# Optional flags travel as (possibly empty) env values; absence means the
# official LDSC defaults apply.
EXTRA=""
if [ -n "$LDSC_INTERCEPT_H2" ]; then
  EXTRA="$EXTRA --intercept-h2 $LDSC_INTERCEPT_H2"
fi
if [ -n "$LDSC_CHISQ_MAX" ]; then
  EXTRA="$EXTRA --chisq-max $LDSC_CHISQ_MAX"
fi

ldsc \
  --h2 "$INPUT" \
  --ref-ld-chr /panels/ref_ld/LDscore. \
  --w-ld-chr /panels/w_ld/weights.hm3_noMHC. \
  --n-blocks "$LDSC_N_BLOCKS" \
  $EXTRA \
  --out "$AUTONOMICS_WORKDIR/ldsc_h2" \
  > "$AUTONOMICS_OUTPUT0" 2>&1
