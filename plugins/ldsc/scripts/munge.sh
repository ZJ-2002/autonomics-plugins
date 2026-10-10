set -eu

# Single optional gzip input: decompressed into the private workspace
# so the official reader sees a plain sumstats table.
case "$AUTONOMICS_INPUT0" in
  *.gz)
    INPUT="$AUTONOMICS_WORKDIR/.autonomics/input-0.tsv"
    gzip -dc -- "$AUTONOMICS_INPUT0" > "$INPUT"
    ;;
  *)
    INPUT="$AUTONOMICS_INPUT0"
    ;;
esac

# Column-name overrides travel as env (possibly empty): the official
# CLI uses the column when the corresponding flag is non-empty.
ARGS=""
for col in snp n_col n_cas_col n_con_col a1 a2 p frq info info_list; do
  case "$col" in
    info_list) flag=--info-list ;;
    *)          flag=--${col} ;;
  esac
  val="$(eval echo "\$LDSC_MUNGE_${col}")"
  if [ -n "$val" ]; then
    ARGS="$ARGS $flag $val"
  fi
done

# Numeric thresholds.
for pair in "maf_min:LDSC_MUNGE_MAF_MIN" "info_min:LDSC_MUNGE_INFO_MIN"; do
  name=${pair%%:*}
  var=${pair#*:}
  val=$(eval echo "\$$var")
  if [ -n "$val" ]; then
    ARGS="$ARGS --${name} $val"
  fi
done

# N-study threshold and minimum N.
for name in nstudy_min n_min; do
  val="$(eval echo \$LDSC_MUNGE_$(echo $name | tr a-z A-Z))"
  if [ -n "$val" ]; then
    ARGS="$ARGS --${name} $val"
  fi
done

# Boolean flags.
[ -n "$LDSC_MUNGE_DANER" ]     && ARGS="$ARGS --daner"
[ -n "$LDSC_MUNGE_DANER_N" ]   && ARGS="$ARGS --daner-n"
[ -n "$LDSC_MUNGE_A1_IS_A2" ]  && ARGS="$ARGS --a1-is-a2"

OUT_PREFIX="$AUTONOMICS_WORKDIR/munged_sumstats"
munge_sumstats \
  $ARGS \
  --out "$OUT_PREFIX" \
  > "$AUTONOMICS_OUTPUT1" 2>&1
mv "$OUT_PREFIX.sumstats.gz" "$AUTONOMICS_OUTPUT0"
cat "$OUT_PREFIX.log" >> "$AUTONOMICS_OUTPUT1"