use std::sync::Arc;

use bib_types::evidence::{EvidenceRecord, EvidenceSet, FORMAT};
use bib_types::{Article, FileFormat, FullText, FullTextSource};
use dag_core::dag::{DagError, DagNode, node_event::NodeReporter};
use dag_core::node::NodeInput;
use dag_core::registry::NodeCtx;
use dag_core::value::FileRef;

use super::literature_fulltext::{LiteratureFulltextNode, LiteratureFulltextSpec};
use crate::shared::BibShared;
use crate::stored_files::{stored_fulltext, vfs_virtual_path};

struct Fixture {
    shared: Arc<BibShared>,
    context: NodeCtx,
    storage: Arc<vfs::OpendalFileStorage>,
    row: FullText,
}

impl Fixture {
    async fn new() -> Self {
        let storage = Arc::new(vfs::OpendalFileStorage::new_temp());
        let shared = Arc::new(
            BibShared::open_in_memory()
                .await
                .unwrap()
                .with_file_storage(storage.clone()),
        );
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            Some(storage.clone()),
        );
        let article = Article::new("fulltext-integrity", "Engineering fixture")
            .with_doi("10.1000/fulltext-integrity");
        shared.bib.upsert_article(&article).await.unwrap();
        let stored = stored_fulltext(&article.id, "paper.txt", b"original");
        storage
            .write_bytes(
                &vfs_virtual_path(&stored.path).unwrap(),
                b"original".to_vec(),
            )
            .await
            .unwrap();
        let row = FullText {
            attachment_key: None,
            article_id: article.id.clone(),
            file_path: stored.path,
            file_format: FileFormat::Txt,
            text_content: None,
            source: FullTextSource::UserUpload,
            file_hash: Some(stored.file_hash),
            file_size: Some(8),
            uploaded_at: None,
            extract_status: None,
            text_format: None,
            extracted_by: None,
            extract_error: None,
        };
        shared.bib.upsert_fulltext(&row).await.unwrap();
        storage
            .write_bytes(
                "/evidence.json",
                EvidenceSet {
                    records: vec![EvidenceRecord {
                        citation: article,
                        origin: None,
                        note: None,
                    }],
                    ..Default::default()
                }
                .to_bytes()
                .unwrap(),
            )
            .await
            .unwrap();
        Self {
            shared,
            context,
            storage,
            row,
        }
    }

    async fn run(&self, extra_input: bool) -> Result<Vec<FileRef>, DagError> {
        let mut node = LiteratureFulltextNode::with_shared(
            LiteratureFulltextSpec {
                fetch_missing: Some(false),
            },
            self.shared.clone(),
        );
        let mut inputs = vec![NodeInput::file(
            0,
            FileRef::new("vfs:///evidence.json", Some(FORMAT.into())),
        )];
        if extra_input {
            inputs.push(NodeInput::file(
                0,
                FileRef::new("vfs:///evidence.json", Some(FORMAT.into())),
            ));
        }
        let outputs = node
            .execute(&self.context, &inputs, &NodeReporter::noop())
            .await?;
        Ok(outputs.get(&0).unwrap().as_file_set().unwrap().to_vec())
    }

    async fn save_row(&self) {
        self.shared.bib.upsert_fulltext(&self.row).await.unwrap();
    }
}

#[tokio::test]
async fn valid_stored_fulltext_is_verified_and_not_declared_immutable() {
    let fixture = Fixture::new().await;
    let files = fixture.run(false).await.unwrap();
    assert_eq!(files.len(), 1);
    let fingerprint = files[0].fingerprint.as_ref().unwrap();
    assert_eq!(fingerprint.size, 8);
    assert_eq!(
        fingerprint.content_hash.as_deref(),
        Some(format!("sha256:{}", fixture.row.file_hash.unwrap()).as_str())
    );
    assert!(!fingerprint.immutable_remote);
}

#[tokio::test]
async fn deleted_backing_file_cannot_publish_a_success_fileset() {
    let fixture = Fixture::new().await;
    fixture
        .storage
        .delete_object(&vfs_virtual_path(&fixture.row.file_path).unwrap())
        .await
        .unwrap();
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn equal_length_content_tampering_cannot_reuse_database_hash() {
    let fixture = Fixture::new().await;
    fixture
        .storage
        .write_bytes(
            &vfs_virtual_path(&fixture.row.file_path).unwrap(),
            b"tampered".to_vec(),
        )
        .await
        .unwrap();
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn wrong_database_size_is_not_published_as_actual_file_size() {
    let mut fixture = Fixture::new().await;
    fixture.row.file_size = Some(999);
    fixture.save_row().await;
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn malformed_database_hash_is_rejected() {
    let mut fixture = Fixture::new().await;
    fixture.row.file_hash = Some("not-a-sha256".into());
    fixture.save_row().await;
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn missing_legacy_hash_and_size_are_computed_from_runtime_bytes() {
    let mut fixture = Fixture::new().await;
    let expected = fixture.row.file_hash.clone().unwrap();
    fixture.row.file_hash = None;
    fixture.row.file_size = None;
    fixture.save_row().await;
    let files = fixture.run(false).await.unwrap();
    let fingerprint = files[0].fingerprint.as_ref().unwrap();
    assert_eq!(fingerprint.size, 8);
    assert_eq!(
        fingerprint.content_hash.as_deref(),
        Some(format!("sha256:{expected}").as_str())
    );
}

#[tokio::test]
async fn library_and_runtime_storage_mismatch_is_not_success() {
    let mut fixture = Fixture::new().await;
    let other = Arc::new(vfs::OpendalFileStorage::new_temp());
    let size = fixture
        .storage
        .content_length("/evidence.json")
        .await
        .unwrap();
    let evidence = fixture
        .storage
        .read_range("/evidence.json", 0..size)
        .await
        .unwrap();
    other
        .write_bytes("/evidence.json", evidence.to_vec())
        .await
        .unwrap();
    fixture.context = NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        Some(other),
    );
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn unrelated_uri_is_not_materialized_from_inline_text() {
    let mut fixture = Fixture::new().await;
    fixture.row.file_path = "https://example.invalid/untrusted.txt".into();
    fixture.row.text_content = Some("untrusted inline text".into());
    fixture.save_row().await;
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn multiple_evidence_inputs_are_not_silently_ignored() {
    let fixture = Fixture::new().await;
    assert!(fixture.run(true).await.is_err());
}

#[tokio::test]
async fn negative_database_size_is_not_cast_to_unsigned_identity() {
    let mut fixture = Fixture::new().await;
    fixture.row.file_size = Some(-1);
    fixture.save_row().await;
    assert!(fixture.run(false).await.is_err());
}

#[tokio::test]
async fn fulltext_database_read_error_is_not_reported_as_normal_absence() {
    let mut fixture = Fixture::new().await;
    let article = Article::new("fulltext-integrity", "Engineering fixture")
        .with_doi("10.1000/fulltext-integrity");
    fixture.shared = Arc::new(
        bib_base::test_fixtures::library_with_failed_reads(
            &article,
            &fixture.row,
            bib_base::test_fixtures::MissingTable::Fulltexts,
        )
        .await
        .unwrap()
        .with_file_storage(fixture.storage.clone()),
    );
    assert!(
        fixture
            .shared
            .bib
            .get_fulltext(&fixture.row.article_id)
            .await
            .is_err()
    );
    println!("FULLTEXT_TABLE_READ_FAILURE_CONFIRMED");
    let error = fixture.run(false).await.unwrap_err().to_string();
    assert!(!error.contains("no full text resolved"), "{error}");
    assert!(error.contains("fulltexts"), "{error}");
}

#[tokio::test]
async fn identifier_database_read_error_is_not_reported_as_normal_absence() {
    let mut fixture = Fixture::new().await;
    let article = Article::new("fulltext-integrity", "Engineering fixture")
        .with_doi("10.1000/fulltext-integrity");
    fixture.shared = Arc::new(
        bib_base::test_fixtures::library_with_failed_reads(
            &article,
            &fixture.row,
            bib_base::test_fixtures::MissingTable::Identifiers,
        )
        .await
        .unwrap()
        .with_file_storage(fixture.storage.clone()),
    );
    assert!(
        fixture
            .shared
            .bib
            .find_by_identifier(bib_types::IdKind::Doi, "10.1000/fulltext-integrity")
            .await
            .is_err()
    );
    println!("IDENTIFIER_TABLE_READ_FAILURE_CONFIRMED");
    let error = fixture.run(false).await.unwrap_err().to_string();
    assert!(!error.contains("no full text resolved"), "{error}");
    assert!(error.contains("identifiers"), "{error}");
}
