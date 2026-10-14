"""Compile source-bound variant metadata. No execution, fitting or approval API.

The trusted core must recompute this binding from admitted bytes and retain its
normal method/source/StudyContract gates. A matching image version or candidate
binding never supplies the missing qualification. No legacy-node aliasing.
"""
import csv
import io
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'research-adapters/b-bulk-normalized-contract'

def require(ok, message):
    if not ok: raise ValueError('normalized full-B binding: ' + message)

def identity(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

def strict(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 4 * 1024**2, 'bounded actual metadata bytes required')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def keys(value, wanted, label):
    require(isinstance(value, dict) and set(value) == set(wanted), label + ' exact fields required')

def compile_unsigned_binding(request_raw, template_raw, genes_raw, assay_raw):
    """Select a software candidate for one complete source-bound contrast.

    Deliberately cannot set execution_ready or method_acceptance_verified true.
    Host-side source and signed method verification remain required afterwards.
    """
    contract_raw = (DIRECTORY / 'runtime-contract.json').read_bytes()
    contract = strict(contract_raw)
    manifest_raw = (DIRECTORY / 'manifest.toml').read_bytes()
    require(identity(manifest_raw) == contract['manifest_identity'], 'manifest source changed')
    for name, record in contract['files'].items():
        require(identity((DIRECTORY / name).read_bytes()) == {k: record[k] for k in ['sha256', 'bytes']}, 'wrapper/component source changed')
    request, template, assay = map(strict, [request_raw, template_raw, assay_raw])
    keys(request, ['schema_version','protocol_version','resource_id','source_resource_id','accession','contrast_id','expression_scale','method',
        'condition_mapping','endpoint_column','software_lock','design','method_parameters','limits','result_exposure'], 'frozen source request')
    keys(template, ['schema_version','protocol_version','status','method','expression_scale','contrast_id','design','software_lock',
        'method_parameters','input_sha256','source_archive_sha256','resource_id','limits'], 'frozen method template')
    keys(assay, ['schema_version','scope','assay_type','normalization','request_identity','feature_registry_identity','gene_registry_identity',
        'source_metadata_identity','contrast_id','resource_id','accession'], 'source-assay declaration')
    require(type(request['schema_version']) is int and request['schema_version'] == 1 and type(template['schema_version']) is int and template['schema_version'] == 1,
            'integer schema1 required')
    require(request['protocol_version'] == template['protocol_version'] == '4.3.2' and template['status'] == 'FROZEN', 'explicit matching frozen v4.3.2 required')
    require(request['method'] == template['method'] == contract['method'] and request['expression_scale'] == template['expression_scale'] == contract['expression_scale'],
            'counts/TPM/voom/DESeq2 and alternate methods refused')
    require(request['software_lock'] == template['software_lock'] == contract['software_lock'], 'declared package version differs from exact software contract')
    for key in ['contrast_id','resource_id','design','method_parameters','limits']:
        require(request[key] == template[key], 'request/template mismatch: ' + key)
    require(template['method_parameters']['trend'] is True and template['method_parameters']['robust'] is True, 'fixed trend/robust required')
    require(template['source_archive_sha256'] == contract['source_design_sha256'], 'exact full v4.3.2 design source required')
    keys(template['input_sha256'], ['expression','genes','samples','decisions'], 'actual input hash slots')
    require(all(v is None or (isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v)) for v in template['input_sha256'].values()), 'invalid actual binding hash slot')
    require(type(assay['schema_version']) is int and assay['schema_version'] == 1 and assay['scope'] == 'EXPLICIT_FROZEN_SOURCE_ASSAY_DECLARATION_NOT_QUALIFICATION', 'assay declaration scope differs')
    require(assay['assay_type'] == contract['source_assay_type'] and assay['normalization'] == 'SOURCE_RMA_LOG2_NOT_RENORMALIZED', 'explicit normalized microarray source required')
    require(assay['request_identity'] == identity(request_raw) and assay['gene_registry_identity'] == identity(genes_raw), 'request/gene byte identity differs')
    for name in ['feature_registry_identity', 'source_metadata_identity']:
        keys(assay[name], ['sha256','bytes'], name)
        require(type(assay[name]['bytes']) is int and assay[name]['bytes'] > 0 and re.fullmatch('[0-9a-f]{64}',assay[name]['sha256'] or '') is not None, 'exact source identity required')
    for name in ['contrast_id','resource_id','accession']:
        require(assay[name] == request[name], 'source assay linkage differs: ' + name)
    # Authenticate the complete identity universe; never parse/select gene effects.
    require(isinstance(genes_raw,bytes) and 0 < len(genes_raw) <= 64*1024**2, 'bounded complete gene registry bytes required')
    table = csv.DictReader(io.StringIO(genes_raw.decode('utf-8')), delimiter='\t')
    require(table.fieldnames == ['matrix_row','gene_id','analysis_id','family_id','contrast_id','estimand_id'], 'exact full gene identity schema required')
    genes = list(table)
    require(genes and all(None not in row and all(isinstance(v,str) and v and not any(c in v for c in '\t\r\n') for v in row.values()) for row in genes), 'complete nonempty gene identities required')
    require([row['matrix_row'] for row in genes] == [str(i+1) for i in range(len(genes))] and len({row['gene_id'] for row in genes}) == len(genes) and len({row['analysis_id'] for row in genes}) == len(genes), 'original gene order or unique identity differs')
    require(all(row['family_id'] == 'B_TRANSCRIPTOME' and row['contrast_id'] == request['contrast_id'] and row['estimand_id'] == 'E_B_DIS' for row in genes), 'gene universe family/contrast/estimand differs')
    return {'schema_version':1, 'scope':'UNSIGNED_SOURCE_BOUND_FULL_B_NORMALIZED_VARIANT', 'variant_id':contract['variant_id'],
        'runtime_contract':identity(contract_raw), 'manifest':identity(manifest_raw), 'binding_compiler_source':identity(Path(__file__).read_bytes()), 'method_sources':contract['files'],
        'image_reference':contract['image_reference'], 'interpreter':contract['interpreter'], 'software_lock':contract['software_lock'],
        'design_kind':contract['design_kind'], 'limma_kind':contract['limma_kind'], 'contrast_id':request['contrast_id'],
        'request':identity(request_raw), 'template':identity(template_raw), 'gene_registry':identity(genes_raw), 'gene_count':len(genes), 'source_assay':identity(assay_raw),
        'source_archive_sha256':template['source_archive_sha256'], 'method_acceptance_verified':False, 'source_qualified':False,
        'execution_ready':False, 'formal_authorized':False, 'scientific_authorization':False, 'G0':False,
        'missing_execution_contracts':['HOST_VERIFIED_SOURCE_ASSAY_AND_FULL_GENE_REGISTRY','EXACT_VARIANT_METHOD_ACCEPTANCE',
            'LOADED_WORKER_SOURCE_AND_BINARY_BINDING','RESOURCE_ADMISSION','EXISTING_SIGNED_STUDY_CONTRACT']}
