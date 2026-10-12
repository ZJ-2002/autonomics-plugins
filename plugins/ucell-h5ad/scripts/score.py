"""H5AD X to official UCell 2.16.0, without replacing its score calculation."""

from contextlib import ExitStack
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import anndata as ad
import numpy as np
from scipy import sparse


R_SOURCE = r'''
arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(as.character(utils::packageVersion("UCell")) == "2.16.0")
data.table::setDTthreads(1)
table <- read.delim(arguments[1], check.names = FALSE, colClasses = "character",
  na.strings = NULL, quote = "", comment.char = "", blank.lines.skip = FALSE,
  fill = FALSE, fileEncoding = "UTF-8")
members <- read.delim(arguments[2], check.names = FALSE, colClasses = "character",
  na.strings = NULL, quote = "", comment.char = "", blank.lines.skip = FALSE,
  fill = FALSE, fileEncoding = "UTF-8")
stopifnot(names(table)[1] == "gene", identical(names(members), c("signature", "gene")))
expression <- matrix(as.numeric(as.matrix(table[, -1, drop = FALSE])),
  nrow = nrow(table), dimnames = list(table[[1]], names(table)[-1]))
stopifnot(all(is.finite(expression)), !anyDuplicated(rownames(expression)),
          !anyDuplicated(colnames(expression)))
program_names <- unique(members$signature)
features <- lapply(program_names, function(program) members$gene[members$signature == program])
names(features) <- program_names
scores <- UCell::ScoreSignatures_UCell(expression, features = features,
  maxRank = 1500, w_neg = 1, missing_genes = "impute", ties.method = "average",
  BPPARAM = BiocParallel::SerialParam(), ncores = 1, chunk.size = 100,
  force.gc = FALSE, name = "")
stopifnot(identical(rownames(scores), colnames(expression)),
          identical(colnames(scores), program_names), all(is.finite(scores)))
formatted <- apply(scores, 2, function(values) sprintf("%.17g", values))
formatted <- matrix(formatted, nrow = nrow(scores), dimnames = dimnames(scores))
output <- data.frame(cell = rownames(scores), formatted, check.names = FALSE)
write.table(output, arguments[3], sep = "\t", quote = FALSE, row.names = FALSE,
            fileEncoding = "UTF-8")
cat("Official UCell", as.character(utils::packageVersion("UCell")),
    "; effective maxRank", min(1500, nrow(expression)), "; cells", ncol(expression), "\n")
'''


class ContractError(RuntimeError):
    pass


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def required_path(name):
    value = os.environ.get(name)
    if not value:
        raise ContractError('missing required environment variable: ' + name)
    return Path(value)


def lexical(value):
    return isinstance(value, str) and bool(value) and not any(character in value for character in '\t\r\n')


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ContractError('duplicate JSON signature key: ' + name)
        result[name] = value
    return result


def signatures(data):
    try:
        programs = json.loads(os.environ['SC_P_JSON_GENE_SETS'], object_pairs_hook=unique_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (KeyError, ValueError) as error:
        raise ContractError('gene_sets must be a strict nonempty JSON object') from error
    if not isinstance(programs, dict) or not programs:
        raise ContractError('gene_sets must be a strict nonempty JSON object')
    known = set(data.var_names)
    summaries = {}
    for name, genes in programs.items():
        if not lexical(name) or name in data.obs:
            raise ContractError('signature names must be nonempty lexical IDs and must not overwrite obs columns')
        if not isinstance(genes, list) or not genes or not all(lexical(gene) for gene in genes):
            raise ContractError('each signature must contain nonempty lexical gene identifiers')
        identifiers = [gene[:-1] if gene.endswith(('+', '-')) else gene for gene in genes]
        if not all(lexical(gene) for gene in identifiers) or len(set(identifiers)) != len(identifiers):
            raise ContractError('duplicate or ambiguous signed signature gene identities')
        if not any(gene in known for gene in identifiers):
            raise ContractError('each signature must have at least one matching gene;no automatic mapping')
        if len(genes) > min(1500, data.n_vars):
            raise ContractError('signature exceeds official effective maxRank')
        summaries[name] = {'genes_requested': len(genes), 'genes_present': sum(gene in known for gene in identifiers),
            'missing_genes': [gene for gene in identifiers if gene not in known], 'signed_members': genes,
            'positive_members': [gene for gene in genes if not gene.endswith('-')],
            'negative_members': [gene for gene in genes if gene.endswith('-')]}
    return programs, summaries


def validate(data):
    if data.X is None or data.n_obs == 0 or data.n_vars == 0:
        raise ContractError('nonempty materialized X is required')
    if data.obs_names.has_duplicates or data.var_names.has_duplicates:
        raise ContractError('cell and gene axes must be unique')
    if not all(lexical(name) for name in [*data.obs_names, *data.var_names]):
        raise ContractError('cell and gene axes must be nonempty lexical identifiers')
    matrix = data.X
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if values.dtype.kind not in 'biuf' or not np.isfinite(values).all():
        raise ContractError('all selected X values must be finite real numbers')
    if values.dtype.kind in 'iu' and ((values > 2**53).any() or (values.dtype.kind == 'i' and (values < -(2**53)).any())):
        raise ContractError('integer X values must be exactly representable in official R double input')
    if sparse.issparse(matrix):
        try:
            matrix.copy().check_format(full_check=True)
        except ValueError as error:
            raise ContractError('invalid sparse matrix structure') from error
        if values.dtype.kind in 'iu' and not matrix.has_canonical_format:
            coordinates = matrix.tocoo()
            order = np.lexsort((coordinates.col, coordinates.row))
            previous_coordinate = None
            total = 0
            for index in order:
                coordinate = (int(coordinates.row[index]), int(coordinates.col[index]))
                if coordinate != previous_coordinate:
                    if abs(total) > 2**53:
                        raise ContractError('duplicate integer coordinates exceed exact official R double input')
                    previous_coordinate, total = coordinate, 0
                total += int(coordinates.data[index])
            if abs(total) > 2**53:
                raise ContractError('duplicate integer coordinates exceed exact official R double input')
    return matrix


def score(data, matrix, programs, summaries):
    scores = {name: np.empty(data.n_obs, dtype=np.float64) for name in programs}
    batches = []
    block_cells = max(1, min(128, 2_000_000 // data.n_vars))
    variables = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    with tempfile.TemporaryDirectory(prefix='ucell-official-') as temporary:
        directory = Path(temporary)
        helper = directory / 'score.R'
        helper.write_text(R_SOURCE)
        members = directory / 'signatures.tsv'
        with members.open('w', encoding='utf-8', newline='') as handle:
            handle.write('signature\tgene\n')
            for name, genes in programs.items():
                for gene in genes:
                    handle.write(name + '\t' + gene + '\n')
        for start in range(0, data.n_obs, block_cells):
            stop = min(start + block_cells, data.n_obs)
            block = matrix[start:stop]
            dense = block.toarray() if sparse.issparse(block) else np.asarray(block)
            if not np.isfinite(dense).all():
                raise ContractError('selected X block became nonfinite during sparse materialization')
            if dense.dtype.kind in 'iu' and ((dense > 2**53).any() or (dense.dtype.kind == 'i' and (dense < -(2**53)).any())):
                raise ContractError('materialized integer X must be exactly representable in official R double input')
            expression = directory / 'matrix.tsv'
            output = directory / 'scores.tsv'
            with expression.open('w', encoding='utf-8', newline='') as handle:
                handle.write('gene\t' + '\t'.join(data.obs_names[start:stop]) + '\n')
                for index, gene in enumerate(data.var_names):
                    handle.write(gene + '\t' + '\t'.join(format(float(value), '.17g') for value in dense[:, index]) + '\n')
            result = subprocess.run(['Rscript', '--vanilla', str(helper), str(expression), str(members), str(output)],
                                    env=variables, capture_output=True, timeout=3300)
            if result.returncode != 0:
                raise ContractError('official UCell failed: ' + result.stderr.decode(errors='replace')[-4000:])
            with output.open(encoding='utf-8', newline='') as handle:
                rows = list(csv.reader(handle, delimiter='\t', quoting=csv.QUOTE_NONE))
            if rows[0] != ['cell', *programs] or [row[0] for row in rows[1:]] != list(data.obs_names[start:stop]):
                raise ContractError('official score axes do not match exact requested cell/signature identities')
            if any(len(row) != len(programs) + 1 for row in rows[1:]):
                raise ContractError('official score table is not rectangular')
            values = np.array([[float(value) for value in row[1:]] for row in rows[1:]], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ContractError('official score table contains undefined scores')
            for index, name in enumerate(programs):
                scores[name][start:stop] = values[:, index]
            batches.append({'start_cell': start, 'stop_cell': stop, 'matrix_sha256': digest(expression),
                'score_table_sha256': digest(output), 'stdout': result.stdout.decode(errors='replace'),
                'stderr': result.stderr.decode(errors='replace')})
    for name, values in scores.items():
        data.obs[name] = values
        summaries[name].update(mean=float(values.mean()),
            **dict(zip(['min', 'p25', 'median', 'p75', 'max'], np.percentile(values, [0,25,50,75,100]).tolist())))
    data.uns['ucell_params'] = {'method': 'UCell', 'version': '2.16.0', 'maxRank': 1500,
        'effective_maxRank': min(1500, data.n_vars), 'w_neg': 1., 'missing_genes': 'impute',
        'ties_method': 'average', 'matrix': 'X', 'gene_sets': {name: len(genes) for name, genes in programs.items()}}
    return {'schema_version': '2.0', 'operation': 'ucell_score', 'cells': data.n_obs, 'genes': data.n_vars,
        'method': 'Official UCell', 'version': '2.16.0', 'source_matrix': 'X',
        'parameters': dict(data.uns['ucell_params']), 'gene_sets': summaries, 'cell_ids': list(data.obs_names),
        'gene_ids': list(data.var_names), 'score_columns': list(programs), 'batches': batches,
        'R_call_sha256': hashlib.sha256(R_SOURCE.encode()).hexdigest(),
        'negative_only_semantics': 'Official positive-minus-weighted-negative score clipped below at zero;not inferred reverse enrichment',
        'study_scale_species_gene_mapping_signature_and_donor_eligibility': 'NOT_VERIFIED',
        'scientific_implementation_lock': 'NOT_GRANTED', 'scientific_release': 'NOT_GRANTED', 'G0': False,
        'packages': {name: importlib.metadata.version(name) for name in ['anndata', 'numpy', 'scipy', 'pandas', 'h5py']}}


def publish(data, report, output, report_path):
    published = []
    with ExitStack() as stack:
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.ucell-', dir=output.parent)))
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.ucell-', dir=report_path.parent)))
        staged, staged_report = directory / 'output.h5ad', report_directory / 'report.json'
        data.write_h5ad(staged, compression='lzf')
        report['outputs'] = [{'port': 0, 'name': output.name, 'bytes': staged.stat().st_size, 'sha256': digest(staged)}]
        report['report_hash_policy'] = 'port_1_hash_recorded_externally_not_recursively'
        staged_report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
        for path in [staged, staged_report]:
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        try:
            for source, destination in [(staged, output), (staged_report, report_path)]:
                status = source.stat()
                os.link(source, destination)
                published.append((destination, (status.st_dev, status.st_ino)))
        except OSError:
            for destination, identity in reversed(published):
                try:
                    status = destination.lstat()
                    if (status.st_dev, status.st_ino) == identity:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise


def run():
    source, output, report_path = [required_path(name) for name in ['AUTONOMICS_INPUT0', 'AUTONOMICS_OUTPUT0', 'AUTONOMICS_OUTPUT1']]
    if not source.is_file() or len({path.resolve() for path in [source, output, report_path]}) != 3:
        raise ContractError('input must be readable and input/output paths must be distinct')
    for path in [output, report_path]:
        if os.path.lexists(path):
            raise ContractError('refusing to overwrite existing output: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
    checksum = digest(source)
    data = ad.read_h5ad(source)
    matrix = validate(data)
    programs, summaries = signatures(data)
    previous_parameters_present = 'ucell_params' in data.uns
    report = score(data, matrix, programs, summaries)
    if digest(source) != checksum:
        raise ContractError('input changed during computation')
    report.update(input_sha256=checksum, overwritten_ucell_parameter_metadata=previous_parameters_present)
    publish(data, report, output, report_path)


if __name__ == '__main__':
    try:
        run()
    except ContractError as error:
        print('h5ad_ucell_score: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print('h5ad_ucell_score: ' + str(error), file=sys.stderr)
        raise SystemExit(3)
