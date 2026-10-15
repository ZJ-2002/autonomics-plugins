"""Real base-R publication fault toys; no singscore computation or node certification."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SCRIPT_SHA256 = '0ccfea285f042f05af15f61dd5de3ef8ff2d924387d8a6d07bf3852eac5a59b2'
PROGRAM = r'''
script <- commandArgs(TRUE)[1]
scenario <- commandArgs(TRUE)[2]
assignment <- function(value, name) is.call(value) && identical(value[[1]],as.name("<-")) && identical(value[[2]],as.name(name))
expressions <- parse(script)
run_definition <- expressions[[which(vapply(expressions,assignment,logical(1),name="run_score"))]]
original <- eval(run_definition[[3]])
outer <- as.list(body(original))[-1]
first <- which(vapply(outer,assignment,logical(1),name="staged"))
catch <- which(vapply(outer,function(value)is.call(value)&&identical(value[[1]],as.name("tryCatch")),logical(1)))
inner <- as.list(outer[[catch]][[2]])[-1]
score <- which(vapply(inner,assignment,logical(1),name="scores"))
stopifnot(length(first)==1L,length(catch)==1L,length(score)==1L)
scope <- new.env(parent=globalenv())
for (expression in expressions) {
 if (is.call(expression) && identical(expression[[1]],as.name("<-")) && is.call(expression[[3]]) &&
     identical(expression[[3]][[1]],as.name("function")) && !identical(expression[[2]],as.name("run_score"))) eval(expression,scope)
}
expected <- parse(text='rank_data <- singscore::rankGenes(expr, tiesMethod = "average", stableGenes = NULL)
simple <- if (length(down_set) == 0) {
 singscore::simpleScore(rank_data, upSet = up_set, centerScore = TRUE, knownDirection = TRUE, dispersionFun = stats::mad)
} else {
 singscore::simpleScore(rank_data, upSet = up_set, downSet = down_set, centerScore = TRUE, knownDirection = TRUE, dispersionFun = stats::mad)
}')
stopifnot(identical(inner[[which(vapply(inner,assignment,logical(1),name="rank_data"))]],expected[[1]]),
 identical(inner[[which(vapply(inner,assignment,logical(1),name="simple"))]],expected[[2]]))
baseline_prefix <- parse(text='staged <- character(); published <- character(); complete <- FALSE
on.exit({unlink(staged);if (!complete) unlink(published)},add=TRUE)')
baseline_tail <- parse(text='staged <- vapply(outputs[1:2],function(path)tempfile(".singscore-",tmpdir=dirname(path)),character(1))
write.table(scores,staged[1],sep="\t",row.names=FALSE,quote=FALSE)
saveRDS(list(rank_data=rank_data,simple=simple,scores=scores),staged[2])
for(position in seq_along(staged)){
 if(!suppressWarnings(file.link(staged[position],outputs[position])))stop("Fresh output publication failed; existing artifacts are never replaced",call.=FALSE)
 published<-c(published,outputs[position])
}
complete<-TRUE;0L')
run_case <- function(mode, baseline=FALSE) {
 directory <- tempfile("singscore-publication-toy-")
 stopifnot(dir.create(directory))
 on.exit(unlink(directory,recursive=TRUE),add=TRUE)
 local_scope <- new.env(parent=scope)
 parents <- rep(directory,3)
 if(mode=="quoted-multiple-parents") {
  parents<-file.path(directory,c("first ' ;$", "second space", "log"));stopifnot(all(vapply(parents,dir.create,logical(1))))
 }
 local_scope$outputs<-file.path(parents,c("scores.tsv","scores.RDS","run.log"))
 do.call(Sys.setenv,as.list(setNames(c(rep("unused-toy-input",3),local_scope$outputs),
  c(paste0("AUTONOMICS_INPUT",0:2),paste0("AUTONOMICS_OUTPUT",0:2)))))
 local_scope$scores<-data.frame(sample=c("toy1","toy2"),TotalScore=c(.25,-.125),group=c("a","b"),stringsAsFactors=FALSE)
 local_scope$rank_data<-matrix(1:4,2,dimnames=list(c("toy-g1","toy-g2"),c("toy1","toy2")))
 local_scope$simple<-data.frame(TotalScore=c(.25,-.125),row.names=c("toy1","toy2"))
 count<-0L;foreign_stage<-NULL;foreign_child<-NULL
 local_scope$message<-function(...) {
  text<-paste0(...,collapse="");error<<-sub("^ERROR: ","",text)
  base::message(...)
 }
 local_scope$sink<-function(file,...) {
  if(missing(file))return(base::sink())
  base::sink(file,...)
  if(mode=="foreign-log-after-sink") {
   stopifnot(file.rename(local_scope$outputs[3],paste0(local_scope$outputs[3],".owned-old")))
   writeLines("FOREIGN_LOG_KEEP",local_scope$outputs[3])
  }
  invisible(NULL)
 }
 local_scope$file.link<-function(from,to) {
  count<<-count+1L
  if(mode=="fail-second" && count==2L)return(FALSE)
  if(grepl("then-fail",mode,fixed=TRUE) && count==2L)return(FALSE)
  if(mode=="foreign-at-link" && count==1L)writeLines("FOREIGN_KEEP",to)
  if(mode=="replace-staged" && count==1L){unlink(from);writeLines("FOREIGN_STAGE",from);foreign_stage<<-from}
  answer<-base::file.link(from,to)
  if(isTRUE(answer) && count==1L && mode %in% c("replace-first-then-fail","same-inode-first-then-fail","same-inode-first-success")) {
   if(mode=="replace-first-then-fail")unlink(to)
   writeLines("FOREIGN_KEEP",to)
  }
  if(isTRUE(answer) && count==2L && mode=="late-first-change")writeLines("FOREIGN_KEEP",local_scope$outputs[1])
  if(isTRUE(answer) && count==1L && mode=="foreign-stage-child") {
   foreign_child<<-file.path(dirname(from),"foreign-child");writeLines("KEEP_CHILD",foreign_child)
  }
  answer
 }
 local_scope$file<-function(description="",open="",...) {
  if(mode=="stage-parent-replaced-before-writer" && open=="wx" && endsWith(description,"scores.tsv")) {
   parent<-dirname(description);stopifnot(file.rename(parent,paste0(parent,"-moved")),dir.create(parent))
   writeLines("FOREIGN_STAGE",description);foreign_stage<<-description
  }
  if(mode=="foreign-before-writer" && open=="wx" && endsWith(description,"scores.tsv")) {
   writeLines("FOREIGN_STAGE",description);foreign_stage<<-description
  }
  base::file(description,open=open,...)
 }
 if(mode=="hash-unavailable") scope$system2<-function(command,...) {
  arguments<-list(...)
  if(identical(command,"/usr/bin/sha256sum") && endsWith(arguments$stdin,"scores.tsv"))return(character())
  base::system2(command,...)
 }
 if(mode=="stage-parent-before-approval") {
  original_fact<-scope$singscore_publication_file_identity
  changed<-FALSE
  scope$singscore_publication_file_identity<-function(filename) {
   if(!changed && endsWith(filename,"scores.tsv")) {
    changed<<-TRUE;parent<-dirname(filename)
    stopifnot(file.rename(parent,paste0(parent,"-moved")),dir.create(parent))
    writeLines("FOREIGN_STAGE",filename);foreign_stage<<-filename
   }
   original_fact(filename)
  }
 }
 method<-function(){}
 if(baseline) {
  body(method)<-as.call(c(list(as.name("{")),as.list(baseline_prefix),as.list(baseline_tail)))
 } else {
  actual_outer<-outer
  actual_outer[[catch]][[2]]<-as.call(c(list(as.name("{")),inner[(score+1L):length(inner)]))
  body(method)<-as.call(c(list(as.name("{")),actual_outer))
 }
 environment(method)<-local_scope
 error<-NULL
 connections_before<-showConnections(all=TRUE)
 answer<-suppressWarnings(tryCatch(method(),error=function(value){error<<-conditionMessage(value);NULL}))
 stopifnot(identical(showConnections(all=TRUE),connections_before))
 if(!is.null(error))cat("ACTUAL_COMPONENT_REFUSAL",error,"\n")
 exists<-file.exists(local_scope$outputs[1:2])
 if(baseline) {
  if(grepl("then-fail",mode,fixed=TRUE))stopifnot(!is.null(error),!exists[1])
  else stopifnot(is.null(error),identical(readLines(local_scope$outputs[1]),"FOREIGN_KEEP"))
  cat("BASELINE_DEFECT_CONFIRMED",mode,"\n")
 } else if(mode %in% c("control","quoted-multiple-parents","foreign-stage-child")) {
  stopifnot(is.null(error),identical(answer,0L),all(exists),identical(readRDS(local_scope$outputs[2]),
    list(rank_data=local_scope$rank_data,simple=local_scope$simple,scores=local_scope$scores)))
  reference<-file.path(directory,"reference.tsv")
  write.table(local_scope$scores,reference,sep="\t",row.names=FALSE,quote=FALSE)
  stopifnot(identical(readBin(reference,"raw",n=file.info(reference)$size),
    readBin(local_scope$outputs[1],"raw",n=file.info(local_scope$outputs[1])$size)))
  baseline_rds<-file.path(directory,"baseline.RDS")
  saveRDS(list(rank_data=local_scope$rank_data,simple=local_scope$simple,scores=local_scope$scores),baseline_rds)
  stopifnot(identical(readRDS(local_scope$outputs[2]),readRDS(baseline_rds)))
  stopifnot(identical(readBin(local_scope$outputs[2],"raw",n=2L),as.raw(c(31L,139L))))
  if(mode=="foreign-stage-child")stopifnot(file.exists(foreign_child),identical(readLines(foreign_child),"KEEP_CHILD"))
  cat("FIXED_COMPONENT_PASS",mode,"\n")
 } else {
  stopifnot(!is.null(error))
  if(mode=="foreign-log-after-sink") {
   stopifnot(!identical(answer,0L),identical(readLines(local_scope$outputs[3]),"FOREIGN_LOG_KEEP"),!any(exists))
  } else if(mode %in% c("replace-first-then-fail","same-inode-first-then-fail","same-inode-first-success","late-first-change","foreign-at-link")) {
   stopifnot(exists[1],identical(readLines(local_scope$outputs[1]),"FOREIGN_KEEP"),!exists[2])
  } else if(mode=="replace-staged") {
   stopifnot(file.exists(foreign_stage),identical(readLines(foreign_stage),"FOREIGN_STAGE"))
  } else if(mode %in% c("foreign-before-writer","stage-parent-replaced-before-writer","stage-parent-before-approval")) {
   stopifnot(file.exists(foreign_stage),identical(readLines(foreign_stage),"FOREIGN_STAGE"),!any(exists))
  } else stopifnot(!any(exists))
  diagnostic<-switch(mode,
   "replace-first-then-fail"="Published score artifact identity or contents changed",
   "same-inode-first-then-fail"="Published score artifact identity or contents changed",
   "same-inode-first-success"="Published score artifact identity or contents changed",
   "late-first-change"="Score artifact changed before publication completed",
   "replace-staged"="Published score artifact identity or contents changed",
   "foreign-before-writer"="cannot open the connection",
   "stage-parent-replaced-before-writer"="cannot open the connection",
   "stage-parent-before-approval"="Staged score artifact changed before publication",
   "foreign-log-after-sink"="Run log identity or finalized contents changed; foreign log preserved",
   "hash-unavailable"="Complete staged score identity unavailable",
   "Fresh output publication failed")
  stopifnot(grepl(diagnostic,error,fixed=TRUE))
  cat("FIXED_SPECIFIC_REFUSAL",mode,error,"\n")
 }
}
if(scenario=="baseline") {
 for(mode in c("replace-first-then-fail","same-inode-first-then-fail","same-inode-first-success"))run_case(mode,TRUE)
} else run_case(scenario)
'''


class SingscorePublicationOwnershipTests(unittest.TestCase):
    def component(self, scenario):
        interpreter = shutil.which('Rscript')
        self.assertIsNotNone(interpreter, 'Existing locked Rscript is required; no silent missing-runtime pass')
        result = subprocess.run([interpreter, '--vanilla', '-', str(ROOT / 'plugins/singscore/scripts/singscore.sh'), scenario],
            input=PROGRAM, capture_output=True, text=True, timeout=60,
            env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('BASELINE_DEFECT_CONFIRMED' if scenario == 'baseline' else
            'FIXED_COMPONENT_PASS' if scenario in ['control', 'quoted-multiple-parents', 'foreign-stage-child'] else
            'FIXED_SPECIFIC_REFUSAL', result.stdout)

    def test_baseline_actual_component_reproduces_three_confirmed_defects(self):
        self.component('baseline')

    def test_control_preserves_entire_rds_object_tsv_bytes_and_scoring_call_ast(self):
        self.component('control')

    def test_quoted_multiple_parent_paths_preserve_writer_objects(self):
        self.component('quoted-multiple-parents')

    def test_replaced_destination_is_preserved_on_later_link_failure(self):
        self.component('replace-first-then-fail')

    def test_same_inode_foreign_change_is_preserved_on_later_link_failure(self):
        self.component('same-inode-first-then-fail')

    def test_same_inode_foreign_change_cannot_be_a_silent_success(self):
        self.component('same-inode-first-success')

    def test_final_sweep_rejects_late_first_destination_change(self):
        self.component('late-first-change')

    def test_ordinary_link_failure_rolls_back_only_owned_outputs(self):
        self.component('fail-second')

    def test_foreign_destination_appearing_at_link_is_never_removed(self):
        self.component('foreign-at-link')

    def test_staged_replacement_is_detected_and_foreign_contents_preserved(self):
        self.component('replace-staged')

    def test_exclusive_writer_does_not_truncate_a_foreign_stage_file(self):
        self.component('foreign-before-writer')

    def test_private_stage_cleanup_never_recursively_deletes_foreign_children(self):
        self.component('foreign-stage-child')

    def test_replaced_stage_parent_cannot_supply_a_foreign_writer_target(self):
        self.component('stage-parent-replaced-before-writer')

    def test_stage_parent_substitution_before_hash_cannot_publish_or_delete_foreign(self):
        self.component('stage-parent-before-approval')

    def test_failed_sha_observation_cannot_authorize_publication_or_deletion(self):
        self.component('hash-unavailable')

    def test_actual_outer_sink_log_replacement_is_preserved_and_refused(self):
        self.component('foreign-log-after-sink')


if __name__ == '__main__':
    unittest.main()
