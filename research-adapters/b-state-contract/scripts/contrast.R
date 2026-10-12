# Explicit core B donor contrast candidate; source-consistent declarations are not biological acceptance.
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

# Preparation writes standard CSV-quoted TSV. Official score tables use the
# separate quote-disabled reader; conflating these changes clinical values.
c_prepared_tsv <- function(path,columns) {
  x<-utils::read.delim(path,colClasses="character",check.names=FALSE,quote="\"",comment.char="",na.strings=NULL)
  s_check(!anyDuplicated(names(x)) && !anyNA(x) && identical(names(x),columns) &&
    !any(vapply(x,function(v) any(grepl("[\\t\\r\\n]",v,perl=TRUE)),logical(1))),"complete non-injectable prepared TSV required");x
}

c_load <- function(config_path,paths) {
  s_check(requireNamespace("jsonlite",quietly=TRUE),"required jsonlite package unavailable")
  config_sha<-s_sha(config_path);c<-s_json(config_path)
  s_keys(c,c("schema_version","protocol_version","status","method","scope","frozen_recipe","column_ids",
    "program_instances","prior_results_from_original_registry","input_sha256"),"prepared contrast config")
  s_check(identical(c$schema_version,1L) && (is.character(c$protocol_version) && length(c$protocol_version)==1L && !is.na(c$protocol_version) && c$protocol_version %in% c("4.2.1","4.3.2")) && identical(c$status,"FROZEN") &&
    identical(c$method,"CORE_B_SCORE_CONTRAST") && identical(c$scope,"CORE_B_SCORE_CONTRAST_NOT_FAMILY_IMAGE_OR_SCIENTIFIC_ACCEPTANCE"),
    "explicit core B prepared contrast recipe required")
  recipe<-c$frozen_recipe
  s_keys(recipe,c("schema_version","protocol_version","status","module","family","role","method","dataset_id","input_sha256",
    "software_lock","preparation_software_lock","contrasts","analyses","limits","method_parameters"),"frozen recipe")
  s_check(identical(recipe$schema_version,1L) && identical(recipe$protocol_version,c$protocol_version) && identical(recipe$status,"FROZEN") &&
    identical(recipe$module,"B") && identical(recipe$family,"B_PRIMARY_STATES") && identical(recipe$role,"CONDITIONAL_EXPLORATORY") &&
    identical(recipe$method,c$method) && s_id(recipe$dataset_id),"B-SPEC/core method substitution forbidden")
  expected<-list(alternative="two.sided",conf_level=.95,missing_selected_score="RETAIN_NA_NO_SAMPLE_DROP",degenerate_variance="RETAIN_NA_NO_METHOD_FALLBACK")
  s_check(s_equal(recipe$method_parameters,expected),"frozen contrast parameters differ")
  source_keys<-c("score_config","score_preparation_audit","scores","score_audit","score_members","score_coverage","column_qc",
    "count_audit","sample_map","metadata_pack","decisions","normalization_config","normalization_receipt")
  s_keys(recipe$input_sha256,source_keys,"all thirteen producer/source identities")
  s_check(all(vapply(recipe$input_sha256,function(v) s_id(v) && grepl("^[0-9a-f]{64}$",v),logical(1))),"complete producer content hashes required")
  s_keys(recipe$preparation_software_lock,"python","preparation lock")
  s_check(s_id(recipe$preparation_software_lock$python) && grepl("^[0-9]+\\.[0-9]+\\.[0-9]+$",recipe$preparation_software_lock$python),"explicit preparation software version required")
  s_keys(recipe$software_lock,c("R","stats","jsonlite","mv_binary_sha256"),"complete official contrast/publisher lock")
  for(pkg in c("R","stats","jsonlite")) {
    actual<-if(pkg=="R") as.character(getRversion()) else as.character(utils::packageVersion(pkg))
    s_check(identical(recipe$software_lock[[pkg]],actual),paste("official contrast software differs:",pkg))
  }
  s_check(identical(recipe$software_lock$mv_binary_sha256,s_sha(Sys.which("mv"))),"fixed no-clobber publisher differs")
  mv_version<-system2("mv","--version",stdout=TRUE,stderr=TRUE)
  s_check(is.null(attr(mv_version,"status")) && grepl("^mv \\(GNU coreutils\\) ",mv_version[1L]),"GNU publisher required")
  s_keys(paths,c("samples","decisions","scores","coverage","preparation_audit"),"actual contrast method paths")
  hashes<-lapply(paths,s_sha)
  s_keys(c$input_sha256,c("samples","decisions","scores","coverage"),"actual method identities")
  s_check(all(vapply(names(c$input_sha256),function(k) identical(c$input_sha256[[k]],hashes[[k]]),logical(1))),"actual contrast method input differs")
  audit<-s_json(paths$preparation_audit)
  s_check(identical(audit$protocol_version,c$protocol_version),"preparation audit protocol differs")
  s_check(identical(audit$scope,"CORE_B_SCORE_CONTRAST_INPUTS_NOT_METHOD_FAMILY_OR_SCIENTIFIC_ACCEPTANCE") &&
    s_equal(audit$frozen_recipe,recipe) && s_equal(audit$input_sha256,recipe$input_sha256) &&
    identical(audit$output_identity[["contrast-config.json"]]$sha256,config_sha) &&
    identical(as.double(audit$output_identity[["contrast-config.json"]]$bytes),unname(file.info(config_path)$size)) &&
    identical(audit$input_sha256$scores,hashes$scores) && identical(audit$input_sha256$score_coverage,hashes$coverage) &&
    s_equal(audit$prior_results_from_original_registry,c$prior_results_from_original_registry),"actual same-source contrast preparation receipt required")
  for(k in c("samples","decisions"))
    s_check(identical(audit$output_identity[[paste0(k,".tsv")]]$sha256,hashes[[k]]) &&
      identical(as.double(audit$output_identity[[paste0(k,".tsv")]]$bytes),unname(file.info(paths[[k]])$size)),"actual complete prepared source differs")
  for(k in c("formal_authorized","family_frozen","scientific_approval_verified","biological_independence_verified",
    "result_viewing_history_reset","covariates_imputed","contrast_method_executed","disease_definition_scientifically_qualified"))
    s_check(identical(audit[[k]],FALSE),paste("preparation authority/data promotion:",k))
  for(k in c("all_score_rows_retained","all_original_columns_retained","all_declared_analysis_rows_retained"))
    s_check(identical(audit[[k]],TRUE),"incomplete contrast preparation universe")
  s_keys(recipe$limits,c("max_input_file_bytes","max_score_rows","max_contrast_sample_rows"),"explicit frozen method limits")
  s_check(all(vapply(recipe$limits,s_integer,logical(1),positive=TRUE)) &&
    all(file.info(unlist(paths))$size<=recipe$limits$max_input_file_bytes),"contrast method exceeds file budget")
  columns<-s_vector(c$column_ids,"complete original column universe")
  s_check(identical(columns,as.character(seq_along(columns))),"complete original score column order required")
  programs<-c$program_instances
  s_check(is.list(programs) && length(programs)>0L,"complete original program instances required")
  for(p in programs) {s_keys(p,c("program_id","program_instance_id"),"program identity");s_check(s_id(p$program_id) && s_id(p$program_instance_id),"invalid program identity")}
  ids<-vapply(programs,function(p) p$program_instance_id,character(1));parents<-vapply(programs,function(p) p$program_id,character(1))
  s_check(!anyDuplicated(ids) && setequal(names(c$prior_results_from_original_registry),ids),"complete program/viewing-history identity required")
  sample_fields<-strsplit("column observation_id independent_unit_id unit_kind original_cohort_id species tissue anatomic_site cell_type group timepoint n_cells member_identity_resolved normalization_status normalization_reason cachexia_definition cachexia_status bone_metastasis_status lesion_type treatment sex age batches"," ")[[1L]]
  samples<-c_prepared_tsv(paths$samples,sample_fields)
  s_check(identical(samples$column,columns) && all(samples$member_identity_resolved %in% c("TRUE","FALSE")) &&
    all(samples$unit_kind %in% c("DONOR","ANIMAL","POOL")) && all(samples$normalization_status %in% c("TPM_AVAILABLE","NOT_SCORABLE")) &&
    all(vapply(samples$independent_unit_id,s_id,logical(1))),"complete source sample/biological declarations required")
  score_fields<-strsplit("dataset_id program_id program_instance_id column observation_id independent_unit_id group timepoint cell_type TotalScore status reason descriptive_only biological_independence_verified program_inference_eligible"," ")[[1L]]
  scores<-s_tsv(paths$scores,score_fields)
  s_check(nrow(scores)<=recipe$limits$max_score_rows && identical(scores$program_instance_id,rep(ids,each=length(columns))) &&
    identical(scores$column,rep(columns,length(ids))) && identical(scores$program_id,rep(parents,each=length(columns))) &&
    all(scores$dataset_id==recipe$dataset_id) && all(scores$biological_independence_verified=="FALSE" & scores$program_inference_eligible=="FALSE"),
    "complete original program-by-column score identity required")
  for(k in c("observation_id","independent_unit_id","group","timepoint","cell_type"))
    s_check(identical(scores[[k]],rep(samples[[k]],length(ids))),"actual complete source score metadata differs")
  coverage<-s_tsv(paths$coverage)
  s_check(identical(coverage$program_instance_id,ids) && identical(coverage$program_id,parents) &&
    all(coverage$status %in% c("SCORING_ELIGIBLE","NOT_ESTIMABLE")),"complete original coverage universe required")
  for(i in seq_along(ids)) {
    part<-scores[scores$program_instance_id==ids[i],,drop=FALSE];cv<-coverage[i,,drop=FALSE]
    reasons<-if(cv$status=="NOT_ESTIMABLE") rep(cv$reason,length(columns)) else samples$normalization_reason
    values<-suppressWarnings(as.numeric(part$TotalScore))
    s_check(identical(part$reason,reasons) && identical(part$status,ifelse(nzchar(reasons),"NOT_ESTIMABLE","ESTIMATED")) &&
      all(part$TotalScore[nzchar(reasons)]=="NA") && all(is.finite(values[!nzchar(reasons)])) &&
      all(abs(values[!nzchar(reasons)])<=1+1e-12) &&
      identical(part$descriptive_only,ifelse(samples$member_identity_resolved=="FALSE","TRUE","FALSE")),"score eligibility/NA/donor state differs")
  }
  contrasts<-recipe$contrasts;s_check(is.list(contrasts) && length(contrasts)>0L,"explicit nonempty frozen contrasts required")
  scope_fields<-c("original_cohort_id","species","tissue","anatomic_site","cell_type")
  for(d in contrasts) {
    s_keys(d,c("contrast_id","estimand_id","method","scope","numerator","denominator","group_timepoints","covariates","family_min_units","disease_interpretation"),"contrast design")
    s_check(s_id(d$contrast_id) && identical(d$estimand_id,"E_B_DIS") && d$method %in% c("WELCH_T","PAIRED_T") &&
      is.list(d$covariates) && is.null(names(d$covariates)) && length(d$covariates)==0L && s_id(d$numerator) && s_id(d$denominator) &&
      d$numerator!=d$denominator && s_integer(d$family_min_units,TRUE) && d$family_min_units %in% c(2L,3L) &&
      d$disease_interpretation %in% c("DISEASE_STATE_CANDIDATE","BACKGROUND_ONLY","PERTURBATION_REFERENCE"),"explicit supported unadjusted contrast design required")
    s_keys(d$scope,scope_fields,"complete contrast scope");s_check(all(vapply(d$scope,s_id,logical(1))),"invalid scope")
    s_keys(d$group_timepoints,c(d$numerator,d$denominator),"explicit group timepoints")
    s_check(all(vapply(d$group_timepoints,s_id,logical(1))) && (d$method=="PAIRED_T" ||
      identical(d$group_timepoints[[d$numerator]],d$group_timepoints[[d$denominator]])),"unpaired repeated timepoints forbidden")
  }
  cids<-vapply(contrasts,function(d) d$contrast_id,character(1));s_check(!anyDuplicated(cids),"duplicate contrast")
  semantic<-vapply(contrasts,function(d) paste(c(unlist(d$scope[scope_fields]),sort(paste(names(d$group_timepoints),unlist(d$group_timepoints),sep="="))),collapse="\t"),character(1))
  s_check(!anyDuplicated(semantic),"duplicate scientific contrast alias")
  analyses<-recipe$analyses;s_check(is.list(analyses) && length(analyses)==length(cids)*length(ids),"complete contrast/program analyses required")
  for(a in analyses) {
    s_keys(a,c("analysis_id","contrast_id","program_instance_id","status"),"analysis identity")
    s_check(s_id(a$analysis_id) && a$contrast_id %in% cids && a$program_instance_id %in% ids &&
      a$status %in% c("FROZEN","NOT_FROZEN","CLOSED_PRE_FREEZE"),"invalid analysis execution decision")
  }
  aids<-vapply(analyses,function(a) a$analysis_id,character(1));pairs<-vapply(analyses,function(a) paste(a$contrast_id,a$program_instance_id,sep="\t"),character(1))
  expected_pairs<-as.vector(outer(cids,ids,paste,sep="\t"))
  s_check(!anyDuplicated(aids) && !any(aids %in% cids) && !anyDuplicated(pairs) && setequal(pairs,expected_pairs),"complete unique analysis universe required")
  decisions<-c_prepared_tsv(paths$decisions,c("contrast_id","column","include","reason"))
  s_check(identical(decisions$contrast_id,rep(cids,each=length(columns))) && identical(decisions$column,rep(columns,length(cids))) &&
    nrow(decisions)*length(ids)<=recipe$limits$max_contrast_sample_rows && all(decisions$include %in% c("YES","NO")) &&
    all(nzchar(decisions$reason[decisions$include=="NO"])) && all(!nzchar(decisions$reason[decisions$include=="YES"])),
    "complete frozen contrast-by-original-column decisions required")
  for(d in contrasts) {
    # Membership is indexed explicitly by column, never by significance.
    selected<-samples[samples$column %in% decisions$column[decisions$contrast_id==d$contrast_id & decisions$include=="YES"],,drop=FALSE]
    s_check(all(vapply(scope_fields,function(k) all(selected[[k]]==d$scope[[k]]),logical(1))) &&
      all(selected$group %in% names(d$group_timepoints)) && all(vapply(seq_len(nrow(selected)),function(j)
        identical(selected$timepoint[j],d$group_timepoints[[selected$group[j]]]),logical(1))),"selected sample outside frozen scope/group/time")
  }
  list(config=c,config_path=config_path,config_sha=config_sha,paths=paths,hashes=hashes,samples=samples,scores=scores,
    coverage=coverage,decisions=decisions,analyses=analyses,contrasts=setNames(contrasts,cids))
}

c_fit <- function(x) {
  output<-list();selected_rows<-list();official<-list();calls<-0L
  for(i in seq_along(x$analyses)) {
    a<-x$analyses[[i]];d<-x$contrasts[[a$contrast_id]]
    selected<-x$samples$column %in% x$decisions$column[x$decisions$contrast_id==a$contrast_id & x$decisions$include=="YES"]
    samples<-x$samples[selected,,drop=FALSE]
    scores<-x$scores[x$scores$program_instance_id==a$program_instance_id & x$scores$column %in% samples$column,,drop=FALSE]
    s_check(identical(scores$column,samples$column),"selected original score column alignment differs")
    values<-suppressWarnings(as.numeric(scores$TotalScore));num<-samples$group==d$numerator;den<-samples$group==d$denominator
    n_num<-length(unique(samples$independent_unit_id[num]));n_den<-length(unique(samples$independent_unit_id[den]));n_pairs<-0L
    if(d$method=="PAIRED_T") n_pairs<-sum(vapply(unique(samples$independent_unit_id),function(u)
      sum(samples$independent_unit_id==u & num)==1L && sum(samples$independent_unit_id==u & den)==1L,logical(1)))
    reason<-"";status<-"NOT_ESTIMABLE";estimate<-se<-df<-lower<-upper<-p<-NA_real_;declaration_consistent<-FALSE
    if(a$status!="FROZEN") {status<-"NOT_RUN";reason<-paste0("ANALYSIS_",a$status)}
    else if(any(samples$member_identity_resolved!="TRUE")) reason<-"UNRESOLVED_BIOLOGICAL_MEMBERSHIP"
    else if(any(samples$unit_kind=="POOL")) reason<-"POOLED_SCORE_MODEL_REQUIRES_SEPARATE_QUALIFICATION"
    else if(any(scores$status!="ESTIMATED") || any(!is.finite(values))) reason<-"SELECTED_SCORE_MISSING_NO_SAMPLE_DROP"
    else if(n_num==0L || n_den==0L) reason<-"FROZEN_GROUP_HAS_NO_SELECTED_BIOLOGICAL_UNITS"
    else {
      numerator<-values[num];denominator<-values[den]
      if(d$method=="WELCH_T") {
        if(anyDuplicated(samples$independent_unit_id)) reason<-"REPEATED_UNIT_IN_UNPAIRED_MODEL"
        else {declaration_consistent<-TRUE;if(min(n_num,n_den)<2L) reason<-"ONE_UNIT_DESCRIPTIVE_ONLY"}
      } else {
        units<-sort(unique(samples$independent_unit_id))
        pairs<-vapply(units,function(u) sum(samples$independent_unit_id==u & num)==1L && sum(samples$independent_unit_id==u & den)==1L,logical(1))
        if(!all(pairs)) reason<-"INCOMPLETE_OR_DUPLICATED_FROZEN_PAIR_NO_SAMPLE_DROP"
        else {
          declaration_consistent<-TRUE;n_pairs<-length(units)
          numerator<-setNames(values[num],samples$independent_unit_id[num])[units]
          denominator<-setNames(values[den],samples$independent_unit_id[den])[units]
          if(n_pairs<2L) reason<-"ONE_PAIR_DESCRIPTIVE_ONLY"
        }
      }
      if(!nzchar(reason)) {
        variance<-if(d$method=="PAIRED_T") stats::var(numerator-denominator) else min(stats::var(numerator),stats::var(denominator))
        if(!is.finite(variance) || variance<=0) reason<-"DEGENERATE_VARIANCE_NO_METHOD_FALLBACK"
        else {
          fit<-tryCatch(stats::t.test(numerator,denominator,alternative="two.sided",paired=d$method=="PAIRED_T",var.equal=FALSE,conf.level=.95),
            error=function(e) e)
          if(inherits(fit,"error")) {reason<-"OFFICIAL_T_TEST_NOT_ESTIMABLE";official[[a$analysis_id]]<-list(error=conditionMessage(fit))}
          else {
            calls<-calls+1L;official[[a$analysis_id]]<-fit
            estimate<-mean(numerator)-mean(denominator);se<-unname(fit$stderr);df<-unname(fit$parameter)
            lower<-unname(fit$conf.int[1L]);upper<-unname(fit$conf.int[2L]);p<-fit$p.value
            s_check(all(is.finite(c(estimate,se,df,lower,upper,p))) && se>0 && df>0 && p>=0 && p<=1 && lower<=upper,
              "official contrast returned invalid statistics");status<-"ESTIMATED"
          }
        }
      }
    }
    units_for_precision<-if(d$method=="PAIRED_T") n_pairs else min(n_num,n_den)
    low<-units_for_precision==2L;eligible<-status=="ESTIMATED" && units_for_precision>=d$family_min_units
    prior<-x$config$prior_results_from_original_registry[[a$program_instance_id]]
    parent<-x$config$program_instances[[match(a$program_instance_id,vapply(x$config$program_instances,function(z) z$program_instance_id,character(1)))]]$program_id
    output[[i]]<-data.frame(analysis_id=a$analysis_id,family="B_PRIMARY_STATES",role="CONDITIONAL_EXPLORATORY",estimand_id="E_B_DIS",
      dataset_id=x$config$frozen_recipe$dataset_id,contrast_id=a$contrast_id,program_id=parent,program_instance_id=a$program_instance_id,
      status=status,reason=reason,method=d$method,n_numerator=n_num,n_denominator=n_den,n_pairs=n_pairs,low_precision=low,
      estimate=estimate,se=se,df=df,ci_lower=lower,ci_upper=upper,nominal_p=p,raw_p=if(eligible) p else NA_real_,
      adjustment_p=if(eligible) p else 1,family_p_numerically_eligible=eligible,
      independence_declaration_consistent=declaration_consistent,biological_independence_verified=FALSE,
      disease_interpretation=d$disease_interpretation,disease_definition_scientifically_qualified=FALSE,
      prior_results=prior,formal_authorized=FALSE)
    if(nrow(samples)) selected_rows[[length(selected_rows)+1L]]<-data.frame(analysis_id=a$analysis_id,contrast_id=a$contrast_id,
      program_instance_id=a$program_instance_id,samples,TotalScore=scores$TotalScore,score_status=scores$status,score_reason=scores$reason,
      stringsAsFactors=FALSE,check.names=FALSE)
  }
  selected<-if(length(selected_rows)) do.call(rbind,selected_rows) else data.frame(
    analysis_id=character(),contrast_id=character(),program_instance_id=character(),x$samples[FALSE,,drop=FALSE],TotalScore=character(),score_status=character(),score_reason=character())
  list(results=do.call(rbind,output),selected=selected,official=official,calls=calls)
}

c_main <- function(args) {
  s_check(length(args)==7L,"usage: contrast.R prepared-config samples decisions actual-scores actual-coverage actual-preparation-audit new-output-directory")
  out<-args[7L];s_check(startsWith(out,"/") && out!="/" && !grepl("(^|/)\\.\\.(/|$)",out) && !file.exists(out) && !s_link(out),"new private absolute output required")
  x<-c_load(args[1L],setNames(as.list(args[2:6]),c("samples","decisions","scores","coverage","preparation_audit")))
  result<-c_fit(x)
  s_check(identical(s_sha(x$config_path),x$config_sha) && identical(lapply(x$paths,s_sha),x$hashes),"contrast inputs changed during fitting")
  parent<-dirname(out);s_check(dir.exists(parent) && !s_link(parent),"private existing output parent required")
  ancestors<-parent;while(tail(ancestors,1L)!="/") ancestors<-c(ancestors,dirname(tail(ancestors,1L)))
  s_check(!any(vapply(ancestors,s_link,logical(1))),"symlink output ancestor")
  stage<-tempfile(pattern=".b-state-contrast-stage-",tmpdir=parent);s_check(dir.create(stage),"owned contrast stage creation failed")
  on.exit(if(dir.exists(stage)) unlink(stage,recursive=TRUE),add=TRUE)
  utils::write.table(result$results,file.path(stage,"results.tsv"),sep="\t",quote=FALSE,row.names=FALSE,na="NA")
  utils::write.table(result$selected,file.path(stage,"selected-samples.tsv"),sep="\t",quote=TRUE,qmethod="double",row.names=FALSE,na="NA")
  saveRDS(result$official,file.path(stage,"official.rds"),compress=FALSE)
  names<-c("results.tsv","selected-samples.tsv","official.rds")
  identity<-setNames(lapply(names,function(name) {path<-file.path(stage,name);list(sha256=s_sha(path),bytes=unname(file.info(path)$size))}),names)
  audit<-list(schema_version=1L,protocol_version=x$config$protocol_version,scope=x$config$scope,method="CORE_B_SCORE_CONTRAST",config_sha256=x$config_sha,
    input_sha256=x$hashes,output_identity=identity,software_lock=x$config$frozen_recipe$software_lock,
    method_parameters=x$config$frozen_recipe$method_parameters,prior_results_from_original_registry=x$config$prior_results_from_original_registry,
    official_t_test_calls=result$calls,all_declared_analysis_rows_retained=TRUE,selected_samples_dropped_after_scores=FALSE,
    scientific_approval_verified=FALSE,biological_independence_verified=FALSE,disease_definition_scientifically_qualified=FALSE,
    family_frozen=FALSE,formal_authorized=FALSE,result_viewing_history_reset=FALSE,full_B_PRIMARY_STATES_complete=FALSE)
  jsonlite::write_json(audit,file.path(stage,"audit.json"),auto_unbox=TRUE,pretty=TRUE,na="null",null="null",digits=17)
  s_check(!file.exists(out) && !s_link(out),"output appeared during fitting")
  move<-system2("mv",c("--no-clobber","--no-target-directory","--",shQuote(stage),shQuote(out)),stdout=TRUE,stderr=TRUE)
  s_check(is.null(attr(move,"status")) && !dir.exists(stage) && dir.exists(out),"no-clobber complete contrast publication failed")
  cat(jsonlite::toJSON(list(scope=audit$scope,official_t_test_calls=result$calls,formal_authorized=FALSE),auto_unbox=TRUE),"\n")
}
if(sys.nframe()==0L) tryCatch(c_main(commandArgs(TRUE)),error=function(e) {cat("BLOCKED:",conditionMessage(e),"\n",file=stderr());quit(status=2L)})
