# Independent normalized-array official limma component, not source/G0 approval.
bulk_check <- function(ok,msg) if(!isTRUE(ok)) stop(msg,call.=FALSE)
bulk_keys <- function(x,keys,label) bulk_check(is.list(x) && !is.null(names(x)) && !anyDuplicated(names(x)) && setequal(names(x),keys),paste(label,"fields differ"))
bulk_id <- function(x) is.character(x) && length(x)==1L && !is.na(x) && nzchar(x) && identical(trimws(x),x) && !grepl("[\t\r\n]",x)
bulk_link <- function(p) {x<-Sys.readlink(p);!is.na(x) && nzchar(x)}
bulk_regular <- function(p) {
  bulk_check(bulk_id(p) && file.exists(p) && !isTRUE(file.info(p)$isdir),"regular input required")
  ancestors<-p
  while(tail(ancestors,1L)!="/" && dirname(tail(ancestors,1L))!=tail(ancestors,1L)) ancestors<-c(ancestors,dirname(tail(ancestors,1L)))
  bulk_check(!any(vapply(ancestors,bulk_link,logical(1))),"symlink input or ancestor")
}
bulk_sha <- function(p) {bulk_regular(p);digest::digest(file=p,algo="sha256",serialize=FALSE)}
bulk_json <- function(p) {
  x<-jsonlite::fromJSON(p,simplifyVector=FALSE)
  walk<-function(v) if(is.list(v)) {
    if(!is.null(names(v))) bulk_check(!anyDuplicated(names(v)),"duplicate JSON key")
    invisible(lapply(v,walk))
  }
  walk(x);x
}
bulk_equal <- function(a,b) {
  if(is.list(a) && is.list(b)) {
    if(length(a)!=length(b) || is.null(names(a))!=is.null(names(b))) return(FALSE)
    if(!is.null(names(a))) return(setequal(names(a),names(b)) && all(vapply(names(a),function(k) bulk_equal(a[[k]],b[[k]]),logical(1))))
    return(all(vapply(seq_along(a),function(i) bulk_equal(a[[i]],b[[i]]),logical(1))))
  }
  identical(a,b)
}
bulk_tsv <- function(p) {
  x<-utils::read.delim(p,colClasses="character",check.names=FALSE,quote="",comment.char="",na.strings=NULL)
  bulk_check(!anyDuplicated(names(x)) && !anyNA(x),"missing or duplicate TSV identity");x
}
bulk_integer <- function(x,positive=FALSE) is.numeric(x) && length(x)==1L && is.finite(x) && x==floor(x) && (if(positive) x>0 else x>=0)

bulk_load <- function(config_path,paths) {
  for(pkg in c("jsonlite","digest","limma","statmod")) bulk_check(requireNamespace(pkg,quietly=TRUE),paste("official package unavailable:",pkg))
  bulk_regular(config_path);bulk_check(file.info(config_path)$size<=64*1024^2,"configuration exceeds byte budget")
  config_sha<-bulk_sha(config_path);cfg<-bulk_json(config_path)
  bulk_keys(cfg,c("schema_version","protocol_version","status","method","expression_scale","contrast_id","design","software_lock","method_parameters","input_sha256","source_archive_sha256","resource_id","limits"),"bulk config")
  bulk_check(identical(cfg$schema_version,1L) && cfg$protocol_version %in% c("4.2.1","4.3.2") && identical(cfg$status,"FROZEN") &&
    identical(cfg$method,"LIMMA_EBAYES") && identical(cfg$expression_scale,"log2_normalized") && bulk_id(cfg$contrast_id) && bulk_id(cfg$resource_id) &&
    is.character(cfg$source_archive_sha256) && length(cfg$source_archive_sha256)==1L && grepl("^[0-9a-f]{64}$",cfg$source_archive_sha256),"frozen normalized-bulk original source contract required")
  bulk_keys(paths,c("expression","genes","samples","decisions"),"actual bulk inputs")
  bulk_keys(cfg$input_sha256,names(paths),"bound inputs")
  hashes<-lapply(paths,bulk_sha)
  bulk_check(all(vapply(names(paths),function(k) identical(cfg$input_sha256[[k]],hashes[[k]]),logical(1))),"actual bulk input hashes differ")
  bulk_keys(cfg$software_lock,c("R","limma","statmod","jsonlite","digest","stats"),"measured software lock")
  for(pkg in names(cfg$software_lock)) {
    measured<-if(pkg=="R") as.character(getRversion()) else as.character(utils::packageVersion(pkg))
    bulk_check(identical(cfg$software_lock[[pkg]],measured),paste("actual software differs:",pkg))
  }
  bulk_keys(cfg$limits,c("max_expression_elements","max_input_file_bytes"),"bulk limits")
  bulk_check(bulk_integer(cfg$limits$max_expression_elements,TRUE) && cfg$limits$max_expression_elements<=10000000 &&
    bulk_integer(cfg$limits$max_input_file_bytes,TRUE) && cfg$limits$max_input_file_bytes<=64*1024^2 &&
    all(vapply(paths,function(p) file.info(p)$size<=cfg$limits$max_input_file_bytes,logical(1))),"bounded bulk inputs required")
  bulk_keys(cfg$method_parameters,c("trend","robust","allowed_warning_messages"),"limma parameters")
  bulk_check(identical(cfg$method_parameters$trend,TRUE) && identical(cfg$method_parameters$robust,TRUE) &&
    is.list(cfg$method_parameters$allowed_warning_messages) && all(vapply(cfg$method_parameters$allowed_warning_messages,bulk_id,logical(1))),"fixed official limma/eBayes trend robust parameters required")
  d<-cfg$design;bulk_keys(d,c("numerator","denominator","covariates","family_min_units","qr_tolerance"),"bulk design")
  bulk_check(bulk_id(d$numerator) && bulk_id(d$denominator) && d$numerator!=d$denominator && is.list(d$covariates) &&
    bulk_integer(d$family_min_units,TRUE) && d$family_min_units>=3L && is.numeric(d$qr_tolerance) && length(d$qr_tolerance)==1L &&
    is.finite(d$qr_tolerance) && d$qr_tolerance>0 && d$qr_tolerance<=1e-4,"frozen group/unit/rank policies required")
  expression<-bulk_tsv(paths$expression);genes<-bulk_tsv(paths$genes);samples<-bulk_tsv(paths$samples);decisions<-bulk_tsv(paths$decisions)
  bulk_check(identical(names(genes),c("matrix_row","gene_id","analysis_id","family_id","contrast_id","estimand_id")) && nrow(genes)>0L &&
    !anyDuplicated(genes$gene_id) && !anyDuplicated(genes$analysis_id) && identical(genes$matrix_row,as.character(seq_len(nrow(genes)))) &&
    all(vapply(genes$gene_id,bulk_id,logical(1))) && all(vapply(genes$analysis_id,bulk_id,logical(1))) &&
    all(genes$family_id=="B_TRANSCRIPTOME") && all(genes$contrast_id==cfg$contrast_id) && all(genes$estimand_id=="E_B_DIS"),"complete original full gene family required")
  bulk_check(names(expression)[1L]=="gene_id" && identical(expression$gene_id,genes$gene_id) && ncol(expression)>=2L &&
    nrow(expression)*(ncol(expression)-1L)<=cfg$limits$max_expression_elements,"expression gene order/elements differ")
  expected_samples<-strsplit("resource_id patient_id independent_unit_id independent_unit_basis sample_id assay_id group weight_loss_6mo_pct sex age diagnosis treatment tissue sampling_time measurement_date outcome_start_date outcome_end_date include reason source_metadata_file source_metadata_sha256"," ")[[1L]]
  bulk_check(identical(names(samples),expected_samples) && !anyDuplicated(samples$sample_id) && !anyDuplicated(samples$independent_unit_id) &&
    identical(names(expression)[-1L],samples$sample_id) && all(samples$include=="YES") &&
    all(vapply(samples$sample_id,bulk_id,logical(1))) && all(vapply(samples$independent_unit_id,bulk_id,logical(1))),"actual sample/declared independent-unit order differs")
  bulk_check(identical(names(decisions),c("sample_id","independent_unit_id","include","reason")) && !anyDuplicated(decisions$sample_id) &&
    all(decisions$include %in% c("YES","NO")) && all(nzchar(decisions$reason[decisions$include=="NO"])) &&
    setequal(decisions$sample_id[decisions$include=="YES"],samples$sample_id),"complete original sample decisions required")
  matched<-match(samples$sample_id,decisions$sample_id)
  bulk_check(identical(decisions$independent_unit_id[matched],samples$independent_unit_id),"decision unit identities differ")
  values<-suppressWarnings(matrix(as.numeric(as.matrix(expression[,-1L,drop=FALSE])),nrow=nrow(expression)))
  bulk_check(all(is.finite(values)),"finite normalized expression required; no imputation")
  rownames(values)<-genes$gene_id;colnames(values)<-samples$sample_id
  list(config=cfg,config_sha256=config_sha,paths=paths,hashes=hashes,genes=genes,samples=samples,decisions=decisions,expression=values)
}

bulk_design <- function(x) {
  d<-x$config$design;data<-x$samples
  bulk_check(setequal(unique(data$group),c(d$denominator,d$numerator)),"two explicit disease groups required")
  data$group<-factor(data$group,levels=c(d$denominator,d$numerator));cov_names<-character()
  for(cov in d$covariates) {
    bulk_keys(cov,c("name","type","levels"),"covariate")
    bulk_check(bulk_id(cov$name) && cov$name %in% c("age","sex","treatment","batch") && cov$name %in% names(data) && !cov$name %in% cov_names,"covariate unsupported or duplicated")
    cov_names<-c(cov_names,cov$name);values<-data[[cov$name]]
    if(identical(cov$type,"NUMERIC")) {
      bulk_check(is.list(cov$levels) && length(cov$levels)==0L,"numeric factor levels forbidden")
      values<-suppressWarnings(as.numeric(values));bulk_check(all(is.finite(values)),"missing numeric covariate")
      data[[cov$name]]<-values
    } else {
      levels<-unlist(cov$levels,use.names=FALSE)
      bulk_check(identical(cov$type,"CATEGORICAL") && is.character(levels) && length(levels)>=2L && !anyDuplicated(levels) &&
        all(vapply(as.list(levels),bulk_id,logical(1))) && all(values %in% levels),"complete frozen categorical covariate required")
      data[[cov$name]]<-factor(values,levels=levels)
    }
  }
  formula<-stats::reformulate(c("group",cov_names));matrix<-stats::model.matrix(formula,data)
  rank<-qr(matrix,tol=d$qr_tolerance)$rank;residual<-nrow(matrix)-rank;arms<-table(data$group)
  minimum<-min(arms)
  identifiable<-rank==ncol(matrix) && residual>0L
  status<-if(!identifiable) "NOT_ESTIMABLE_DESIGN" else if(minimum>=d$family_min_units) "IDENTIFIABLE_DECLARED_UNITS" else if(minimum>=2L) "LOW_PRECISION_EXPLORATORY" else "DESCRIPTIVE_ONLY"
  list(status=status,n_case=unname(arms[d$numerator]),n_control=unname(arms[d$denominator]),sample_ids=x$samples$sample_id,
    independent_unit_ids=x$samples$independent_unit_id,model_columns=colnames(matrix),rank=rank,residual_df=residual,
    candidate_family_p_allowed=identifiable && minimum>=d$family_min_units,biological_independence_verified=FALSE,
    identifiable=identifiable,reason=if(!identifiable) "DESIGN_NOT_IDENTIFIABLE" else "",
    condition_coding="denominator reference; numerator minus denominator",data=data,formula=formula,matrix=matrix)
}
bulk_design_record <- function(d) d[setdiff(names(d),c("data","formula","matrix"))]

bulk_fit <- function(x,d) {
  result<-x$genes;n<-nrow(result)
  result$status<-"NOT_ESTIMABLE";result$reason<-if(d$status=="NOT_ESTIMABLE_DESIGN") "DESIGN_NOT_IDENTIFIABLE" else "DESCRIPTIVE_ONLY_INDEPENDENT_UNIT_COUNT"
  result$numerator<-x$config$design$numerator;result$denominator<-x$config$design$denominator
  result$raw_p<-result$family_p<-NA_real_;result$family_p_status<-"NOT_ESTIMABLE";result$family_p_reason<-result$reason
  for(key in c("log2_expression_difference","standard_error","ci_lower","ci_upper","moderated_t","moderated_df")) result[[key]]<-NA_real_
  result$average_expression<-rowMeans(x$expression);result$n_case<-d$n_case;result$n_control<-d$n_control
  warnings<-character();fit<-NULL
  variable<-apply(x$expression,1L,function(row) any(row!=row[1L]))
  result$reason[!variable]<-"CONSTANT_EXPRESSION";result$family_p_reason[!variable]<-"CONSTANT_EXPRESSION"
  if(d$status %in% c("IDENTIFIABLE_DECLARED_UNITS","LOW_PRECISION_EXPLORATORY") && any(variable)) {
    withCallingHandlers({
      ordinary<-limma::lmFit(x$expression[variable,,drop=FALSE],design=d$matrix)
      fit<-limma::eBayes(ordinary,trend=x$config$method_parameters$trend,robust=x$config$method_parameters$robust)
    },warning=function(w) {
      message<-conditionMessage(w);warnings<<-c(warnings,message)
      bulk_check(message %in% unlist(x$config$method_parameters$allowed_warning_messages),paste("unapproved official limma warning:",message));invokeRestart("muffleWarning")
    })
    beta<-fit$coefficients[,2L];se<-fit$stdev.unscaled[,2L]*sqrt(fit$s2.post);p<-fit$p.value[,2L];df<-fit$df.total
    half<-stats::qt(0.975,df=df)*se
    good<-is.finite(beta) & is.finite(se) & se>0 & is.finite(p) & p>=0 & p<=1 & is.finite(df) & df>0 & is.finite(half)
    slots<-which(variable);valid<-slots[good]
    result$reason[slots]<-"OFFICIAL_LIMMA_NONFINITE_OR_ZERO_PRECISION";result$family_p_reason[slots]<-result$reason[slots]
    result$log2_expression_difference[slots]<-beta;result$standard_error[slots]<-se
    result$ci_lower[slots]<-beta-half;result$ci_upper[slots]<-beta+half;result$moderated_t[slots]<-fit$t[,2L];result$moderated_df[slots]<-df
    result$status[valid]<-"ESTIMATED";result$reason[valid]<-"";result$raw_p[valid]<-p[good]
    if(d$candidate_family_p_allowed) {
      result$family_p[valid]<-result$raw_p[valid];result$family_p_status[valid]<-"ESTIMATED";result$family_p_reason[valid]<-""
    } else result$family_p_reason[valid]<-"BELOW_FROZEN_FAMILY_UNIT_MINIMUM_LOW_PRECISION"
  }
  # No topTable selection or per-contrast FDR: retain the full frozen gene set.
  list(results=result,official=list(fit=fit,variable_gene_ids=x$genes$gene_id[variable],full_gene_ids=x$genes$gene_id),warnings=warnings,method_executed=!is.null(fit))
}

bulk_main <- function(args) {
  bulk_check(length(args)>=1L && ((args[1L]=="DESIGN" && length(args)==7L) || (args[1L]=="LIMMA" && length(args)==8L)),"usage: bulk-limma.R DESIGN|LIMMA config expression genes samples decisions [actual-design-audit] new-output-directory")
  output<-tail(args,1L);bulk_check(!file.exists(output) && !bulk_link(output),"output exists; refusing overwrite")
  x<-bulk_load(args[2L],setNames(as.list(args[3:6]),c("expression","genes","samples","decisions")));d<-bulk_design(x)
  audit<-list(scope="BULK_NORMALIZED_MODEL_COMPONENT_NOT_G0_OR_SCIENTIFIC_ACCEPTANCE",stage=args[1L],protocol_version=x$config$protocol_version,
    config_sha256=x$config_sha256,input_sha256=x$hashes,software_lock=x$config$software_lock,design=bulk_design_record(d),
    model_formula=paste(deparse(d$formula),collapse=""),method_executed=FALSE,formal_authorized=FALSE,scientific_approval_verified=FALSE,
    biological_independence_verified=FALSE,source_qualified=FALSE,family_frozen=FALSE)
  fit<-NULL
  if(args[1L]=="LIMMA") {
    sha<-bulk_sha(args[7L]);qa<-bulk_json(args[7L])
    expected<-jsonlite::fromJSON(jsonlite::toJSON(audit,auto_unbox=TRUE,na="null",null="null",digits=17),simplifyVector=FALSE)
    expected$stage<-"DESIGN"
    bulk_check(bulk_equal(qa,expected),"actual same-source DESIGN receipt differs")
    fit<-bulk_fit(x,d);audit$design_receipt_sha256<-sha;audit$method_executed<-fit$method_executed;audit$method_warnings<-as.list(fit$warnings)
    bulk_check(identical(sha,bulk_sha(args[7L])),"DESIGN receipt changed during limma processing")
  }
  bulk_check(identical(bulk_sha(args[2L]),x$config_sha256) && identical(lapply(x$paths,bulk_sha),x$hashes),"bulk input changed during processing")
  parent<-dirname(output);bulk_check(dir.exists(parent) && !bulk_link(parent),"regular output parent required")
  ancestors<-parent
  while(tail(ancestors,1L)!="/" && dirname(tail(ancestors,1L))!=tail(ancestors,1L)) ancestors<-c(ancestors,dirname(tail(ancestors,1L)))
  bulk_check(!any(vapply(ancestors,bulk_link,logical(1))),"symlink output ancestor")
  stage<-tempfile(pattern=".bulk-limma-stage-",tmpdir=parent);bulk_check(dir.create(stage),"owned staging unavailable")
  on.exit(if(dir.exists(stage)) unlink(stage,recursive=TRUE),add=TRUE)
  if(!is.null(fit)) {
    utils::write.table(fit$results,file.path(stage,"results.tsv"),sep="\t",quote=FALSE,row.names=FALSE,na="NA")
    saveRDS(fit$official,file.path(stage,"official.rds"))
  }
  jsonlite::write_json(audit,file.path(stage,"audit.json"),auto_unbox=TRUE,pretty=TRUE,na="null",null="null",digits=17)
  bulk_check(!file.exists(output),"output appeared during processing")
  moved<-system2("mv",c("--no-clobber","--no-target-directory","--",shQuote(stage),shQuote(output)),stdout=TRUE,stderr=TRUE)
  bulk_check(is.null(attr(moved,"status")) && !dir.exists(stage) && dir.exists(output),"complete no-clobber bulk publication failed")
  cat(jsonlite::toJSON(list(scope=audit$scope,stage=args[1L],design_status=d$status,formal_authorized=FALSE),auto_unbox=TRUE),"\n")
}
if(sys.nframe()==0L) tryCatch(bulk_main(commandArgs(TRUE)),error=function(e) {cat("BLOCKED:",conditionMessage(e),"\n",file=stderr());quit(status=2L)})
