# Core B official singscore on actual source-bound preparation outputs. No G0.
s_check <- function(ok,msg) if(!isTRUE(ok)) stop(msg,call.=FALSE)
s_keys <- function(x,keys,label) s_check(is.list(x) && !is.null(names(x)) &&
  !anyDuplicated(names(x)) && setequal(names(x),keys),paste(label,"fields differ"))
s_id <- function(x) is.character(x) && length(x)==1L && !is.na(x) && nzchar(x) &&
  identical(trimws(x),x) && !grepl("[\\t\\r\\n]",x,perl=TRUE)
s_link <- function(path) {v<-Sys.readlink(path);!is.na(v) && nzchar(v)}
s_sha <- function(path) {
  s_check(file.exists(path) && !isTRUE(file.info(path)$isdir) && !s_link(path),"regular method input required")
  parents<-dirname(path)
  while(tail(parents,1L)!="/" && tail(parents,1L)!=".") parents<-c(parents,dirname(tail(parents,1L)))
  s_check(!any(vapply(parents,s_link,logical(1))),"symlink input ancestor")
  value<-system2("sha256sum",shQuote(path),stdout=TRUE,stderr=TRUE)
  s_check(is.null(attr(value,"status")) && length(value)==1L && grepl("^[0-9a-f]{64}  ",value),"method input hashing failed")
  substr(value,1L,64L)
}
s_json <- function(path) {
  s_check(file.info(path)$size<=64*1024^2,"method metadata exceeds bounded reader")
  x<-jsonlite::fromJSON(path,simplifyVector=FALSE)
  walk<-function(v) {
    if(is.list(v)) {
      if(!is.null(names(v))) s_check(!anyDuplicated(names(v)),"duplicate JSON identity")
      invisible(lapply(v,walk))
    } else if(is.numeric(v)) s_check(all(is.finite(v)),"nonfinite JSON value")
  };walk(x);x
}
s_tsv <- function(path,columns=NULL) {
  x<-utils::read.delim(path,colClasses="character",check.names=FALSE,quote="",comment.char="",na.strings=NULL)
  s_check(!anyDuplicated(names(x)) && !anyNA(x) && (is.null(columns) || identical(names(x),columns)),"complete exact TSV schema required");x
}
s_equal <- function(a,b) {
  if(is.list(a) && is.list(b)) {
    if(length(a)!=length(b) || is.null(names(a))!=is.null(names(b))) return(FALSE)
    if(!is.null(names(a))) return(setequal(names(a),names(b)) && all(vapply(names(a),function(k) s_equal(a[[k]],b[[k]]),logical(1))))
    return(all(vapply(seq_along(a),function(i) s_equal(a[[i]],b[[i]]),logical(1))))
  };identical(a,b)
}
s_vector <- function(x,label) {
  s_check(is.list(x) && is.null(names(x)) && length(x)>0L && all(vapply(x,s_id,logical(1))),paste("explicit",label,"required"))
  v<-unlist(x,use.names=FALSE);s_check(!anyDuplicated(v),paste("duplicate",label));v
}
s_integer <- function(x,positive=FALSE) is.numeric(x) && length(x)==1L && is.finite(x) && x==floor(x) &&
  (if(positive) x>0 else x>=0)

s_load <- function(config_path,paths) {
  for(pkg in c("singscore","jsonlite","digest")) s_check(requireNamespace(pkg,quietly=TRUE),paste("official package unavailable:",pkg))
  config_sha<-s_sha(config_path);c<-s_json(config_path)
  s_keys(c,c("schema_version","protocol_version","status","method","scope","frozen_recipe","input_sha256", "gene_ids",
    "column_ids","ranking_background_gene_ids","prior_results_from_original_registry"),"prepared method config")
  scope<-"CORE_B_PROGRAM_SCORING_NOT_CONTRAST_FAMILY_IMAGE_OR_SCIENTIFIC_ACCEPTANCE"
  s_check(identical(c$schema_version,1L) && (is.character(c$protocol_version) && length(c$protocol_version)==1L && !is.na(c$protocol_version) && c$protocol_version %in% c("4.2.1","4.3.2")) && identical(c$status,"FROZEN") &&
    identical(c$method,"CORE_B_SINGSCORE") && identical(c$scope,scope),"frozen core B scoring recipe required")
  s_keys(paths,c("expression","members","coverage","column_qc","preparation_audit"),"actual method sources")
  hashes<-lapply(paths,s_sha);s_keys(c$input_sha256,setdiff(names(paths),"preparation_audit"),"actual score hashes")
  s_check(all(vapply(names(c$input_sha256),function(k) identical(c$input_sha256[[k]],hashes[[k]]),logical(1))),"actual method file identity differs")
  recipe<-c$frozen_recipe
  s_check(identical(recipe$protocol_version,c$protocol_version),"score recipe protocol differs")
  s_check(identical(recipe$module,"B") && identical(recipe$family,"B_PRIMARY_STATES") && identical(recipe$role,"CONDITIONAL_EXPLORATORY") &&
    identical(recipe$method,"CORE_B_SINGSCORE") && identical(recipe$status,"FROZEN"),"wrong core B recipe; B-SPEC replacement forbidden")
  parameters<-list(rank_axis="WITHIN_SAMPLE_ACROSS_GENES",tiesMethod="average",stableGenes=NULL,
    knownDirection=TRUE,centerScore=TRUE,score_column="TotalScore")
  s_check(s_equal(recipe$method_parameters,parameters),"official score parameters differ")
  s_keys(recipe$software_lock,c("R","singscore","jsonlite","digest","mv_binary_sha256"),"complete official software lock")
  for(pkg in c("R","singscore","jsonlite","digest")) {
    actual<-if(pkg=="R") as.character(getRversion()) else as.character(utils::packageVersion(pkg))
    s_check(identical(recipe$software_lock[[pkg]],actual),paste("official software lock differs:",pkg))
  }
  s_check(identical(recipe$software_lock$mv_binary_sha256,s_sha(Sys.which("mv"))),"fixed no-clobber publisher differs")
  mv_version<-system2("mv","--version",stdout=TRUE,stderr=TRUE)
  s_check(is.null(attr(mv_version,"status")) && length(mv_version)>0L && grepl("^mv \\(GNU coreutils\\) ",mv_version[1L]),"GNU publisher required")
  s_check(s_integer(recipe$seed) && recipe$seed<=.Machine$integer.max,"explicit integer seed required");set.seed(recipe$seed)
  audit<-s_json(paths$preparation_audit)
  s_check(identical(audit$protocol_version,c$protocol_version),"preparation audit protocol differs")
  prepared_identity<-audit$output_identity[["scoring-config.json"]]
  s_check(identical(audit$scope,"CORE_B_PROGRAM_SCORE_INPUTS_NOT_METHOD_IMAGE_FAMILY_OR_SCIENTIFIC_ACCEPTANCE") &&
    s_equal(audit$frozen_recipe,recipe) && identical(prepared_identity$sha256,config_sha) &&
    identical(as.double(prepared_identity$bytes),unname(file.info(config_path)$size)) &&
    identical(audit$input_sha256$expression,hashes$expression) && identical(audit$input_sha256$column_qc,hashes$column_qc) &&
    s_equal(audit$prior_results_from_original_registry,c$prior_results_from_original_registry),"actual same-source preparation receipt differs")
  for(key in c("formal_authorized","family_frozen","scientific_approval_verified","mapping_biological_validity_verified",
    "biological_independence_verified","official_method_executed","directions_inferred_from_project_results","result_viewing_history_reset"))
    s_check(identical(audit[[key]],FALSE),paste("preparation authority/viewing-history promotion:",key))
  s_check(identical(audit$all_source_members_retained,TRUE) && identical(audit$all_original_columns_retained,TRUE),"incomplete preparation universe")
  for(k in c("members","coverage"))
    s_check(identical(audit$output_identity[[paste0(k,".tsv")]]$sha256,hashes[[k]]) &&
      identical(as.double(audit$output_identity[[paste0(k,".tsv")]]$bytes),unname(file.info(paths[[k]])$size)),"actual prepared member/coverage bytes differ")
  genes<-s_vector(c$gene_ids,"gene universe");columns<-s_vector(c$column_ids,"column universe")
  background<-s_vector(c$ranking_background_gene_ids,"ranking background")
  s_check(all(background %in% genes) && identical(columns,as.character(seq_along(columns))) &&
    s_integer(recipe$limits$max_dense_elements,TRUE) && length(genes)*as.double(length(columns))<=recipe$limits$max_dense_elements &&
    s_integer(recipe$limits$max_input_file_bytes,TRUE) && all(file.info(unlist(paths))$size<=recipe$limits$max_input_file_bytes) &&
    s_integer(recipe$limits$background_min_genes,TRUE) && length(background)>=recipe$limits$background_min_genes,
    "complete expression exceeds frozen memory/file/background budget")
  expr<-s_tsv(paths$expression,c("gene_id",columns))
  s_check(identical(expr$gene_id,genes),"complete normalized gene universe differs")
  matrix<-matrix(suppressWarnings(as.numeric(as.matrix(expr[-1L]))),nrow=length(genes),dimnames=list(genes,columns))
  qc<-s_tsv(paths$column_qc)
  s_check(identical(qc$column,columns) && all(qc$normalization_status %in% c("TPM_AVAILABLE","NOT_SCORABLE")) &&
    all(qc$descriptive_only %in% c("TRUE","FALSE")) && all(qc$member_identity_resolved %in% c("TRUE","FALSE")) &&
    all(qc$program_inference_eligible=="FALSE" & qc$biological_independence_verified=="FALSE"),"complete original column eligibility required")
  available<-which(qc$normalization_status=="TPM_AVAILABLE")
  for(j in seq_along(columns)) {
    if(j %in% available) s_check(all(is.finite(matrix[,j])) && all(matrix[,j]>=0) && abs(sum(matrix[,j])-1e6)<=1e-7,"qualified TPM column differs")
    else s_check(all(expr[[j+1L]]=="NA") && nzchar(qc$normalization_reason[j]),"unscorable column cannot be filled or ranked")
  }
  members<-s_tsv(paths$members,c("program_id","program_instance_id","source_member_id","source_species","direction",
    "gene_id","mapping_status","mapping_reason","measured_status"))
  coverage<-s_tsv(paths$coverage,c("program_id","program_instance_id","original_members","mapped_members","measured_members",
    "coverage","up_original_members","up_measured_members","up_coverage","down_original_members","down_measured_members",
    "down_coverage","status","reason"))
  programs<-recipe$programs;s_check(is.list(programs) && length(programs)>0L,"explicit frozen program instances required")
  ids<-vapply(programs,function(p) p$program_instance_id,character(1))
  s_check(!anyDuplicated(ids) && identical(coverage$program_instance_id,ids) && setequal(unique(members$program_instance_id),ids) &&
    !anyDuplicated(members[c("program_instance_id","source_member_id")]) && all(members$direction %in% c("UP","DOWN")),"complete unique original program/member universe required")
  for(i in seq_along(programs)) {
    p<-programs[[i]];rows<-members[members$program_instance_id==ids[i],,drop=FALSE];cv<-coverage[i,,drop=FALSE]
    s_check(all(rows$program_id==p$program_id) && identical(cv$program_id,p$program_id) && all(rows$source_species==p$mapping_recipe$input_species),"program source identity differs")
    mapped<-rows$mapping_status=="MAPPED"
    s_check(all(rows$mapping_status %in% c("MAPPED","UNMAPPED")) && all(nzchar(rows$gene_id[mapped])) &&
      !anyDuplicated(rows$gene_id[mapped]) && all(!nzchar(rows$mapping_reason[mapped])) &&
      all(!nzchar(rows$gene_id[!mapped]) & nzchar(rows$mapping_reason[!mapped])),"complete explicit unique mapped membership required")
    expected<-ifelse(!mapped,"UNMAPPED",ifelse(!rows$gene_id %in% genes,"UNMEASURED",
      ifelse(!rows$gene_id %in% background,"OUTSIDE_FROZEN_BACKGROUND","MEASURED")))
    s_check(identical(rows$measured_status,expected),"actual member measurement/background classification differs")
    arm_total<-vapply(c("UP","DOWN"),function(d) sum(rows$direction==d),integer(1))
    arm_measured<-vapply(c("UP","DOWN"),function(d) sum(rows$direction==d & expected=="MEASURED"),integer(1))
    measured<-sum(expected=="MEASURED");fraction<-measured/nrow(rows);arm_fraction<-arm_measured/arm_total
    s_check(s_integer(p$members_min,TRUE) && is.numeric(p$coverage_min) && p$coverage_min>0 && p$coverage_min<=1 &&
      is.numeric(p$signed_arm_coverage_min) && p$signed_arm_coverage_min>0 && p$signed_arm_coverage_min<=1,"explicit frozen coverage policy required")
    reason<-if(arm_total["UP"]==0L) "DOWN_ONLY_DIRECTION_REQUIRES_SEPARATE_METHOD_QUALIFICATION" else
      if(measured<p$members_min || fraction<p$coverage_min || any(arm_total>0 & (arm_measured==0L | arm_fraction<p$signed_arm_coverage_min)))
        "FROZEN_SIGNATURE_COVERAGE_OR_MEMBERS_INSUFFICIENT" else
        if(any(arm_measured>=length(background))) "SIGNATURE_ARM_SPANS_ENTIRE_BACKGROUND" else ""
    s_check(identical(cv$reason,reason) && identical(cv$status,if(nzchar(reason)) "NOT_ESTIMABLE" else "SCORING_ELIGIBLE") &&
      identical(cv$original_members,as.character(nrow(rows))) && identical(cv$mapped_members,as.character(sum(mapped))) &&
      identical(cv$measured_members,as.character(measured)) && abs(as.numeric(cv$coverage)-fraction)<1e-15 &&
      identical(cv$up_original_members,as.character(arm_total["UP"])) && identical(cv$up_measured_members,as.character(arm_measured["UP"])) &&
      identical(cv$down_original_members,as.character(arm_total["DOWN"])) && identical(cv$down_measured_members,as.character(arm_measured["DOWN"])),
      "actual complete signature coverage differs")
    for(d in c("UP","DOWN")) {
      actual<-cv[[if(d=="UP") "up_coverage" else "down_coverage"]]
      s_check(if(arm_total[d]==0L) identical(actual,"NA") else
        is.finite(suppressWarnings(as.numeric(actual))) && abs(as.numeric(actual)-arm_fraction[d])<1e-15,
        "actual signed-arm coverage fraction differs")
    }
  }
  list(config=c,config_path=config_path,config_sha256=config_sha,paths=paths,hashes=hashes,matrix=matrix,
    background=background,available=available,qc=qc,members=members,coverage=coverage,programs=programs,ids=ids)
}

s_score <- function(x) {
  ranks<-if(length(x$available)) singscore::rankGenes(x$matrix[x$background,x$available,drop=FALSE],tiesMethod="average",stableGenes=NULL) else NULL
  official<-list();scores<-list();calls<-0L
  for(i in seq_along(x$programs)) {
    p<-x$programs[[i]];cv<-x$coverage[i,,drop=FALSE]
    value<-rep(NA_real_,nrow(x$qc));reason<-if(cv$status=="NOT_ESTIMABLE") rep(cv$reason,nrow(x$qc)) else x$qc$normalization_reason
    if(cv$status=="SCORING_ELIGIBLE" && length(x$available)) {
      rows<-x$members[x$members$program_instance_id==x$ids[i] & x$members$measured_status=="MEASURED",,drop=FALSE]
      up<-rows$gene_id[rows$direction=="UP"];down<-rows$gene_id[rows$direction=="DOWN"]
      # Official S4 dispatch distinguishes an omitted downSet from NULL.
      fit<-if(length(down)) singscore::simpleScore(ranks,upSet=up,downSet=down,knownDirection=TRUE,centerScore=TRUE) else
        singscore::simpleScore(ranks,upSet=up,knownDirection=TRUE,centerScore=TRUE)
      s_check(identical(rownames(fit),x$qc$column[x$available]) && length(fit$TotalScore)==length(x$available) &&
        all(is.finite(fit$TotalScore)),"official scoring returned incomplete/nonfinite column values")
      value[x$available]<-fit$TotalScore;official[[x$ids[i]]]<-fit;calls<-calls+1L
    }
    scores[[i]]<-data.frame(dataset_id=x$config$frozen_recipe$dataset_id,program_id=p$program_id,program_instance_id=x$ids[i],
      column=x$qc$column,observation_id=x$qc$observation_id,independent_unit_id=x$qc$independent_unit_id,
      group=x$qc$group,timepoint=x$qc$timepoint,cell_type=x$qc$cell_type,TotalScore=value,
      status=ifelse(is.finite(value),"ESTIMATED","NOT_ESTIMABLE"),reason=reason,
      descriptive_only=x$qc$descriptive_only,biological_independence_verified="FALSE",program_inference_eligible="FALSE")
  }
  list(scores=do.call(rbind,scores),official=list(ranks=ranks,scores=official),calls=calls)
}

s_main <- function(args) {
  s_check(length(args)==7L,"usage: score.R prepared-config expression members coverage column-qc actual-preparation-audit new-output-directory")
  out<-args[7L];s_check(startsWith(out,"/") && out!="/" && !grepl("(^|/)\\.\\.(/|$)",out) && !file.exists(out) && !s_link(out),"new private absolute output directory required")
  x<-s_load(args[1L],setNames(as.list(args[2:6]),c("expression","members","coverage","column_qc","preparation_audit")))
  result<-s_score(x)
  s_check(identical(s_sha(x$config_path),x$config_sha256) && identical(lapply(x$paths,s_sha),x$hashes),"method inputs changed while scoring")
  parent<-dirname(out);s_check(dir.exists(parent) && !s_link(parent),"private existing output parent required")
  parents<-parent;while(tail(parents,1L)!="/") parents<-c(parents,dirname(tail(parents,1L)))
  s_check(!any(vapply(parents,s_link,logical(1))),"symlink output ancestor")
  stage<-tempfile(pattern=".b-state-score-stage-",tmpdir=parent);s_check(dir.create(stage),"cannot create owned scoring stage")
  on.exit(if(dir.exists(stage)) unlink(stage,recursive=TRUE),add=TRUE)
  utils::write.table(result$scores,file.path(stage,"scores.tsv"),sep="\t",quote=FALSE,row.names=FALSE,na="NA")
  for(name in c("members","coverage")) s_check(file.copy(x$paths[[name]],file.path(stage,paste0(name,".tsv")),overwrite=FALSE),"cannot retain full original member/coverage bytes")
  saveRDS(result$official,file.path(stage,"official.rds"),compress=FALSE)
  published_names<-c("scores.tsv","members.tsv","coverage.tsv","official.rds")
  published_identity<-setNames(lapply(published_names,function(name) {
    path<-file.path(stage,name);list(sha256=s_sha(path),bytes=unname(file.info(path)$size))
  }),published_names)
  audit<-list(schema_version=1L,protocol_version=x$config$protocol_version,scope=x$config$scope,method="CORE_B_SINGSCORE",
    config_sha256=x$config_sha256,input_sha256=x$hashes,software_lock=x$config$frozen_recipe$software_lock,
    method_parameters=x$config$frozen_recipe$method_parameters,output_identity=published_identity,
    prior_results_from_original_registry=x$config$prior_results_from_original_registry,
    rank_genes_executed=!is.null(result$official$ranks),simple_score_calls=result$calls,official_method_executed=result$calls>0L,
    all_source_members_retained=TRUE,all_original_columns_retained=TRUE,result_viewing_history_reset=FALSE,
    formal_authorized=FALSE,family_frozen=FALSE,scientific_approval_verified=FALSE,biological_independence_verified=FALSE)
  jsonlite::write_json(audit,file.path(stage,"audit.json"),auto_unbox=TRUE,pretty=TRUE,na="null",null="null",digits=17)
  s_check(!file.exists(out) && !s_link(out),"output appeared during scoring")
  move<-system2("mv",c("--no-clobber","--no-target-directory","--",shQuote(stage),shQuote(out)),stdout=TRUE,stderr=TRUE)
  s_check(is.null(attr(move,"status")) && !dir.exists(stage) && dir.exists(out),"no-clobber complete scoring publication failed")
  cat(jsonlite::toJSON(list(scope=audit$scope,formal_authorized=FALSE,official_method_executed=audit$official_method_executed),auto_unbox=TRUE),"\n")
}
if(sys.nframe()==0L) tryCatch(s_main(commandArgs(TRUE)),error=function(e) {cat("BLOCKED:",conditionMessage(e),"\n",file=stderr());quit(status=2L)})
