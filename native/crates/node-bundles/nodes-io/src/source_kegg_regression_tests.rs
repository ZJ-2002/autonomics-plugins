use super::*;

#[test]
fn selected_gene_aliases_have_one_frozen_identity() {
    assert_eq!(canonical_gene_id("10458", "hsa").unwrap(), "hsa:10458");
    assert_eq!(canonical_gene_id("hsa:10458", "hsa").unwrap(), "hsa:10458");
    for value in [
        "mmu:10458",
        " hsa:10458",
        "hsa:",
        "10458/other",
        "10458+other",
        "10458\n",
    ] {
        assert!(canonical_gene_id(value, "hsa").is_err(), "{value:?}");
    }
}

#[test]
fn strict_pairs_accept_crlf_and_empty_results_not_error_markup() {
    assert!(kegg::parser::checked_pairs("\r\n").unwrap().is_empty());
    let rows =
        kegg::parser::checked_pairs("hsa:10458\tpath:hsa00010\r\nhsa:10458\tpath:hsa00010\r\n")
            .unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].source, "hsa:10458");
    assert_eq!(rows[0].target, "path:hsa00010");
    assert!(kegg::parser::checked_pairs("<html>temporarily unavailable</html>").is_err());
}

#[test]
fn selected_pairs_require_exact_organism_and_five_ascii_digits() {
    for organism in ["hsa", "eco", "abcd"] {
        validate_gene_pathway_pair(
            &format!("{organism}:b0002"),
            &format!("path:{organism}00010"),
            organism,
        )
        .unwrap();
    }
    for value in [
        "path:hsa0001",
        "path:hsa000100",
        "path:hsa０００１０",
        "map00010",
        "path:map00010",
    ] {
        assert!(validate_gene_pathway_pair("hsa:10458", value, "hsa").is_err());
    }
}

#[test]
fn mapper_retains_broad_maps_for_downstream_policy() {
    for digits in ["01100", "01110", "01120"] {
        let pathway = format!("hsa{digits}");
        validate_gene_pathway_pair("hsa:10458", &format!("path:{pathway}"), "hsa").unwrap();
        assert_eq!(
            normalize_pathway_id(&pathway, KeggPathwayIdStyle::Map),
            format!("map{digits}")
        );
        assert_eq!(
            normalize_pathway_id(&pathway, KeggPathwayIdStyle::Organism),
            pathway
        );
    }
}

#[test]
fn repeated_brite_classes_are_deduplicated_without_name_guessing() {
    let hierarchy: KeggBriteNode = serde_json::from_value(serde_json::json!({"name":"br08901","children":[
        {"name":"B category","children":[{"name":"map00010 Synthetic pathway"}]},
        {"name":"A category","children":[{"name":"00010 Synthetic pathway"},{"name":"00010 Synthetic pathway"}]}]})).unwrap();
    let mut details = BTreeMap::new();
    collect_pathway_hierarchy(&hierarchy, &mut details).unwrap();
    assert_eq!(details.len(), 1);
    assert_eq!(details["map00010"].class, "A category;B category");
    assert_eq!(details["map00010"].name, "Synthetic pathway");
}

#[tokio::test]
async fn empty_dual_outputs_keep_every_declared_field() {
    let annotation = build_annotation_batch(Vec::new()).unwrap();
    let metadata = build_metadata_batch(Vec::new()).unwrap();
    assert_eq!(annotation.num_rows(), 0);
    assert_eq!(metadata.num_rows(), 0);
    assert_eq!(annotation.schema().fields().len(), 5);
    assert_eq!(metadata.schema().fields().len(), 4);
    assert!(
        annotation
            .schema()
            .fields()
            .iter()
            .all(|field| field.data_type() == &DataType::Utf8 && !field.is_nullable())
    );
    assert!(
        metadata.schema().fields()[..2]
            .iter()
            .all(|field| !field.is_nullable())
    );
    assert!(
        metadata.schema().fields()[2..]
            .iter()
            .all(|field| field.is_nullable())
    );
}

#[tokio::test]
async fn selected_strings_accept_views_and_large_offsets_not_numbers() {
    for values in [
        Arc::new(StringArray::from(vec![Some("10458"), Some("hsa:10458")]))
            as arrow_array::ArrayRef,
        Arc::new(arrow_array::LargeStringArray::from(vec![
            Some("10458"),
            Some("hsa:10458"),
        ])) as arrow_array::ArrayRef,
        Arc::new(arrow_array::StringViewArray::from(vec![
            Some("10458"),
            Some("hsa:10458"),
        ])) as arrow_array::ArrayRef,
    ] {
        let batch = RecordBatch::try_new(
            Arc::new(Schema::new(vec![Field::new(
                "gene",
                values.data_type().clone(),
                true,
            )])),
            vec![values],
        )
        .unwrap();
        let frame = SessionContext::new().read_batch(batch).unwrap();
        assert_eq!(
            checked_selected_genes(&frame, "gene", "hsa", "test")
                .await
                .unwrap(),
            BTreeSet::from(["hsa:10458".into()])
        );
    }
    let values = Arc::new(arrow_array::Int64Array::from(vec![10458]));
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new(
            "gene",
            DataType::Int64,
            false,
        )])),
        vec![values],
    )
    .unwrap();
    let frame = SessionContext::new().read_batch(batch).unwrap();
    assert!(
        checked_selected_genes(&frame, "gene", "hsa", "test")
            .await
            .is_err()
    );
}
