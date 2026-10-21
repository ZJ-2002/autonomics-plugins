# Fixed donor-level design and official DESeq2 adapter. No scientific approval.
b_check <- function(ok, msg) if (!isTRUE(ok)) stop(msg, call.=FALSE)
b_keys <- function(x, keys, label) b_check(is.list(x) && !is.null(names(x)) &&
  !anyDuplicated(names(x)) && setequal(names(x),keys), paste(label,"fields differ"))
b_id <- function(x) is.character(x) && length(x)==1L && !is.na(x) && nzchar(x) &&
  identical(trimws(x),x) && !grepl("[\\t\\r\\n]",x,perl=TRUE)
b_link <- function(p) { target<-Sys.readlink(p);!is.na(target) && nzchar(target) }
b_sha <- function(path) {
  b_check(file.exists(path) && !b_link(path),"regular input required")
  result <- system2("sha256sum",shQuote(path),stdout=TRUE,stderr=TRUE)
  b_check(is.null(attr(result,"status")) && length(result)==1L && grepl("^[0-9a-f]{64}  ",result),"content hashing failed")
  substr(result,1L,64L)
}
b_read_json <- function(path) {
  x<-jsonlite::fromJSON(path,simplifyVector=FALSE)
  walk<-function(v) {
    if (is.list(v)) {
      if (!is.null(names(v))) b_check(!anyDuplicated(names(v)),"duplicate JSON identity")
      invisible(lapply(v,walk))
    }
  };walk(x);x
}
b_tsv <- function(path) {
  x<-utils::read.delim(path,colClasses="character",check.names=FALSE,quote="",comment.char="",na.strings=NULL)
  b_check(!anyDuplicated(names(x)) && !anyNA(x),"TSV identity missing or duplicated");x
}
b_integer <- function(x,positive=FALSE) is.numeric(x) && length(x)==1L && is.finite(x) &&
  x==floor(x) && (if(positive) x>0 else x>=0)
b_equal_json <- function(a,b) {
  if(is.list(a) && is.list(b)) {
    if(length(a)!=length(b) || is.null(names(a))!=is.null(names(b))) return(FALSE)
    if(!is.null(names(a))) return(setequal(names(a),names(b)) && all(vapply(names(a),function(k) b_equal_json(a[[k]],b[[k]]),logical(1))))
    return(all(vapply(seq_along(a),function(i) b_equal_json(a[[i]],b[[i]]),logical(1))))
  };identical(a,b)
}

b_load <- function(config_path,paths,stage) {
  b_check(stage %in% c("DESIGN","DESEQ2"),"fixed execution stage required")
  for(pkg in c("jsonlite","Matrix")) b_check(requireNamespace(pkg,quietly=TRUE),paste("package unavailable:",pkg))
  c<-b_read_json(config_path)
  b_keys(c,c("schema_version","protocol_version","status","method","contrast_id","scope","design",
    "software_lock","method_parameters","input_sha256","limits"),"donor config")
  b_check(identical(c$schema_version,1L) && (is.character(c$protocol_version) && length(c$protocol_version)==1L && !is.na(c$protocol_version) && c$protocol_version %in% c("4.2.1","4.3.2")) &&
    identical(c$status,"FROZEN") && identical(c$method,"DESEQ2_WALD"),"frozen supported core B count model required")
  b_check(b_id(c$contrast_id),"contrast identity missing")
  b_keys(paths,c("counts","genes","samples","decisions"),"actual inputs")
  hashes<-lapply(paths,b_sha);b_keys(c$input_sha256,names(paths),"input SHA256")
  b_check(all(vapply(names(paths),function(k) identical(hashes[[k]],c$input_sha256[[k]]),logical(1))),"actual input identity mismatch")
  b_keys(c$software_lock,c("R","Matrix","jsonlite","DESeq2","mv_binary_sha256"),"software lock")
  b_check(identical(c$software_lock$mv_binary_sha256,b_sha(Sys.which("mv"))),"fixed publication binary differs")
  mv_version<-system2("mv","--version",stdout=TRUE,stderr=TRUE)
  b_check(length(mv_version)>0L && grepl("^mv \\(GNU coreutils\\) ",mv_version[1L]),"GNU no-clobber publisher required")
  for(pkg in c("R","Matrix","jsonlite")) {
    actual<-if(pkg=="R") as.character(getRversion()) else as.character(utils::packageVersion(pkg))
    b_check(identical(c$software_lock[[pkg]],actual),paste("software lock differs:",pkg))
  }
  b_check(b_id(c$software_lock$DESeq2) && grepl("^[0-9]+[.][0-9]+[.][0-9]+$",c$software_lock$DESeq2),"declared DESeq2 version required")
  # Package absence is checked before any output, even for non-estimable models.
  # DESIGNS do not claim numerical method acceptance and do not load DESeq2.
  if(stage=="DESEQ2") {
    b_check(requireNamespace("DESeq2",quietly=TRUE),"package unavailable: DESeq2; no substitute algorithm")
    b_check(identical(c$software_lock$DESeq2,as.character(utils::packageVersion("DESeq2"))),"DESeq2 software lock differs")
  }
  b_keys(c$design,c("independence","numerator","denominator","covariates","min_cells","family_min_units","qr_tolerance"),"design")
  d<-c$design;b_check(b_id(d$independence) && d$independence %in% c("UNPAIRED","PAIRED") && b_id(d$numerator) &&
    b_id(d$denominator) && d$numerator!=d$denominator,"explicit independent/paired contrast required")
  b_check(is.list(d$covariates) && b_integer(d$min_cells,TRUE) && b_integer(d$family_min_units,TRUE) && d$family_min_units %in% c(2L,3L) &&
    is.numeric(d$qr_tolerance) && length(d$qr_tolerance)==1L && is.finite(d$qr_tolerance) &&
    d$qr_tolerance>0 && d$qr_tolerance<=1e-8,"explicit cell/N/rank policies required")
  b_keys(c$scope,c("original_cohort_id","species","tissue","anatomic_site","cell_type","timepoints"),"contrast scope")
  b_check(all(vapply(c$scope[setdiff(names(c$scope),"timepoints")],b_id,logical(1))) &&
    is.list(c$scope$timepoints) && length(c$scope$timepoints)>0L && all(vapply(c$scope$timepoints,b_id,logical(1))) &&
    !anyDuplicated(unlist(c$scope$timepoints)),"complete cohort/tissue/time scope required")
  if(d$independence=="UNPAIRED") b_check(length(c$scope$timepoints)==1L,"unpaired model cannot mix timepoints")
  b_keys(c$limits,c("max_dense_elements"),"count limits")
  b_check(b_integer(c$limits$max_dense_elements,TRUE),"explicit dense memory admission required")
  p<-c$method_parameters
  b_keys(p,c("fit_type","size_factor_type","minmu","cooks_cutoff","allowed_warning_messages"),"DESeq2 parameters")
  b_check(b_id(p$fit_type) && p$fit_type %in% c("parametric","local","mean") && b_id(p$size_factor_type) && p$size_factor_type %in% c("ratio","poscounts") &&
    is.numeric(p$minmu) && length(p$minmu)==1L && is.finite(p$minmu) && p$minmu>0 &&
    (identical(p$cooks_cutoff,FALSE) || (is.numeric(p$cooks_cutoff) && length(p$cooks_cutoff)==1L && is.finite(p$cooks_cutoff) && p$cooks_cutoff>0)) &&
    is.list(p$allowed_warning_messages) && all(vapply(p$allowed_warning_messages,b_id,logical(1))),"fixed method parameters required")
  genes<-b_tsv(paths$genes);samples<-b_tsv(paths$samples);decisions<-b_tsv(paths$decisions)
  b_check(identical(names(genes),c("matrix_row","gene_id","analysis_id","family_id","contrast_id","estimand_id")) &&
    nrow(genes)>0L && !anyDuplicated(genes$gene_id) && !anyDuplicated(genes$analysis_id) &&
    all(vapply(genes$gene_id,b_id,logical(1))) && all(vapply(genes$analysis_id,b_id,logical(1))) &&
    identical(genes$matrix_row,as.character(seq_len(nrow(genes)))) && all(genes$family_id=="B_TRANSCRIPTOME") &&
    all(genes$contrast_id==c$contrast_id) && all(genes$estimand_id=="E_B_DIS"),"complete registered gene universe required")
  base<-c("matrix_column","observation_id","independent_unit_id","original_cohort_id","species","tissue","anatomic_site",
          "cell_type","group","timepoint","n_cells","member_identity_resolved")
  cov_names<-vapply(d$covariates,function(v) {
    b_keys(v,c("name","type","levels"),"covariate")
    b_check(b_id(v$name) && grepl("^[A-Za-z][A-Za-z0-9_]*$",v$name) &&
      !v$name %in% c(base,"condition","unit_id","if","else","for","while","repeat","function","TRUE","FALSE","NULL","NA","Inf","NaN"),"safe non-reserved covariate required")
    b_check(b_id(v$type) && v$type %in% c("NUMERIC","FACTOR"),"typed frozen covariate required")
    if(v$type=="NUMERIC") b_check(is.null(v$levels),"numeric covariate cannot have levels") else
      b_check(is.list(v$levels) && length(v$levels)>=2L && !anyDuplicated(unlist(v$levels)) && all(vapply(v$levels,b_id,logical(1))),"complete factor levels required")
    v$name
  },character(1))
  b_check(!anyDuplicated(cov_names) && identical(names(samples),c(base,cov_names)) && nrow(samples)>0L &&
    identical(samples$matrix_column,as.character(seq_len(nrow(samples)))) && !anyDuplicated(samples[c("observation_id","cell_type")]) &&
    all(vapply(samples$independent_unit_id,b_id,logical(1))) && all(samples$member_identity_resolved %in% c("TRUE","FALSE")) &&
    all(grepl("^[0-9]+$",samples$n_cells)),"complete observation/biological-unit metadata required")
  b_check(identical(names(decisions),c("matrix_column","include","reason")) &&
    identical(decisions$matrix_column,samples$matrix_column) && all(decisions$include %in% c("YES","NO")) &&
    all(nzchar(trimws(decisions$reason[decisions$include=="NO"]))),"full frozen inclusion flow required")
  connection<-file(paths$counts,open="rt")
  geometry<-tryCatch({
    header<-readLines(connection,n=1L,warn=FALSE)
    b_check(length(header)==1L && header %in% c("%%MatrixMarket matrix coordinate integer general","%%MatrixMarket matrix coordinate real general"),"general coordinate raw-count format required")
    line<-readLines(connection,n=1L,warn=FALSE);comments<-0L
    while(length(line) && startsWith(line,"%")) {
      comments<-comments+1L;b_check(comments<=10000L,"excessive matrix header")
      line<-readLines(connection,n=1L,warn=FALSE)
    }
    shape<-strsplit(trimws(line),"[[:space:]]+")[[1L]]
    b_check(length(shape)==3L && all(grepl("^[0-9]+$",shape)),"matrix dimensions invalid")
    as.numeric(shape)
  },finally=close(connection))
  b_check(all(is.finite(geometry)) && identical(geometry[1:2],as.double(c(nrow(genes),nrow(samples)))) &&
    prod(geometry[1:2])<=c$limits$max_dense_elements && geometry[3L]<=prod(geometry[1:2]),
    "count dimensions/memory bound before matrix allocation")
  counts<-Matrix::readMM(paths$counts)
  b_check(identical(dim(counts),c(nrow(genes),nrow(samples))) && prod(as.double(dim(counts)))<=c$limits$max_dense_elements &&
    all(is.finite(counts@x)) && all(counts@x>=0) && all(counts@x==floor(counts@x)) &&
    all(counts@x<=.Machine$integer.max) && length(counts@x)==geometry[3L],"DESeq2 integer counts/dimensions/memory bound required")
  # readMM retains duplicate coordinate entries; a forged source cannot exploit
  # implicit sparse coalescing to change the count interpretation.
  coords<-paste(counts@i,counts@j,sep=":");b_check(!anyDuplicated(coords),"duplicate count coordinates")
  chosen<-which(decisions$include=="YES");data<-samples[chosen,,drop=FALSE]
  for(k in setdiff(names(c$scope),"timepoints")) b_check(all(data[[k]]==c$scope[[k]]),paste("mixed frozen scope:",k))
  b_check(all(data$timepoint %in% unlist(c$scope$timepoints)) && all(data$group %in% c(d$denominator,d$numerator)),"selected group/time outside frozen contrast")
  list(config=c,config_sha256=b_sha(config_path),hashes=hashes,genes=genes,samples=samples,decisions=decisions,
       counts=counts,chosen=chosen,data=data,cov_names=cov_names,paths=paths,config_path=config_path)
}

b_design <- function(x) {
  d<-x$config$design;data<-x$data;reasons<-character();n<-setNames(integer(2),c(d$denominator,d$numerator))
  for(g in names(n)) n[g]<-length(unique(data$independent_unit_id[data$group==g]))
  if(!nrow(data)) reasons<-c(reasons,"NO_INCLUDED_OBSERVATIONS")
  if(any(data$member_identity_resolved!="TRUE")) reasons<-c(reasons,"UNRESOLVED_POOL_DESCRIPTIVE_ONLY")
  if(any(as.numeric(data$n_cells)<d$min_cells)) reasons<-c(reasons,"INCLUDED_OBSERVATION_BELOW_FROZEN_CELL_MINIMUM")
  if(length(x$chosen) && any(Matrix::colSums(x$counts[,x$chosen,drop=FALSE])==0)) reasons<-c(reasons,"ZERO_COUNT_LIBRARY")
  if(d$independence=="UNPAIRED") {
    if(anyDuplicated(data$independent_unit_id)) reasons<-c(reasons,"REPEATED_UNIT_CANNOT_BE_INDEPENDENT_REPLICATE")
  } else {
    pairs<-table(factor(data$independent_unit_id),factor(data$group,levels=names(n)))
    if(!nrow(pairs) || any(pairs!=1L)) reasons<-c(reasons,"PAIRED_UNIT_REQUIRES_EXACTLY_ONE_OBSERVATION_PER_ARM")
  }
  if(any(n<2L)) reasons<-c(reasons,"SINGLE_UNIT_DESCRIPTIVE_ONLY")
  data$condition<-factor(data$group,levels=c(d$denominator,d$numerator))
  if(d$independence=="PAIRED") data$unit_id<-factor(data$independent_unit_id,levels=sort(unique(data$independent_unit_id)))
  for(v in d$covariates) {
    raw<-data[[v$name]]
    if(v$type=="NUMERIC") {
      value<-suppressWarnings(as.numeric(raw));if(any(!nzchar(raw) | !is.finite(value))) reasons<-c(reasons,paste0("MISSING_OR_NONFINITE_COVARIATE:",v$name))
    } else {
      value<-factor(raw,levels=unlist(v$levels));if(any(is.na(value))) reasons<-c(reasons,paste0("COVARIATE_OUTSIDE_FROZEN_LEVELS:",v$name))
    };data[[v$name]]<-value
  }
  formula<-stats::reformulate(c(if(d$independence=="PAIRED") "unit_id","condition",x$cov_names))
  matrix<-NULL;rank<-NA_integer_;residual_df<-NA_integer_;warnings<-character()
  if(!length(reasons)) {
    matrix<-stats::model.matrix(formula,data=data,contrasts.arg=lapply(data[vapply(data,is.factor,logical(1))],function(v) stats::contr.treatment(levels(v),base=1L)))
    rank<-qr(matrix,tol=d$qr_tolerance,LAPACK=FALSE)$rank;residual_df<-nrow(matrix)-rank
    if(rank!=ncol(matrix)) reasons<-c(reasons,"DESIGN_NOT_FULL_RANK")
    if(residual_df<=0L) reasons<-c(reasons,"NO_RESIDUAL_DEGREES_OF_FREEDOM")
  }
  low<-any(n<3L);status<-if(length(reasons)) "NOT_ESTIMABLE" else "DESIGN_IDENTIFIABLE_NOT_METHOD_ACCEPTANCE"
  list(status=status,reasons=unique(reasons),independent_unit_counts=as.list(n),low_precision_exploratory=low,
       candidate_family_p_allowed=!length(reasons) && all(n>=d$family_min_units),
       primary_disease_confirmation_allowed=FALSE,power_adequacy_verified=FALSE,scientific_approval_verified=FALSE,
       residual_df=residual_df,rank=rank,design_columns=if(is.null(matrix)) character() else colnames(matrix),
       design_matrix=if(is.null(matrix)) NULL else unname(matrix),selected_columns=x$chosen,
       data=data,formula=formula)
}

b_wald_quality <- function(r,dds) {
  b_check(identical(rownames(r),rownames(dds)),"official coefficient/fit row identity differs")
  converged<-S4Vectors::mcols(dds)$betaConv
  b_check(is.logical(converged) && length(converged)==nrow(r),"official coefficient convergence diagnostics missing")
  good<-is.finite(r$pvalue) & r$pvalue>=0 & r$pvalue<=1 & is.finite(r$log2FoldChange) &
    is.finite(r$lfcSE) & r$lfcSE>0 & converged %in% TRUE
  reason<-ifelse(is.finite(r$baseMean) & r$baseMean==0,"ALL_ZERO_COUNTS",
    ifelse(!converged %in% TRUE,"OFFICIAL_WALD_COEFFICIENT_NOT_CONVERGED","OFFICIAL_WALD_RESULT_UNAVAILABLE_OR_OUTLIER"))
  reason[good]<-"";list(estimable=good,reasons=reason,beta_converged=converged)
}

# Canonical order is a fixed implementation rule, not a model-parameter slot.
# Keep x, selected_columns and source-order QA/design matrices unchanged.
b_canonical_fit_order <- function(x,design) {
  chosen<-x$chosen;ids<-as.character(design$data$observation_id)
  b_check(length(chosen)>0L && !anyNA(chosen) && !anyDuplicated(chosen) &&
    all(chosen %in% seq_len(nrow(x$samples))) && length(ids)==length(chosen) &&
    all(vapply(ids,b_id,logical(1))) && !anyDuplicated(ids) &&
    identical(ids,as.character(x$samples$observation_id[chosen])),
    "complete unique source-bound observation IDs required for canonical fit")
  fit_order<-order(ids,method="radix")
  b_check(identical(sort(fit_order),seq_along(chosen)),"canonical fit order must be a full source-axis bijection")
  fit_order
}

b_deseq <- function(x,design) {
  genes<-x$genes;result<-data.frame(analysis_id=genes$analysis_id,estimand_id=genes$estimand_id,
    gene_id=genes$gene_id,contrast_id=genes$contrast_id,family_id=genes$family_id,
    status="NOT_ESTIMABLE",raw_p=NA_real_,family_p=NA_real_,log2_fold_change=NA_real_,standard_error=NA_real_,
    base_mean=NA_real_,beta_converged=NA,reason=paste(design$reasons,collapse=";"),low_precision_exploratory=design$low_precision_exploratory,
    family_p_status="NOT_ESTIMABLE",family_p_reason=paste(design$reasons,collapse=";"),
    stringsAsFactors=FALSE)
  warning_messages<-character();dds<-NULL
  if(!identical(design$status,"NOT_ESTIMABLE")) {
    p<-x$config$method_parameters
    fit_order<-b_canonical_fit_order(x,design)
    counts<-as.matrix(x$counts[,x$chosen[fit_order],drop=FALSE]);storage.mode(counts)<-"integer"
    data<-design$data[fit_order,,drop=FALSE]
    rownames(counts)<-genes$gene_id;colnames(counts)<-data$observation_id
    rownames(data)<-colnames(counts)
    withCallingHandlers({
      dds<-DESeq2::DESeqDataSetFromMatrix(countData=counts,colData=data,design=design$formula)
      dds<-DESeq2::DESeq(dds,test="Wald",fitType=p$fit_type,sfType=p$size_factor_type,betaPrior=FALSE,
        minReplicatesForReplace=Inf,parallel=FALSE,quiet=TRUE,minmu=p$minmu)
      b_check(identical(attr(DESeq2::dispersionFunction(dds),"fitType"),p$fit_type),"automatic dispersion-fit substitution forbidden")
      r<-DESeq2::results(dds,contrast=c("condition",x$config$design$numerator,x$config$design$denominator),
        independentFiltering=FALSE,pAdjustMethod="none",cooksCutoff=p$cooks_cutoff,lfcThreshold=0,parallel=FALSE)
      b_check(identical(rownames(r),genes$gene_id),"official result gene universe differs")
      result$raw_p<-r$pvalue;result$log2_fold_change<-r$log2FoldChange;result$standard_error<-r$lfcSE;result$base_mean<-r$baseMean
      quality<-b_wald_quality(r,dds);good<-quality$estimable;result$beta_converged<-quality$beta_converged
      result$status[good]<-"ESTIMATED";result$reason[good]<-""
      result$reason[!good]<-quality$reasons[!good]
      result$raw_p[!good]<-NA_real_
      result$family_p_reason[!good]<-result$reason[!good]
      if(design$candidate_family_p_allowed) {
        result$family_p[good]<-result$raw_p[good];result$family_p_status[good]<-"ESTIMATED";result$family_p_reason[good]<-""
      } else result$family_p_reason[good]<-"BELOW_FROZEN_FAMILY_UNIT_MINIMUM_LOW_PRECISION"
    },warning=function(w) {
      msg<-conditionMessage(w);warning_messages<<-c(warning_messages,msg)
      b_check(msg %in% unlist(p$allowed_warning_messages),paste("unapproved official method warning:",msg));invokeRestart("muffleWarning")
    })
  }
  # Full BH/BY belongs to the complete registered multi-contrast family stage,
  # never this per-contrast producer. Missing P values remain NA, not deleted.
  list(results=result,official_rds=dds,warnings=warning_messages)
}


b_verify_qa <- function(path,x,design) {
  qa<-b_read_json(path);sha<-b_sha(path)
  expected_design<-jsonlite::fromJSON(jsonlite::toJSON(design[setdiff(names(design),c("data","formula"))],auto_unbox=TRUE,na="null",null="null",digits=17),simplifyVector=FALSE)
  b_check(identical(qa$scope,"DONOR_COUNT_MODEL_COMPONENT_NOT_G0_OR_SCIENTIFIC_ACCEPTANCE") && identical(qa$stage,"DESIGN") &&
    identical(qa$config_sha256,x$config_sha256) && b_equal_json(qa$input_sha256,x$hashes) &&
    b_equal_json(qa$design,expected_design) && b_equal_json(qa$software_lock,x$config$software_lock) &&
    identical(qa$model_formula,paste(deparse(design$formula),collapse="")) && identical(qa$method_executed,FALSE) &&
    identical(qa$formal_authorized,FALSE) && identical(qa$scientific_approval_verified,FALSE) && identical(qa$family_frozen,FALSE),
    "actual same-source design receipt differs")
  sha
}

b_main <- function(args) {
  b_check(length(args)>=1L && ((args[1L]=="DESIGN" && length(args)==7L) ||
    (args[1L]=="DESEQ2" && length(args)==8L)),"usage: donor.R DESIGN|DESEQ2 config counts genes samples decisions [actual-design-audit-for-DESEQ2] new-output-directory")
  out<-tail(args,1L);b_check(!file.exists(out) && !b_link(out),"output already exists")
  x<-b_load(args[2L],setNames(as.list(args[3:6]),c("counts","genes","samples","decisions")),args[1L]);d<-b_design(x)
  audit<-list(scope="DONOR_COUNT_MODEL_COMPONENT_NOT_G0_OR_SCIENTIFIC_ACCEPTANCE",stage=args[1L],
    config_sha256=x$config_sha256,input_sha256=x$hashes,software_lock=x$config$software_lock,
    design=d[setdiff(names(d),c("data","formula"))],method_executed=FALSE,formal_authorized=FALSE,
    scientific_approval_verified=FALSE,family_frozen=FALSE,model_formula=paste(deparse(d$formula),collapse=""))
  fit<-NULL;if(args[1L]=="DESEQ2") {
    qa_sha<-b_verify_qa(args[7L],x,d)
    audit$design_receipt_sha256<-qa_sha
    fit<-b_deseq(x,d);audit$method_executed<-!is.null(fit$official_rds);audit$method_warnings<-fit$warnings
    b_check(identical(qa_sha,b_sha(args[7L])),"design receipt changed during method")
  }
  b_check(identical(b_sha(args[2L]),x$config_sha256) && identical(lapply(x$paths,b_sha),x$hashes),"input changed during model processing")
  parent<-dirname(out);b_check(dir.exists(parent) && !b_link(parent),"regular private output parent required")
  stage<-tempfile(pattern=".donor-stage-",tmpdir=parent);b_check(dir.create(stage),"cannot create owned staging")
  on.exit(if(dir.exists(stage)) unlink(stage,recursive=TRUE),add=TRUE)
  if(!is.null(fit)) {
    utils::write.table(fit$results,file.path(stage,"results.tsv"),sep="\t",quote=FALSE,row.names=FALSE,na="NA")
    saveRDS(fit$official_rds,file.path(stage,"official.rds"))
  }
  jsonlite::write_json(audit,file.path(stage,"audit.json"),auto_unbox=TRUE,pretty=TRUE,na="null",null="null",digits=17)
  # Same private container directory; external artifact publication occurs only
  # after successful execution. No existing directory can be replaced.
  b_check(!file.exists(out),"output appeared during processing")
  move<-system2("mv",c("--no-clobber","--no-target-directory","--",shQuote(stage),shQuote(out)),stdout=TRUE,stderr=TRUE)
  b_check(is.null(attr(move,"status")) && !dir.exists(stage) && dir.exists(out),"no-clobber complete output publication failed")
  cat(jsonlite::toJSON(list(scope=audit$scope,stage=args[1L],design_status=d$status,formal_authorized=FALSE),auto_unbox=TRUE),"\n")
}
if(sys.nframe()==0L) tryCatch(b_main(commandArgs(TRUE)),error=function(e) {cat("BLOCKED:",conditionMessage(e),"\n",file=stderr());quit(status=2L)})
