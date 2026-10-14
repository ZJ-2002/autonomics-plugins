import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import acquire_opentargets_direct_reference as proof


class DirectAcquisitionTests(unittest.TestCase):
    def record(self):
        return dict(url=proof.BASE+'target/part-00000.zstd.parquet', status=200, bytes=50,
                    etag='"fixed"', last_modified='Mon, 07 Sep 2026 15:56:27 GMT')

    def response(self, record):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *arguments): return False
        result=Response()
        result.status=200
        result.url=record['url']
        result.headers={'Content-Length':str(record['bytes']), 'ETag':record['etag'], 'Last-Modified':record['last_modified']}
        return result

    def test_full_toy_file_is_hashed_and_existing_destination_is_not_replaced(self):
        record=self.record();body=b'PAR1DATA'+b'PAR1';record['bytes']=len(body)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);destination=root/'result.parquet'
            for position in range(2):
                response=self.response(record);response.read=io.BytesIO(body).read
                with patch.object(proof,'urlopen',return_value=response) as request:
                    if position==0:
                        receipt=proof.acquire(record,root/'first.tmp',destination)
                        self.assertEqual(receipt['sha256'],hashlib.sha256(body).hexdigest())
                    else:
                        with self.assertRaises(FileExistsError):proof.acquire(record,root/'second.tmp',destination)
                    self.assertEqual(request.call_count,1)
                self.assertEqual(destination.read_bytes(),body)

    def test_truncated_overlong_and_nonparquet_bodies_never_publish(self):
        record=self.record();record['bytes']=12
        for body in [b'PAR1DATA',b'PAR1DATAEXTRA',b'NOPEdatANOPE']:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);response=self.response(record);response.read=io.BytesIO(body).read
                with patch.object(proof,'urlopen',return_value=response) as request:
                    with self.assertRaises(RuntimeError):proof.acquire(record,root/'partial',root/'result.parquet')
                    self.assertEqual(request.call_count,1)
                self.assertFalse((root/'result.parquet').exists())

    def test_exact_official_origin_and_metadata_scope_are_required(self):
        original=self.record()
        self.assertEqual(proof.validate_resource('target',original),'part-00000.zstd.parquet')
        for key,value in [('url','https://example.invalid/part.parquet'), ('url',original['url']+'?token=x'),
                          ('url',proof.BASE+'target/../part.parquet'), ('bytes',proof.FILE_LIMIT+1),
                          ('etag',None), ('last_modified',''), ('status',206)]:
            changed=copy.deepcopy(original);changed[key]=value
            with self.assertRaises(RuntimeError):proof.validate_resource('target',changed)

    def test_partial_compressed_redirect_and_changed_identity_responses_are_refused(self):
        record=self.record()
        proof.check_response(self.response(record),record)
        for key,value in [('Content-Length','49'),('ETag','"new"'),('Last-Modified','new'),
                          ('Content-Encoding','gzip'),('Content-Range','bytes 0-49/50')]:
            response=self.response(record);response.headers[key]=value
            with self.assertRaises(RuntimeError):proof.check_response(response,record)
        for key,value in [('status',206),('url','http://ftp.ebi.ac.uk/file')]:
            response=self.response(record);setattr(response,key,value)
            with self.assertRaises(RuntimeError):proof.check_response(response,record)

    def test_inventory_is_only_generic_direct_overall_and_annotation_reference(self):
        self.assertEqual(proof.SELECTED,{'association_overall_direct':14,'target':3,'disease':1})
        self.assertEqual(proof.TOTAL,867128423)
        self.assertNotIn('association_by_datasource_direct',proof.SELECTED)


if __name__=='__main__':unittest.main()
