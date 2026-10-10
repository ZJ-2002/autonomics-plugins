set -eu

# Always-on optimizer settings travel with defaults; the six optional
# official flags travel as (possibly empty) env values, and absence means
# the flag is omitted exactly like the legacy Rust string building.
EXTRA=""
if [ -n "$MTAG_FORCE" ]; then
  EXTRA="$EXTRA --force"
fi
if [ -n "$MTAG_NO_OVERLAP" ]; then
  EXTRA="$EXTRA --no_overlap"
fi
if [ -n "$MTAG_PERFECT_GENCOV" ]; then
  EXTRA="$EXTRA --perfect_gencov"
fi
if [ -n "$MTAG_EQUAL_H2" ]; then
  EXTRA="$EXTRA --equal_h2"
fi
if [ -n "$MTAG_STD_BETAS" ]; then
  EXTRA="$EXTRA --std_betas"
fi
if [ -n "$MTAG_NUMERICAL_OMEGA" ]; then
  EXTRA="$EXTRA --numerical_omega"
fi

mtag \
  --sumstats "$AUTONOMICS_INPUT0","$AUTONOMICS_INPUT1" \
  --snp_name snpid \
  --z_name z \
  --n_name n \
  --eaf_name freq \
  --chr_name chr \
  --bpos_name bpos \
  --a1_name a1 \
  --a2_name a2 \
  --ld_ref_panel /panels/ld_ref/ \
  --out "$AUTONOMICS_WORKDIR/mtag" \
  --make_full_path \
  --time_limit "$MTAG_TIME_LIMIT_HOURS" \
  --tol "$MTAG_TOL" \
  $EXTRA
