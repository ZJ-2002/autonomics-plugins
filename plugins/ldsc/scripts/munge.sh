set -eu

# Input transport is private; never infer an input filename from the output.
INPUT=$AUTONOMICS_INPUT0
case "$INPUT" in
  *.gz)
    INPUT="$AUTONOMICS_WORKDIR/.autonomics/input-0.tsv"
    mkdir -p "$AUTONOMICS_WORKDIR/.autonomics"
    gzip -dc -- "$AUTONOMICS_INPUT0" > "$INPUT"
    ;;
esac

# Build argv with POSIX positional parameters. Each column name remains one
# argument, including spaces or shell metacharacters. Official option names
# contain hyphens and, for sample-size columns, a capital N.
set --
for name in SNP N_COL N_CAS_COL N_CON_COL A1 A2 P FRQ INFO INFO_LIST SIGNED_SUMSTATS NSTUDY; do
  case "$name" in
    SNP) flag=--snp ;; N_COL) flag=--N-col ;;
    N_CAS_COL) flag=--N-cas-col ;; N_CON_COL) flag=--N-con-col ;;
    A1) flag=--a1 ;; A2) flag=--a2 ;; P) flag=--p ;; FRQ) flag=--frq ;;
    INFO) flag=--info ;; INFO_LIST) flag=--info-list ;;
    SIGNED_SUMSTATS) flag=--signed-sumstats ;; NSTUDY) flag=--nstudy ;;
  esac
  # Only the fixed variable name is evaluated; the value is never shell code.
  eval "value=\${LDSC_MUNGE_${name}-}"
  if [ -n "$value" ]; then set -- "$@" "$flag" "$value"; fi
done
for name in INFO_MIN MAF_MIN N_MIN NSTUDY_MIN; do
  case "$name" in
    INFO_MIN) flag=--info-min ;; MAF_MIN) flag=--maf-min ;;
    N_MIN) flag=--n-min ;; NSTUDY_MIN) flag=--nstudy-min ;;
  esac
  eval "value=\${LDSC_MUNGE_${name}-}"
  if [ -n "$value" ]; then set -- "$@" "$flag" "$value"; fi
done
for name in DANER DANER_N A1_INC; do
  case "$name" in DANER) flag=--daner ;; DANER_N) flag=--daner-n ;; A1_INC) flag=--a1-inc ;; esac
  eval "value=\${LDSC_MUNGE_${name}-}"
  case "$value" in ''|false|0) ;; true|1) set -- "$@" "$flag" ;; *) echo "invalid presence flag: $name" >&2; exit 2 ;; esac
done
# Legacy compatibility field is not an official LDSC option. Preserve parsing
# of old specs, but explicitly refuse a true request rather than misinterpret it.
case "${LDSC_MUNGE_A1_IS_A2-}" in ''|false|0) ;; *) echo 'a1_is_a2 is not an official LDSC option; use an explicitly reviewed allele convention' >&2; exit 2 ;; esac

OUT_PREFIX="$AUTONOMICS_WORKDIR/munged_sumstats"
if munge_sumstats "$@" --sumstats "$INPUT" --out "$OUT_PREFIX" > "$AUTONOMICS_OUTPUT1" 2>&1; then
  # This image's official logger writes to .log, not stdout. Keep the complete
  # official log exactly once. Forward separate process diagnostics to the
  # runtime's stderr stream before replacing the temporary capture.
  if [ -s "$AUTONOMICS_OUTPUT1" ]; then cat "$AUTONOMICS_OUTPUT1" >&2; fi
  cat "$OUT_PREFIX.log" > "$AUTONOMICS_OUTPUT1"
else
  status=$?
  if [ -f "$OUT_PREFIX.log" ]; then cat "$OUT_PREFIX.log" >> "$AUTONOMICS_OUTPUT1"; fi
  exit "$status"
fi
mv "$OUT_PREFIX.sumstats.gz" "$AUTONOMICS_OUTPUT0"
