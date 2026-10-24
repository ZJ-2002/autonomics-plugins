import collections
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path


ARCHIVES = Path.home()/'.local/state/autonomics/validation-archives'
PROOFS = {
    'restoration':('45e8a832cb9947e0b93dea53525a5fba','4a8e2642bdd82145370a020fb721353b2c998e9fa2fe115039b813f0c8171bde','retained-canonical-bindings-restored'),
    'resident':('29ba9d6d3d02474dbfb41295e1f0085f','646362552859c9730c542f6eb290355283977d8f8654a47bafd54d96db20f39d','fixed120-resident-source-observation'),
    'typed_conversion':('c4b20c559df740d2b17ada0aab2a105b','fe08eaead439481a66423f502132e018816731ae103c8cbee18b212eea26d4f5','sensitivity-typed-public-image'),
    'typed_deployment':('91d335e63ef44ef9916f417d712c9bed','12a91898a9870f3d22f8bbf25cd4135ef13fbe9edcfdd5d16232afdc60440371','sensitivity-typed-public-image-deployment'),
    'carrier':('5d2f350634cc48308f1fab102e048b33','361fb35885afa48629f9a127ffd43e382d24618204d9696f2d4ecc7aa44a7736','a-carrier-concordance'),
    'gate':('5c99043cfe33491e9ac73bd59361aef3','e0ebfdb56ea1e92f504ba4d8dd337a1d997c8fdeeb451a5d3af4b6c4f9256d2d','published-test-gate-closure'),
    'convergence':('8c87eb3afad44c5d82e86ca603589b5b','09642d7c01e16b8f233be74f705433618a0c55e2724b28de2de1eec3b3646506','b-source-convergence'),
    'image_install':('8898b3a2755843748cb1ead29730f88b','5f9191ac57f789b450bee9b6f7ef0decfd8872dad9cbe730e360b15a243a7b07','two-public-image-reference-installation'),
    'msigdb':('e1d126aea279409ba5f80a41ccd68110','1b80bdf935c4ca8248f2fc383d79f79e5a57cd0a68420c8f7d0218c05e36c382','msigdb-node-network-candidate'),
    'opengwas':('620db72dbd244381b7df4b22b49806c0','190d348f3d362be6881542f59bf0c19640b2bac0e59e91a603724451bc745f9b','installed-ieugwasr-transport'),
}
SENSITIVITY = {'FUNC_evalue','FUNC_hypothesize.combine_pvalues'}
ASSEMBLY = {'FUNC_hypothesize.p_adjust','FUNC_hypothesize.boolean_test'}


def require(condition,message):
    if not condition:
        raise ValueError(message)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def encode(value):
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT'),'Managed reconciliation required')
    os.umask(0o077)
    evidence = {}

    def member(key,name='verification.json'):
        session,seal,directory = PROOFS[key]
        root = ARCHIVES/session
        receipt = json.loads((root/'SESSION.json').read_bytes())
        raw = (root/'artifacts/MANIFEST.json').read_bytes()
        require(receipt['state'] == 'CLEANED' and receipt['worker_exit_status'] == 0 and receipt['manifest_sha256'] == seal == sha(raw),'Successful immutable evidence required: '+key)
        manifest = json.loads(raw)
        relative = 'permanent/'+directory+'/'+name
        payload = (root/'artifacts'/relative).read_bytes()
        fact = manifest['files'][relative]
        require(fact['sha256'] == sha(payload) and fact['bytes'] == len(payload),'Evidence member differs: '+key)
        evidence[key+':'+name] = {'session':session,'seal':seal,'member':relative,'sha256':sha(payload)}
        return json.loads(payload)

    restoration = member('restoration')
    baseline = member('restoration','FIXED120_CANONICAL_BINDINGS_RESTORED.json')
    resident = member('resident')
    registry = member('resident','registry.json')
    conversion = member('typed_conversion')
    deployed = member('typed_deployment')
    carrier = member('carrier')
    gate = member('gate')
    convergence = member('convergence')
    installed = member('image_install')
    msigdb = member('msigdb')
    opengwas = member('opengwas')
    require(restoration['restored_binding_count'] == 17 and conversion['historical_cases'] == 101 and conversion['method_recomputations'] == 0,'Expected scoped proofs differ')
    require(deployed['resident_pid'] == resident['resident_pid'] and deployed['registered_addresses'] == resident['registered_addresses'] == 668,'Resident observations do not align')
    require(gate['new_required_count'] == 1220 and not gate['removed_ids'] and gate['new_unit_execution']['tests_run'] == 20,'Published gate closure differs')
    require(carrier['real_carriers_compared'] == 1 and carrier['real_result_rows'] == 3 and carrier['binary64_precision_claimed'] is False,'Carrier scope differs')
    addresses = {row['address'] for row in registry['nodes']}
    plugins = {row['name']:row for row in registry['plugins']}
    require(installed['installed_images'] == 2 and all(row['content_identity_equal'] is True for row in installed['images']),'Exact installed image identities differ')
    installed_references = {row['name']:row['installed_reference'] for row in installed['images']}
    require(set(installed_references) == {'sensitivity','permutation'},'Installed family set differs')
    require(deployed['image'] == conversion['image'] and plugins['cachexia-sensitivity-typed-values']['image'] == deployed['image']
            and plugins['cachexia-sensitivity-typed-values']['source']['rev'] == deployed['target_revision'],'Typed source/image deployment differs')
    typed_source = next(value for path,value in deployed['source_hashes'].items() if path.endswith('/scripts/typed_values.py'))
    require(typed_source['sha256'] == conversion['script_sha256'],'Typed converter source differs')
    require(msigdb['installed_source_identity_checked'] is True and len(msigdb['container_canaries']) == 1,'Installed MSigDB canary scope differs')
    canary = msigdb['container_canaries'][0]
    require(canary['method'] == 'HEAD' and canary['status'] == 200 and canary['response_body_bytes_read'] == 0 and canary['container_exit_code'] == 0,'MSigDB canary outcome differs')
    require(opengwas['private_metadata_calls'] == 1 and opengwas['readback']['passed'] is True and opengwas['readback']['full_RDS_read'] is True,'Official gwasinfo readback scope differs')
    observed_rows = {row['function_id']:row for row in resident['rows']}
    ids = [row['function_id'] for row in baseline['rows']]
    require(len(ids) == len(set(ids)) == 120,'Fixed universe differs')
    current = copy.deepcopy(baseline)
    changes = []
    for row in current['rows']:
        identifier = row['function_id']
        before = copy.deepcopy(row)
        effective = row['effective_software_addresses']
        present = [address for address in effective if address in addresses]
        missing = [address for address in effective if address not in addresses]
        require(effective,'Every slot requires an explicit retained selection or binding')
        observed = []
        for address in present:
            if address.startswith('core/'):
                kind = 'CORE_REGISTERED_ADDRESS_AND_PINNED_BINARY_NOT_NEW_METHOD_EXECUTION'
            else:
                name = address.split('/',1)[0]
                require(name in resident['families'],'Missing family source observation: '+address)
                kind = 'CONFIG_DISK_GIT_REGISTRY_CHAIN' if resident['families'][name]['pinned_git_blobs_verified'] else 'LOCAL_PATH_CONFIG_DISK_REGISTRY_NOT_GIT_VERIFIED'
            observed.append({'address':address,'scope':kind})
        row['historical_unresolved_before_postdeployment_merge'] = list(row['unresolved'])
        resolved = []
        if not missing:
            marker = 'FRESH_SELECTED_RESIDENT_IDENTITY_NOT_REOBSERVED'
            if marker in row['unresolved']:
                row['unresolved'].remove(marker)
                resolved.append({'gap':marker,'evidence_key':'resident:verification.json','scope':'METADATA_AND_IMPLEMENTATION_IDENTITY_OBSERVED_NOT_NEW_EXECUTION'})
        row['current_deployment_observation'] = {'evidence_key':'resident:verification.json','resident_pid_at_observation':resident['resident_pid'],
            'registered_effective_addresses':present,'missing_effective_addresses':missing,'observations':observed,
            'date_bound_observation_not_future_liveness':True,'gateway_submitted_execution_claimed':False}
        updates = []
        if identifier in SENSITIVITY or identifier == 'FUNC_permutation_test':
            family = 'cachexia-sensitivity' if identifier in SENSITIVITY else 'cachexia-permutation'
            image_name = 'sensitivity' if identifier in SENSITIVITY else 'permutation'
            require(plugins[family]['registered'] and plugins[family]['error'] is None and plugins[family]['image'] == installed_references[image_name],'Exact installed public family differs')
            for marker in ('FULL_LAYER_PULL_PENDING','EXACT_DIGEST_PRODUCTION_INSTALL_AND_LOADING_PENDING'):
                if marker in row['unresolved']:
                    row['unresolved'].remove(marker)
                    resolved.append({'gap':marker,'evidence_keys':['image_install:verification.json','resident:verification.json'],'scope':'EXACT_IMAGE_CACHE_AND_SELECTED_RESIDENT_SOURCE_CHAIN_ONLY'})
            updates.append({'kind':'PUBLIC_COMPUTATION_IMAGE_TRANSPORT_LINKED','family':family,'image':plugins[family]['image'],'new_method_execution':False})
        if identifier in SENSITIVITY:
            updates.append({'kind':'TYPED_COMPANION_PORTABILITY_AND_RESIDENT_SOURCE_LINKED','evidence_keys':['typed_conversion:verification.json','typed_deployment:verification.json'],'historical_outputs_converted':101,'new_statistical_fits':0,'whole_image_equivalence_claimed':False})
        if identifier in ASSEMBLY:
            updates.append({'kind':'ONE_SEEN_CARRIER_RDS_TSV_SERIALIZATION_CONCORDANCE','evidence_key':'carrier:verification.json','carriers':1,'rows':3,'binary64_or_intake_integration_claimed':False,'finite_primary_authority_granted':False})
        if identifier == 'FUNC_msigdb_gmt':
            marker = 'INSTALLED_SOURCE_CANARY_AND_RESIDENT_CONTAINER_TRANSPORT_PENDING'
            if marker in row['unresolved']:
                row['unresolved'].remove(marker)
                row['unresolved'].append('RESIDENT_GATEWAY_SUBMITTED_MSIGDB_CONTAINER_EXECUTION_NOT_CLAIMED')
                resolved.append({'gap':marker,'evidence_key':'msigdb:verification.json','scope':'INSTALLED_SOURCE_HEAD_CANARY_ONLY_NOT_FULL_RESOURCE_OR_GATEWAY_DAG'})
            updates.append({'kind':'INSTALLED_SOURCE_NETWORK_CANARY','evidence_key':'msigdb:verification.json','scope':'ONE_HEAD_200_ZERO_BODY_BYTES_NO_NEW_GMT_DOWNLOAD'})
        if 'source_opengwas_' in identifier:
            updates.append({'kind':'SHARED_OFFICIAL_CONTAINER_TRANSPORT_SCOPE','evidence_key':'opengwas:verification.json','actual_live_operation':'gwasinfo',
                'native_core_readiness_or_other_live_operations_inferred':False,'official_scoped_alternative_does_not_silently_replace_native_factory':True})
        row['postdeployment_resolved_historical_gaps'] = resolved
        row['postdeployment_evidence_observations'] = updates
        if row != before:
            changes.append(identifier)
    require([row['function_id'] for row in current['rows']] == ids,'ID/order changed')
    for before,after in zip(baseline['rows'],current['rows'],strict=True):
        for field in ('selected_addresses','effective_software_addresses','method_layer','plan_qualification_layer','software_disposition_retained','review_state_retained'):
            require(before[field] == after[field],'Unreviewed layer changed: '+field)
        require(after['current_deployment_observation']['missing_effective_addresses'] == ([] if before['function_id'] != 'FUNC_spatial_nhood' else before['effective_software_addresses']),'Unexpected registered-route result')
    require(current['counts'] == baseline['counts'],'Historical approval counts changed')
    missing_functions = [row['function_id'] for row in current['rows'] if row['current_deployment_observation']['missing_effective_addresses']]
    summary = {'fixed_function_ids':120,'functions_with_all_effective_routes_observed':120-len(missing_functions),'functions_with_missing_effective_routes':missing_functions,
        'route_observation_is_not_software_or_scientific_PASS':True,'historical_software_dispositions':dict(collections.Counter(row['software_disposition_retained'] for row in current['rows'])),
        'new_software_admissions_issued':0,'new_node_repairs_claimed':0,'new_method_or_scientific_computations':0,
        'published_required_test_ids':1220,'whole_1220_suite_execution_claimed':False,'local_draft_merged_or_certified':False,
        'spatial_state':'CONDITIONAL_NOT_READY','GS01':'OPEN','scientific_release_granted':False,'g0_granted':False}
    current['postdeployment_reconciliation'] = {'schema':'FIXED120_POSTDEPLOYMENT_RECONCILIATION_V1','evidence':evidence,'summary':summary,
        'resolved_history_is_retained_per_row':True,'original_four_layers_not_recertified_by_metadata':True,
        'additional_reused_receipts_not_all_fields_promoted':[key for key in ('convergence','gate','carrier','msigdb','opengwas','image_install')]}
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'fixed120-postdeployment'
    output.mkdir(mode=0o700)
    (output/'merge.py').write_bytes(Path(__file__).read_bytes())
    (output/'FIXED120_POSTDEPLOYMENT.json').write_bytes(encode(current))
    buffer = io.StringIO()
    writer = csv.writer(buffer,delimiter='\t',lineterminator='\n')
    writer.writerow(['function_id','role','historical_software_disposition','method_classification','original_selected_addresses','effective_software_addresses','registered_addresses_observed','missing_addresses','remaining_gaps','new_evidence_observation_kinds','scientific_release_granted'])
    for row in current['rows']:
        observation = row['current_deployment_observation']
        writer.writerow([row['function_id'],row['role'],row['software_disposition_retained'],row['method_layer']['classification'],
            json.dumps(row['selected_addresses']),json.dumps(row['effective_software_addresses']),json.dumps(observation['registered_effective_addresses']),
            json.dumps(observation['missing_effective_addresses']),json.dumps(row['unresolved'],ensure_ascii=False),
            json.dumps([entry['kind'] for entry in row['postdeployment_evidence_observations']]),False])
    (output/'FIXED120_POSTDEPLOYMENT.tsv').write_text(buffer.getvalue())
    (output/'COUNTS.json').write_bytes(encode(summary))
    report = {'schema':'FIXED120_POSTDEPLOYMENT_PROJECTION_PROOF_V1','checks':{'fixed_IDs_order_and_denominator_preserved':True,'original_selection_method_and_scientific_layers_preserved':True,'all_evidence_members_bound_to_seals_and_successful_exits':True},
        'summary':summary,'evidence':evidence,'products':{name:{'sha256':sha((output/name).read_bytes()),'bytes':(output/name).stat().st_size} for name in ['FIXED120_POSTDEPLOYMENT.json','FIXED120_POSTDEPLOYMENT.tsv','COUNTS.json']},
        'new_method_API_DAG_test_or_deployment_executions':0,'scientific_release_granted':False,'g0_granted':False}
    (output/'verification.json').write_bytes(encode(report))
    print(json.dumps({'fixed_functions':120,'registered_route_observation_functions':summary['functions_with_all_effective_routes_observed'],'missing':missing_functions,'new_software_admissions':0}),flush=True)


if __name__ == '__main__':
    main()
