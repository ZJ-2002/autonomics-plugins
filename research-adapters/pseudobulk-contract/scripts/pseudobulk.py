#!/usr/bin/env python3
"""Exact disk-backed count aggregation with frozen biological-unit declarations.

No normalization, differential test, annotation inference, sample selection,
family freeze, G0 grant or assertion of biological independence.
"""
import argparse
import base64
import csv
import ctypes
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import tempfile
from contextlib import contextmanager

SAMPLE_COLUMNS = ('resource_id original_cohort_id donor_id sample_id library_id pool_id pool_members '
                  'independent_unit_id pair_id species tissue anatomic_site cell_type group timepoint '
                  'cachexia_definition cachexia_status bone_metastasis_status lesion_type treatment sex age '
                  'batch source_metadata_file source_metadata_sha256 include reason').split()
CELL_COLUMNS = ('matrix_column_id resource_id sample_id library_id cell_id cell_type '
                'observation_id include reason').split()
INPUTS = ['matrix', 'features', 'barcodes', 'sample_map', 'cell_map', 'metadata_pack']
MAX_COUNT = 2**53 - 1  # Exact integer interchange with R's double-backed matrices.


def require(ok, message):
    if not ok: raise ValueError(message)


def protocol_version(record):
    require(isinstance(record, dict) and type(record.get('protocol_version')) is str and
            record['protocol_version'] in {'4.2.1', '4.3.2'},
            'explicit supported core B protocol version required')
    return record['protocol_version']


def same_protocol(*records):
    require(bool(records), 'protocol-bearing records required')
    versions = [protocol_version(record) for record in records]
    require(len(set(versions)) == 1, 'core B protocol versions differ across producer lineage')
    return versions[0]


def strict_json(raw):
    def pairs(rows):
        out = {}
        for k,v in rows:
            require(k not in out, 'duplicate JSON identity'); out[k]=v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def identity(raw): return {'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)}


def sha_file(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def regular(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and not any(a.is_symlink() for a in p.parents),
            'regular non-symlink input required')
    return p


def bounded(path, maximum=64*1024**2):
    p=regular(path)
    with p.open('rb') as f:raw=f.read(maximum+1)
    require(len(raw)<=maximum,'metadata input exceeds bounded reader'); return raw


@contextmanager
def consumed_text(path, expected_sha256):
    """Hash the bytes actually parsed, including BOM and original newlines."""
    digest=hashlib.sha256()
    class Lines:
        def __iter__(self):return self
        def __next__(self):
            raw=source.readline(65537)
            if not raw:raise StopIteration
            require(len(raw)<=65536,'metadata row exceeds bounded reader')
            digest.update(raw)
            if source.tell()==len(raw):raw=raw.removeprefix(b'\xef\xbb\xbf')
            return raw.decode('utf-8')
    with Path(path).open('rb') as source:
        yield Lines()
        require(digest.hexdigest()==expected_sha256,'consumed metadata bytes differ from frozen identity')


def tsv(raw, columns):
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), delimiter='\t')
    require(reader.fieldnames==columns, 'exact declared TSV columns required')
    rows=list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows), 'malformed TSV row')
    return rows


def label(value):
    require(isinstance(value,str) and value.strip()==value and value and len(value)<=256
            and not any(c in value for c in '\t\n\r\x00') and value not in {'UNKNOWN','PENDING','NA'},
            'explicit bounded identity required')
    return value


def decision(row):
    require(row['include'] in {'YES','NO'}, 'explicit inclusion decision required')
    if row['include']=='NO':require(row['reason'].strip(), 'exclusion reason required')
    return row['include']=='YES'


def metadata_pack(raw):
    pack=strict_json(raw)
    require(isinstance(pack,dict) and set(pack)=={'schema_version','artifacts'} and type(pack['schema_version']) is int and pack['schema_version']==1,
            'exact metadata byte pack required')
    require(isinstance(pack['artifacts'],list) and pack['artifacts'], 'metadata byte evidence missing')
    out={}
    for ref in pack['artifacts']:
        require(isinstance(ref,dict) and set(ref)=={'name','sha256','bytes','base64'}, 'metadata artifact identity malformed')
        name=label(ref['name']);require(name not in out,'duplicate metadata name')
        require(type(ref['bytes']) is int and ref['bytes']>=0, 'metadata byte size invalid')
        require(isinstance(ref['base64'],str),'metadata base64 must be text')
        data=base64.b64decode(ref['base64'],validate=True)
        require(identity(data)=={k:ref[k] for k in ['sha256','bytes']}, 'metadata evidence bytes differ')
        out[name]=ref
    return out


def validate_units(samples_raw, metadata_raw, policy):
    """Validate declarations and keep unresolved pools explicitly non-inferential.

    Consistency with source bytes does not establish biological truth or G0.
    Observation IDs are explicit; repeated libraries/timepoints do not create
    new biological units. No condition is inferred from gene expression.
    """
    require(isinstance(policy,dict) and set(policy)=={'unit_definitions','observations'}, 'exact unit/observation policy required')
    definitions=policy['unit_definitions']; observations=policy['observations']
    require(isinstance(definitions,dict) and definitions and isinstance(observations,dict) and observations,
            'explicit biological units and observations required')
    sample_rows=tsv(samples_raw,SAMPLE_COLUMNS); require(sample_rows,'complete sample map required')
    pack=metadata_pack(metadata_raw); occupied={}; resolved={}
    for uid,unit in definitions.items():
        label(uid)
        require(isinstance(unit,dict) and set(unit)=={'kind','original_cohort_id','species','member_ids'}, 'unit definition fields differ')
        for field in ['original_cohort_id','species']:label(unit[field])
        require(isinstance(unit['kind'],str) and unit['kind'] in {'DONOR','ANIMAL','POOL'},'unknown biological unit kind')
        members=unit['member_ids']
        if members is None:
            require(unit['kind']=='POOL','only unresolved pools can lack member identities')
            resolved[uid]=False;continue
        require(isinstance(members,list) and members, 'explicit biological members required')
        for member in members:label(member)
        require(len(set(members))==len(members),'explicit unique biological members required')
        require(len(members)>=2 if unit['kind']=='POOL' else len(members)==1, 'unit membership cardinality differs')
        if unit['kind']=='DONOR':require(unit['species']=='Homo sapiens','human donor species differs')
        if unit['kind']=='ANIMAL':require(unit['species']!='Homo sapiens','animal unit is human')
        for member in members:
            key=(unit['original_cohort_id'], member)
            require(key not in occupied,'underlying biological member occurs in multiple independent units')
            occupied[key]=uid
        resolved[uid]=True
    indexed={}; selected=set(); used_units=set()
    for row in sample_rows:
        key=tuple(label(row[k]) for k in ['resource_id','sample_id','library_id'])
        require(key not in indexed,'duplicate sample/library identity'); indexed[key]=row
        include=decision(row); uid=label(row['independent_unit_id']);used_units.add(uid)
        require(uid in definitions,'unregistered biological unit'); unit=definitions[uid]
        require(row['original_cohort_id']==unit['original_cohort_id'] and row['species']==unit['species'],
                'unit cohort/species differs')
        if unit['kind']=='POOL':
            label(row['pool_id']);require(not row['donor_id'],'pool cannot be relabeled as a single donor')
            actual=None if row['pool_members']=='' else strict_json(row['pool_members'])
            require(actual==unit['member_ids'],'pool member declaration differs')
        else:
            require(row['donor_id']==unit['member_ids'][0] and not row['pool_id'] and not row['pool_members'],
                    'individual/pool identity differs')
        name=label(row['source_metadata_file'])
        require(name in pack and row['source_metadata_sha256']==pack[name]['sha256'], 'sample source metadata identity differs')
        if include:selected.add(key)
    require(used_units==set(definitions),'unit definitions differ from complete sample map')
    owners={}; obs_meta={}
    for oid,obs in observations.items():
        label(oid)
        require(isinstance(obs,dict) and set(obs)=={'unit_id','sample_keys','cell_types'}, 'observation fields differ')
        label(obs['unit_id'])
        require(obs['unit_id'] in definitions and isinstance(obs['sample_keys'],list) and obs['sample_keys'],
                'observation biological unit/sample set missing')
        types=obs['cell_types'];require(isinstance(types,list) and types,'complete cell type universe required')
        for cell_type in types:label(cell_type)
        require(len(set(types))==len(types),'complete unique cell type universe required')
        attributes=[]
        for rawkey in obs['sample_keys']:
            require(isinstance(rawkey,list) and len(rawkey)==3,'sample key must be resource/sample/library')
            for v in rawkey:label(v)
            key=tuple(rawkey); require(key in selected and key not in owners,'observation sample missing or counted twice')
            owners[key]=oid;row=indexed[key]
            require(row['independent_unit_id']==obs['unit_id'],'observation unit differs from sample')
            attributes.append(tuple(label(row[k]) for k in ['original_cohort_id','species','tissue','anatomic_site','group','timepoint']))
        require(len(set(attributes))==1,'different groups/timepoints/tissues/cohorts cannot be pooled into one observation')
        obs_meta[oid]={'unit_id':obs['unit_id'],'resolved_member_identity':resolved[obs['unit_id']],
            **dict(zip(['original_cohort_id','species','tissue','anatomic_site','group','timepoint'],attributes[0])),
            'sample_keys':obs['sample_keys'],'cell_types':types,
            'batches':sorted({indexed[tuple(k)]['batch'] for k in obs['sample_keys']})}
    require(set(owners)==selected,'complete frozen inclusion/observation flow required')
    return {'samples':indexed,'sample_rows':sample_rows,'sample_observations':owners,
            'observations':obs_meta,'unit_definitions':definitions,
            'biological_independence_verified':False,'scientific_G0_granted':False}


def validate_config(config):
    require(isinstance(config,dict) and set(config)=={'schema_version','protocol_version','status','operation','input_scale','input_sha256',
                        'unit_policy','feature_type','software_lock','limits'},'exact aggregation configuration required')
    require(type(config['schema_version']) is int and config['schema_version']==1 and protocol_version(config) in {'4.2.1','4.3.2'} and config['status']=='FROZEN'
            and config['operation']=='BIOLOGICAL_UNIT_CELLTYPE_RAW_COUNT_SUM'
            and config['input_scale']=='RAW_UNNORMALIZED_COUNTS' and config['feature_type']=='Gene Expression',
            'explicit raw-count aggregation recipe required')
    require(isinstance(config['input_sha256'],dict) and set(config['input_sha256'])==set(INPUTS) and all(isinstance(d,str) and re.fullmatch('[0-9a-f]{64}',d)
            for d in config['input_sha256'].values()),'all consumed input hashes required')
    require(config['software_lock']=={'python':platform.python_version(),'sqlite':sqlite3.sqlite_version},'software lock differs')
    limits=config['limits']
    require(isinstance(limits,dict) and set(limits)=={'sqlite_cache_kib','max_database_bytes'} and type(limits['sqlite_cache_kib']) is int
            and 1024<=limits['sqlite_cache_kib']<=65536 and type(limits['max_database_bytes']) is int
            and limits['max_database_bytes']>0,'bounded cache and explicit scratch budget required')


def integer(token):
    try: value=Decimal(token)
    except InvalidOperation:raise ValueError('malformed raw count')
    require(value.is_finite() and value>=0 and value==value.to_integral_value() and value<=MAX_COUNT,
            'raw counts must be exact nonnegative integers in interchange range')
    return int(value)


def atomic_publish(stage, output):
    require(not os.path.lexists(output),'output directory already exists')
    for p in stage.iterdir():
        with p.open('rb') as f:os.fsync(f.fileno())
    fd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.renameat2(-100,os.fsencode(stage),-100,os.fsencode(output),1)!=0:
        raise OSError(ctypes.get_errno(),'no-clobber complete publication failed')
    fd=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def aggregate(config_path, inputs, output):
    config_raw=bounded(config_path); config=strict_json(config_raw);validate_config(config)
    require(set(inputs)==set(INPUTS),'all aggregation inputs required')
    inputs={k:regular(p) for k,p in inputs.items()}
    output=Path(output).absolute();require(not os.path.lexists(output),'output directory already exists')
    require(not any(p.is_symlink() for p in output.parents),'symlink output ancestor')
    output.parent.mkdir(parents=True,exist_ok=True)
    hashes={k:sha_file(p) for k,p in inputs.items()}
    require(hashes==config['input_sha256'],'frozen input identity differs')
    metadata={k:bounded(inputs[k]) for k in ['sample_map','metadata_pack','features']}
    require(all(identity(raw)['sha256']==hashes[k] for k,raw in metadata.items()),'consumed metadata bytes differ from frozen identity')
    units=validate_units(metadata['sample_map'],metadata['metadata_pack'],config['unit_policy'])
    feature_raw=metadata['features']; features=[];seen=set()
    for line in feature_raw.decode('utf-8-sig').splitlines():
        cols=line.split('\t');require(len(cols)==3,'feature file must have ID/name/type columns')
        gid=label(cols[0]);require(gid not in seen,'duplicate raw feature identity');seen.add(gid)
        features.append(cols)
    require(features,'raw feature universe missing')
    retained={}
    for i,feature in enumerate(features,1):
        if feature[2]==config['feature_type']:retained[i]=len(retained)+1
    require(retained,'RNA feature universe empty')
    columns=[(oid,t) for oid,obs in sorted(units['observations'].items()) for t in sorted(obs['cell_types'])]
    column_index={key:i+1 for i,key in enumerate(columns)}
    with tempfile.TemporaryDirectory(prefix='.pseudobulk-scratch-',dir=output.parent) as scratch:
        scratch=Path(scratch);stage=scratch/'publish';stage.mkdir()
        db=sqlite3.connect(scratch/'scratch.db')
        try:
            db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA cache_size=-'+str(config['limits']['sqlite_cache_kib']))
            pages=config['limits']['max_database_bytes']//db.execute('PRAGMA page_size').fetchone()[0]
            require(pages>=1,'scratch database budget too small')
            db.execute('PRAGMA max_page_count='+str(pages))
            db.execute("PRAGMA temp_store_directory='"+str(scratch).replace("'","''")+"'")
            db.execute('CREATE TABLE barcodes (idx INTEGER PRIMARY KEY, label TEXT UNIQUE NOT NULL)')
            db.execute('CREATE TABLE cells (label TEXT PRIMARY KEY, cell_id TEXT UNIQUE NOT NULL, output_column INTEGER, inclusion TEXT NOT NULL, reason TEXT NOT NULL)')
            db.execute('CREATE TABLE seen (gene INTEGER, cell INTEGER, PRIMARY KEY(gene,cell)) WITHOUT ROWID')
            db.execute(f'CREATE TABLE sums (gene INTEGER, col INTEGER, value INTEGER CHECK(typeof(value)=\'integer\' AND value<={MAX_COUNT}), PRIMARY KEY(gene,col)) WITHOUT ROWID')
            db.execute('CREATE INDEX sum_order ON sums(col,gene)')
            barcode_count=0
            with consumed_text(inputs['barcodes'],hashes['barcodes']) as f:
                for barcode_count,line in enumerate(f,1):
                    barcode=label(line.rstrip('\r\n'));db.execute('INSERT INTO barcodes VALUES (?,?)',(barcode_count,barcode))
            require(barcode_count>0,'matrix columns missing')
            with consumed_text(inputs['cell_map'],hashes['cell_map']) as f:
                reader=csv.DictReader(f,delimiter='\t');require(reader.fieldnames==CELL_COLUMNS,'exact cell map columns required')
                for row in reader:
                    require(None not in row and all(v is not None for v in row.values()),'malformed cell map row')
                    mid=label(row['matrix_column_id']);cid=label(row['cell_id']);ct=label(row['cell_type'])
                    require(db.execute('SELECT 1 FROM barcodes WHERE label=?',(mid,)).fetchone(),'unknown matrix cell identity')
                    key=tuple(row[k] for k in ['resource_id','sample_id','library_id']);require(key in units['samples'],'cell sample mapping missing')
                    include=decision(row);expected_oid=units['sample_observations'].get(key)
                    if expected_oid is None:
                        require(not include and not row['observation_id'],'excluded sample cell cannot enter an observation')
                        col=None
                    else:
                        require(row['observation_id']==expected_oid,'cell observation differs from frozen sample')
                        require((expected_oid,ct) in column_index or not include,'included cell type outside frozen universe')
                        col=column_index[(expected_oid,ct)] if include else None
                    db.execute('INSERT INTO cells VALUES (?,?,?,?,?)',(mid,cid,col,row['include'],row['reason']))
            require(db.execute('SELECT COUNT(*) FROM cells').fetchone()[0]==barcode_count,'complete matrix-to-cell map required')
            db.execute('CREATE TABLE mapping AS SELECT b.idx,c.output_column FROM barcodes b JOIN cells c ON c.label=b.label')
            db.execute('CREATE UNIQUE INDEX map_idx ON mapping(idx)');db.commit()
            def budget():
                size=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
                require(size<=config['limits']['max_database_bytes'],'scratch database budget exceeded')
            budget(); count=0;raw_sum=0;retained_sum=0;streamhash=hashlib.sha256()
            with inputs['matrix'].open('rb') as f:
                header=f.readline(4097);require(len(header)<=4096,'matrix header exceeds bound');streamhash.update(header)
                require(header.decode('ascii').strip() in {'%%MatrixMarket matrix coordinate integer general','%%MatrixMarket matrix coordinate real general'},'raw general coordinate MatrixMarket required')
                def lines():
                    while True:
                        raw=f.readline(4097)
                        if not raw:break
                        streamhash.update(raw);require(len(raw)<=4096,'matrix line exceeds bound')
                        line=raw.decode('ascii').strip()
                        if line and not line.startswith('%'):yield line
                records=lines()
                shape=next(records,'').split();require(len(shape)==3 and all(re.fullmatch('[0-9]+',v) for v in shape),'matrix dimensions invalid')
                ng,nc,nnz=map(int,shape);require(ng==len(features) and nc==barcode_count,'feature/cell matrix dimensions differ')
                for line in records:
                    fields=line.split();require(len(fields)==3 and all(re.fullmatch('[0-9]+',v) for v in fields[:2]),'matrix coordinate invalid')
                    i,j=map(int,fields[:2]);value=integer(fields[2]);require(1<=i<=ng and 1<=j<=nc,'matrix coordinate outside dimensions')
                    db.execute('INSERT INTO seen VALUES (?,?)',(i,j));count+=1;raw_sum+=value
                    require(count<=nnz,'extra matrix coordinates beyond declared count')
                    col=db.execute('SELECT output_column FROM mapping WHERE idx=?',(j,)).fetchone()[0]
                    if i in retained and col is not None and value:
                        db.execute('INSERT INTO sums VALUES (?,?,?) ON CONFLICT(gene,col) DO UPDATE SET value=value+excluded.value',(retained[i],col,value));retained_sum+=value
                    if count%10000==0:db.commit();budget()
                require(count==nnz,'matrix declared coordinate count differs')
            require(streamhash.hexdigest()==hashes['matrix'],'consumed matrix bytes differ from frozen identity')
            db.commit();budget()
            nnz_out=db.execute('SELECT COUNT(*) FROM sums').fetchone()[0]
            with (stage/'counts.mtx').open('x') as f:
                f.write(f'%%MatrixMarket matrix coordinate integer general\n% exact biological-unit observation/cell-type raw-count sum\n{len(retained)} {len(columns)} {nnz_out}\n')
                for i,j,v in db.execute('SELECT gene,col,value FROM sums ORDER BY col,gene'):f.write(f'{i} {j} {v}\n')
            with (stage/'features.tsv').open('x',newline='') as f:
                writer=csv.writer(f,delimiter='\t',lineterminator='\n');writer.writerows(features[i-1] for i in retained)
            with (stage/'feature-qc.tsv').open('x',newline='') as f:
                writer=csv.writer(f,delimiter='\t',lineterminator='\n');writer.writerow(['original_row','feature_id','type','included','reason'])
                for i,feature in enumerate(features,1):writer.writerow([i,feature[0],feature[2],'YES' if i in retained else 'NO','' if i in retained else 'FROZEN_NON_RNA_FEATURE_TYPE'])
            with (stage/'columns.tsv').open('x',newline='') as f:
                writer=csv.writer(f,delimiter='\t',lineterminator='\n')
                writer.writerow(['column','observation_id','independent_unit_id','group','timepoint','cell_type','n_cells','count_state','unit_identity_scope','member_identity_resolved','biological_independence_verified'])
                for i,(oid,ct) in enumerate(columns,1):
                    obs=units['observations'][oid];n=db.execute('SELECT COUNT(*) FROM cells WHERE output_column=?',(i,)).fetchone()[0]
                    writer.writerow([i,oid,obs['unit_id'],obs['group'],obs['timepoint'],ct,n,
                        'COUNTS_AVAILABLE' if n else 'ZERO_CELLS_NOT_INFERENTIAL',
                        'DECLARED_MEMBERS_NOT_SCIENTIFICALLY_VERIFIED' if obs['resolved_member_identity'] else 'UNRESOLVED_POOL_DESCRIPTIVE_ONLY',
                        str(obs['resolved_member_identity']).upper(),'FALSE'])
            with (stage/'cell-qc.tsv').open('x',newline='') as f:
                writer=csv.writer(f,delimiter='\t',lineterminator='\n');writer.writerow(['matrix_column','matrix_column_id','cell_id','output_column','included','reason'])
                writer.writerows(db.execute('SELECT b.idx,b.label,c.cell_id,c.output_column,c.inclusion,c.reason FROM barcodes b JOIN cells c ON c.label=b.label ORDER BY b.idx'))
            require({k:sha_file(p) for k,p in inputs.items()}==hashes and sha_file(config_path)==identity(config_raw)['sha256'],'input changed during aggregation')
            strata={}
            fields=['original_cohort_id','species','tissue','anatomic_site','group','timepoint']
            for obs in units['observations'].values():
                for ct in obs['cell_types']:
                    key=tuple(obs[k] for k in fields)+(ct,)
                    strata.setdefault(key,set()).add(obs['unit_id'])
            audit={'scope':'EXACT_COUNT_AGGREGATION_NOT_DIFFERENTIAL_INFERENCE_OR_G0','config':identity(config_raw),
                   'input_sha256':hashes,'software_lock':config['software_lock'],'frozen_recipe':config,
                   'raw_dimensions':[ng,nc,nnz],'output_dimensions':[len(retained),len(columns),nnz_out],
                   'all_input_count_sum':str(raw_sum),'retained_count_sum':str(retained_sum),
                   'observations':units['observations'],'unit_definitions':units['unit_definitions'],
                   'declared_unit_strata':[{**dict(zip(fields+['cell_type'],key)),
                     'unit_ids':sorted(ids),'declared_units':len(ids),
                     'resolved_declared_units':sum(units['unit_definitions'][u]['member_ids'] is not None for u in ids)}
                     for key,ids in sorted(strata.items())],
                   'biological_independence_verified':False,'scientific_G0_granted':False,
                   'inference_executed':False,'family_frozen':False,
                   'output_identity':{p.name:{'sha256':sha_file(p),'bytes':p.stat().st_size} for p in stage.iterdir()}}
            (stage/'audit.json').write_bytes(canonical(audit))
            atomic_publish(stage,output)
            return audit
        finally:db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True,type=Path)
    for name in INPUTS:parser.add_argument('--'+name.replace('_','-'),dest=name,required=True,type=Path)
    parser.add_argument('--output-directory',type=Path,required=True);args=parser.parse_args()
    try:
        result=aggregate(args.config,{k:getattr(args,k) for k in INPUTS},args.output_directory)
        print(json.dumps({'scope':result['scope'],'output_dimensions':result['output_dimensions'],'scientific_G0_granted':False}))
    except (ValueError,OSError,sqlite3.Error,UnicodeError,csv.Error) as e:
        print('BLOCKED: '+str(e),file=__import__('sys').stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
