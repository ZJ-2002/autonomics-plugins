set -eu

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

input=${AUTONOMICS_INPUT0:-}
log=${AUTONOMICS_OUTPUT0:-}
clumps=${AUTONOMICS_OUTPUT1:-}
chromosomes=${AUTONOMICS_OUTPUT2:-}
[ -n "$input" ] && [ -n "$log" ] && [ -n "$clumps" ] && [ -n "$chromosomes" ] ||
  fail 'All declared input/output ports are required'
for output in "$log" "$clumps" "$chromosomes"; do
  [ -d "$(dirname "$output")" ] || fail 'Output parent must be a directory'
done
log_identity=$(realpath -m "$log")
clumps_identity=$(realpath -m "$clumps")
chromosomes_identity=$(realpath -m "$chromosomes")
[ "$log_identity" != "$clumps_identity" ] && [ "$log_identity" != "$chromosomes_identity" ] &&
  [ "$clumps_identity" != "$chromosomes_identity" ] || fail 'Output paths must be distinct'
for output in "$log" "$clumps" "$chromosomes"; do
  if [ -e "$output" ] || [ -L "$output" ]; then
    fail 'Existing output must not be overwritten'
  fi
done
[ -f "$input" ] || fail 'Input must be a regular file'

layout=${PLINK2_CLUMP_INPUT_FORMAT:-}
case "$layout" in
  twosamplemr|plink_assoc)
    FIELD_ARGS='--clump-id-field SNP --clump-p-field P'
    ;;
  ieu_open_gwas)
    FIELD_ARGS='--clump-id-field variant --clump-p-field pval'
    ;;
  *) fail "unsupported input_format: $layout" ;;
esac
awk -v probability1="${PLINK2_CLUMP_P1:-}" -v probability2="${PLINK2_CLUMP_P2:-}" \
    -v correlation="${PLINK2_CLUMP_R2:-}" -v window="${PLINK2_CLUMP_KB:-}" \
    -v chromosome="${PLINK2_CLUMP_CHR:-}" '
function fail(message) { print message > "/dev/stderr"; exit 1 }
function number(value) { return value ~ /^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$/ }
BEGIN {
  if (!number(probability1) || !number(probability2) || !number(correlation) ||
      probability1 + 0 < 0 || probability1 + 0 > 1 || probability2 + 0 < 0 || probability2 + 0 > 1 ||
      correlation + 0 < 0 || correlation + 0 > 1) fail("Clump thresholds must be finite numbers in 0..1")
  if (probability2 + 0 < probability1 + 0) fail("clump_p2 must be >= clump_p1")
  if (correlation + 0 >= 1 - 1 / 17592186044416) fail("clump_r2 must be below the official 1-2^-44 boundary")
  if (window !~ /^[0-9]+$/ || window + 0 <= 0) fail("clump_kb must be a positive integer")
  if (chromosome != "" && (chromosome !~ /^[0-9]+$/ || chromosome + 0 < 1 || chromosome + 0 > 22))
    fail("chr must be an integer in 1..22")
}' </dev/null
CHR_SEQ='1 22'
CHR_ARGS=''
LABEL='autosomes 1..=22'
if [ -n "${PLINK2_CLUMP_CHR:-}" ]; then
  CHR_SEQ="$PLINK2_CLUMP_CHR $PLINK2_CLUMP_CHR"
  CHR_ARGS="--chr $PLINK2_CLUMP_CHR"
  LABEL="chromosome $PLINK2_CLUMP_CHR"
fi
for chromosome in $(seq $CHR_SEQ); do
  for extension in bed bim fam; do
    [ -f "/panels/plink_ref/1000G.EUR.QC.${chromosome}.${extension}" ] ||
      fail "Missing reference payload for chromosome ${chromosome}: ${extension}"
  done
done
stage=$(mktemp -d /work/.plink2-clump.XXXXXXXX)
mkdir "$stage/per_chr"
magic=$(od -An -tx1 -N2 "$input" | tr -d ' \n')
if [ "$magic" = 1f8b ]; then
  gzip -dc "$input" > "$stage/report.raw" || fail 'Compressed report is invalid'
else
  cp "$input" "$stage/report.raw"
fi
cat > "$stage/parse-report.awk" <<'AWK'
function fail(message) { failed = 1; print message > "/dev/stderr"; exit 1 }
function number(value) { return value ~ /^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$/ }
function csv_fields(record, fields, position, character, value, count, quoted, closed) {
  delete fields
  count = 1
  value = ""
  quoted = 0
  closed = 0
  for (position = 1; position <= length(record); position++) {
    character = substr(record, position, 1)
    if (quoted) {
      if (character == "\"") {
        if (substr(record, position + 1, 1) == "\"") { value = value "\""; position++ }
        else { quoted = 0; closed = 1 }
      } else value = value character
    } else if (closed) {
      if (character != ",") fail("Malformed CSV after closing quote")
      fields[count++] = value
      value = ""
      closed = 0
    } else if (character == "\"") {
      if (value != "") fail("Malformed CSV quote")
      quoted = 1
    } else if (character == ",") {
      fields[count++] = value
      value = ""
    } else value = value character
  }
  if (quoted) return 0
  fields[count] = value
  return count
}
function emit(fields, count, position, value) {
  for (position = 1; position <= count; position++) {
    value = fields[position]
    if (value ~ /[[:space:][:cntrl:]]/) fail("Report fields must be single PLINK tokens")
    if (value == "") value = "NA"
    printf "%s%s", position == 1 ? "" : "\t", value
  }
  printf "\n"
}
{
  record = $0
  sub(/\r$/, "", record)
  if (record ~ /^[[:space:]]*$/) next
  if (layout == "ieu_open_gwas") {
    while ((count = csv_fields(record, fields)) == 0) {
      if ((getline continuation) <= 0) fail("Unterminated quoted CSV field")
      sub(/\r$/, "", continuation)
      record = record "\n" continuation
    }
  } else {
    if (record ~ /\t/) count = split(record, fields, "\t")
    else {
      sub(/^[[:space:]]+/, "", record)
      sub(/[[:space:]]+$/, "", record)
      count = split(record, fields, /[[:space:]]+/)
    }
  }
  if (!header_seen) {
    for (position = 1; position <= count; position++) {
      if (fields[position] == "") fail("Report header names must not be empty")
      if (fields[position] in columns) fail("Duplicate report header")
      columns[fields[position]] = position
    }
    identifier_name = layout == "ieu_open_gwas" ? "variant" : "SNP"
    probability_name = layout == "ieu_open_gwas" ? "pval" : "P"
    if (!(identifier_name in columns) || !(probability_name in columns)) fail("Required report columns missing")
    identifier_column = columns[identifier_name]
    probability_column = columns[probability_name]
    header_count = count
    header_seen = 1
  } else {
    if (count != header_count) fail("Ragged report row")
    if (fields[identifier_column] == "") fail("Variant identifier is empty")
    probability = fields[probability_column]
    if (probability != "NA" && (!number(probability) || probability + 0 < 0 || probability + 0 > 1))
      fail("Invalid report P value")
  }
  emit(fields, count)
}
END { if (!failed && !header_seen) fail("Report header is required") }
AWK
awk -v layout="$layout" -f "$stage/parse-report.awk" "$stage/report.raw" > "$stage/report.tsv"
printf 'input_sha256: ' > "$log"
sha256sum "$input" >> "$log"
printf 'input_format: %s; normalized empty ancillary cells: NA\n' "$layout" >> "$log"
printf 'raw_official_artifact_directory: %s\n' "$stage/per_chr" >> "$log"
header=$(printf '#CHROM\tPOS\tID\tP\tTOTAL\tNONSIG\tS0.05\tS0.01\tS0.001\tS0.0001\tSP2')
printf 'SOURCE_CHR\t%s\n' "$header" > "$stage/clumps.tsv"
: > "$stage/chromosomes.tsv"
for chromosome in $(seq $CHR_SEQ); do
  out_prefix=$stage/per_chr/clump.chr${chromosome}
  if ! plink2 \
      --bfile "/panels/plink_ref/1000G.EUR.QC.${chromosome}" \
      --clump cols=+chrom,+pos "$stage/report.tsv" \
      $FIELD_ARGS $CHR_ARGS \
      --clump-p1 "$PLINK2_CLUMP_P1" --clump-p2 "$PLINK2_CLUMP_P2" \
      --clump-r2 "$PLINK2_CLUMP_R2" --clump-kb "$PLINK2_CLUMP_KB" \
      --threads 2 --memory 1024 require --out "$out_prefix" \
      >> "$log" 2>&1; then
    fail "plink2 clump failed on chromosome ${chromosome}"
  fi
  if [ -f "${out_prefix}.clumps" ]; then
    [ "$(head -n 1 "${out_prefix}.clumps")" = "$header" ] || fail 'Official clumps schema changed'
    tail -n +2 "${out_prefix}.clumps" > "$stage/rows.tsv"
    sed "s/^/${chromosome}\t/" "$stage/rows.tsv" >> "$stage/clumps.tsv"
  else
    grep -q 'No significant --clump results' "${out_prefix}.log" || fail 'Official clumps output unexpectedly missing'
  fi
  printf 'chr\t%s\n' "$chromosome" >> "$stage/chromosomes.tsv"
done
printf 'plink2 clump completed across %s\n' "$LABEL" >> "$log"
for output in "$clumps" "$chromosomes"; do
  if [ -e "$output" ] || [ -L "$output" ]; then
    fail 'Output appeared during execution; no analytical publication allowed'
  fi
done
cp "$stage/clumps.tsv" "$clumps"
cp "$stage/chromosomes.tsv" "$chromosomes"
