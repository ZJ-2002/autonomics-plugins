import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile


FIELDS = ['test_id', 'row_id', 'field', 'value', 'value_kind']
ROLE = 'SURVEY_TECHNICAL_BACKGROUND_ASSOCIATION_NOT_CANCER_MECHANISM'
MODES = {'design', 'mean', 'var', 'quantile', 'glm', 'ttest', 'post', 'rake', 'calibrate', 'trim'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def unique_object(items):
    require(len({key for key, value in items}) == len(items), 'Duplicate JSON keys')
    return dict(items)


def technical_contract_version():
    version = os.environ.get('AUTONOMICS_TECHNICAL_CONTRACT_VERSION', '1')
    require(version in {'1', '2'}, 'Unknown installed technical contract version')
    return int(version)


def validate_technical_identity(request, upstream):
    version = technical_contract_version()
    roles = {'SYNTHETIC_TECHNICAL_INPUT'} if version == 1 else {'SYNTHETIC_TECHNICAL_INPUT', 'EMPIRICAL_TECHNICAL_INPUT'}
    require(request['scope'] == 'TECHNICAL_ONLY_NOT_G0' and request['input_role'] in roles and
            request['scientific_qualification'] == 'NOT_GRANTED' and request['analysis_role'] == ROLE and
            request['mode'] in MODES, 'Installed technical scope and truthful input role required')
    if version == 2:
        require(type(request.get('schema_version')) is int and request['schema_version'] == 2 and
                type(upstream.get('schema_version')) is int and upstream['schema_version'] == 2 and
                upstream.get('input_role') == request['input_role'] and
                upstream.get('scientific_qualification') == 'NOT_GRANTED' and
                type(upstream.get('state_schema_version')) is int and upstream['state_schema_version'] == 2 and
                upstream.get('state_input_role') == request['input_role'] and
                upstream.get('state_scientific_qualification') == 'NOT_GRANTED', 'Role-bound v2 request, state and audit identity required')
        state_sha = upstream.get('output1_sha256')
        require(isinstance(state_sha, str) and len(state_sha) == 64 and
                all(character in '0123456789abcdef' for character in state_sha), 'Original complete RDS state hash required')
    else:
        require('schema_version' not in request or type(request['schema_version']) is int and request['schema_version'] == 1,
                'V2 request cannot enter installed v1 typed node')
        require('schema_version' not in upstream or type(upstream['schema_version']) is int and upstream['schema_version'] == 1,
                'V2 audit cannot enter installed v1 typed node')


def parse_summary(payload, upstream):
    request_text = upstream['request_json']
    require(isinstance(request_text, str) and hashlib.sha256(request_text.encode()).hexdigest() == upstream['contract_sha256'],
            'Upstream contract identity mismatch')
    request = json.loads(request_text, object_pairs_hook=unique_object)
    require(upstream['status'] == 'TECHNICAL_PASS_NOT_SCIENTIFIC' and
            upstream['G0_granted'] is False and upstream['scientific_qualification_granted'] is False and
            upstream['resident_deployment_granted'] is False, 'Qualified technical upstream audit required')
    validate_technical_identity(request, upstream)
    require(hashlib.sha256(payload).hexdigest() == upstream['output0_sha256'], 'Upstream summary identity mismatch')
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8')), delimiter='\t', strict=True)
    require(reader.fieldnames == FIELDS, 'Exact survey summary columns required')
    rows = list(reader)
    require(type(upstream['summary_rows']) is int and 0 < len(rows) <= 100000 and
            len(rows) == upstream['summary_rows'], 'Complete bounded summary cardinality required')
    columns = {field: [] for field in FIELDS}
    for position, row in enumerate(rows):
        require(None not in row and all(value is not None for value in row.values()), 'Ragged summary')
        require(row['test_id'] == request['test_id'] and row['row_id'] == 'field_' + str(position + 1) and
                bool(row['field']), 'Exact lexical field coordinates required')
        kind = row['value_kind']
        if kind in {'MISSING', 'NAN'}:
            require(row['value'] == 'NA', 'Missing state must remain explicit, not zero')
            value = None
        else:
            value = float(row['value'])
            require((kind == 'FINITE' and math.isfinite(value)) or
                    (kind == 'POS_INF' and value == math.inf) or
                    (kind == 'NEG_INF' and value == -math.inf), 'Numeric value/status mismatch')
        for field in FIELDS:
            columns[field].append(value if field == 'value' else row[field])
    columns['source_position'] = list(range(len(rows)))
    return columns


def technical_provenance(upstream):
    if technical_contract_version() == 1:
        return {}
    request = json.loads(upstream['request_json'], object_pairs_hook=unique_object)
    validate_technical_identity(request, upstream)
    return dict(schema_version=2, input_role=upstream['input_role'], scientific_qualification='NOT_GRANTED',
        upstream_state_sha256=upstream['output1_sha256'], G0_granted=False)


def write_products(inputs, outputs):
    require(os.environ.get('AUTONOMICS_INPUT_COUNT') == '2', 'Exactly two inputs required')
    require(inputs[0].stat().st_size <= 16 * 1024**2 and inputs[1].stat().st_size <= 2 * 1024**2,
            'Input byte budget exceeded')
    upstream = json.loads(inputs[1].read_text(), object_pairs_hook=unique_object)
    columns = parse_summary(inputs[0].read_bytes(), upstream)
    import pyarrow as arrow
    import pyarrow.parquet as parquet
    require(arrow.__version__ == '25.0.1', 'Pinned official PyArrow required')
    schema = arrow.schema([arrow.field(field, arrow.float64() if field == 'value' else arrow.string(),
        nullable=field == 'value') for field in FIELDS] + [arrow.field('source_position', arrow.uint32(), nullable=False)])
    table = arrow.Table.from_pydict(columns, schema=schema)
    parquet.write_table(table, outputs[0], compression='zstd')
    require(parquet.read_table(outputs[0]).equals(table, check_metadata=True), 'Full Parquet readback differs')
    provenance = technical_provenance(upstream)
    outputs[3].write_text(json.dumps({'schema': str(schema), 'rows': table.num_rows,
        'nullable_value': True, 'lexical_coordinates_preserved': True,
        'source_position_uint32': True, 'physical_output_order_not_assumed': True, **provenance}, indent=2) + '\n')
    audit = {'status': 'TECHNICAL_TYPED_VALUES_PASS_NOT_SCIENTIFIC', 'rows': table.num_rows,
        'input0_sha256': sha256(inputs[0]), 'input1_sha256': sha256(inputs[1]), 'output0_sha256': sha256(outputs[0]),
        'G0_granted': False, 'scientific_qualification_granted': False, 'resident_deployment_granted': False}
    if technical_contract_version() == 2:
        audit.update(provenance)
    return audit


def execute():
    outputs = [Path(os.environ['AUTONOMICS_OUTPUT' + str(index)]).absolute() for index in range(4)]
    require(len(set(outputs)) == 4 and len({path.name for path in outputs}) == 4 and
            len({path.parent.resolve() for path in outputs}) == 1, 'Distinct colocated output ports required')
    require(not any(path.exists() or path.is_symlink() for path in outputs), 'Refusing existing or linked output')
    inputs = [Path(os.environ['AUTONOMICS_INPUT' + str(index)]).resolve(strict=True) for index in range(2)]
    require(not set(path.resolve() for path in outputs).intersection(inputs), 'Input/output alias forbidden')
    created = []
    completed = False
    with tempfile.TemporaryDirectory(prefix='.survey-typed-owned-', dir=outputs[0].parent) as directory:
        private = [Path(directory) / path.name for path in outputs]
        try:
            try:
                audit = write_products(inputs, private)
                private[2].write_text('PASS explicit official Arrow types and readback; not scientific approval\n')
                status = 0
            except Exception as error:
                audit = {'status': 'BLOCKED', 'error': str(error), 'G0_granted': False,
                    'scientific_qualification_granted': False, 'resident_deployment_granted': False}
                private[2].write_text('BLOCKED ' + str(error) + '\n')
                status = 2
            private[1].write_text(json.dumps(audit, indent=2, allow_nan=False) + '\n')
            for position in (range(4) if status == 0 else (1, 2)):
                source_identity = private[position].stat()
                os.link(private[position], outputs[position], follow_symlinks=False)
                created.append((outputs[position], source_identity.st_dev, source_identity.st_ino))
            completed = True
            return status
        finally:
            if not completed:
                for filename, device, inode in reversed(created):
                    try:
                        current = filename.lstat()
                        if (current.st_dev, current.st_ino) == (device, inode):
                            filename.unlink()
                    except FileNotFoundError:
                        pass


def main():
    try:
        return execute()
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
