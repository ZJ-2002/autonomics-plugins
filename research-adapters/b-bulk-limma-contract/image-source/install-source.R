# Fixed offline source installer; run only during root-authorized image build.
check<-function(ok,msg) if(!isTRUE(ok)) stop(msg,call.=FALSE)
args<-commandArgs(trailingOnly=TRUE);check(length(args)==1L,"build context path required")
root<-args[[1L]];lock<-read.delim(file.path(root,"package-lock.tsv"),colClasses="character",check.names=FALSE,na.strings=NULL)
check(identical(as.character(getRversion()),"4.6.1"),"controlled R version differs")
lib<-"/opt/b-bulk-library";dir.create(lib,recursive=TRUE,showWarnings=FALSE)
.libPaths(c(lib,"/opt/epi-library",.Library))
for(name in c("grDevices","graphics","stats","utils","methods")) {
 check(identical(as.character(packageVersion(name)),"4.6.1"),paste("R base package differs:",name))
 check(requireNamespace(name,quietly=TRUE),paste("base namespace unavailable:",name))
}
sha<-function(path) {
 result<-system2("sha256sum",c("--",shQuote(path)),stdout=TRUE,stderr=TRUE)
 check(is.null(attr(result,"status")) && length(result)==1L && grepl("^[0-9a-f]{64}  ",result),"file hashing failed")
 substr(result,1L,64L)
}
for(i in seq_len(nrow(lock))) {
 row<-lock[i,,drop=FALSE];archive<-file.path(root,"archives",row$archive)
 check(identical(sha(archive),row$sha256),"source archive bytes differ")
 status<-system2(file.path(R.home("bin"),"R"),c("CMD","INSTALL","--no-multiarch",paste0("--library=",shQuote(lib)),shQuote(archive)))
 check(identical(status,0L),paste("offline source installation failed:",row$name))
 check(identical(as.character(packageVersion(row$name,lib.loc=lib)),row$version),paste("installed version differs:",row$name))
 description<-packageDescription(row$name,lib.loc=lib)
 for(field in c("Depends","Imports","LinkingTo")) {
  actual<-description[[field]];if(is.null(actual)) actual<-""
  check(identical(gsub("\\s+"," ",trimws(actual)),row[[tolower(field)]]),paste("installed dependency differs:",row$name,field))
 }
}
for(name in lock$name) check(requireNamespace(name,quietly=TRUE),paste("installed namespace unavailable:",name))
version<-system2("mv","--version",stdout=TRUE,stderr=TRUE)
check(length(version)>0L && grepl("^mv \\(GNU coreutils\\) ",version[[1L]]),"GNU no-clobber publisher required")
record<-list(scope="B_BULK_IMAGE_RUNTIME_MEASUREMENT_NOT_METHOD_OR_G0_ACCEPTANCE",R=as.character(getRversion()),
 packages=setNames(lapply(c(lock$name,"stats"),function(name) as.character(packageVersion(name))),c(lock$name,"stats")),
 core_sha256=sha("/opt/b-bulk/bulk-limma.R"),design_entry_sha256=sha("/opt/b-bulk/run-design.R"),
 limma_entry_sha256=sha("/opt/b-bulk/run-limma.R"),launcher_sha256=sha("/opt/b-bulk/bin/Rscript-vanilla"),
 package_lock_sha256=sha(file.path(root,"package-lock.tsv")),source_lock_sha256=sha(file.path(root,"SOURCE_LOCK.json")),
 Rscript_sha256=sha(unname(Sys.which("Rscript"))),mv_sha256=sha(unname(Sys.which("mv"))),
 image_qualified=FALSE,method_acceptance_verified=FALSE,scientific_G0_granted=FALSE,formal_authorized=FALSE)
jsonlite::write_json(record,file.path(root,"IMAGE_RUNTIME.json"),auto_unbox=TRUE,digits=NA,pretty=TRUE)
