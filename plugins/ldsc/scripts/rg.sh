set -eu

# Two optional gzip inputs: decompressed into the private workspace.
for index in 0 1; do
  in_var="AUTONOMICS_INPUT${index}"
  eval "input=\$$in_var"
  case "$input" in
    *.gz)
      dst="$AUTONOMICS_WORKDIR/.autonomics/input-${index}.tsv"
      gzip -dc -- "$input" > "$dst"
      # Re-point the env var the script will read.
      eval "$in_var=\"\$dst\""
      ;;
  esac
done

# Optional flag carried as a possibly-empty env value.
EXTRA=""
if [ -n "$LDSC_RG_CHISQ_MAX" ]; then
  EXTRA="--chisq-max $LDSC_RG_CHISQ_MAX"
fi

ldsc \
  --rg "$AUTONOMICS_INPUT0","$AUTONOMICS_INPUT1" \
  --ref-ld-chr /panels/ref_ld/LDscore. \
  --w-ld-chr /panels/w_ld/weights.hm3_noMHC. \
  --n-blocks "$LDSC_RG_N_BLOCKS" \
  $EXTRA \
  --out "$AUTONOMICS_WORKDIR/ldsc_rg" \
  > "$AUTONOMICS_OUTPUT0" 2>&1