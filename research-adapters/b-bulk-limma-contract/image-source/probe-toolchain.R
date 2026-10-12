# Fixed tiny C/C++/Fortran compile probe, never a statistical method.
check<-function(ok,msg) if(!isTRUE(ok)) stop(msg,call.=FALSE)
args<-commandArgs(trailingOnly=TRUE);check(length(args)==1L,"exclusive probe receipt path required")
output<-args[[1L]];link<-Sys.readlink(output)
check(startsWith(output,"/") && !file.exists(output) && (is.na(link) || !nzchar(link)),"new absolute toolchain receipt required")
check(identical(as.character(getRversion()),"4.6.1"),"controlled R version differs")
tools<-Sys.which(c("gcc","g++","gfortran","make","sha256sum"))
check(all(nzchar(tools)),"C/C++/Fortran/make tooling unavailable in pinned base")
version<-lapply(tools,function(tool) {
 value<-system2(tool,"--version",stdout=TRUE,stderr=TRUE)
 check(is.null(attr(value,"status")) && length(value)>0L,"compiler version probe failed");value[[1L]]
})
sha<-function(path) {
 value<-system2("sha256sum",c("--",shQuote(path)),stdout=TRUE,stderr=TRUE)
 check(is.null(attr(value,"status")) && length(value)==1L && grepl("^[0-9a-f]{64}  ",value),"tool hashing failed")
 substr(value,1L,64L)
}
scratch<-tempfile("b-bulk-toolchain-");check(dir.create(scratch),"private compiler scratch unavailable")
sources<-list(c="int main(void) { return 0; }",cpp="int main() { return 0; }",
              f90=c("program probe","implicit none","integer :: i","i=1","if (i /= 1) stop 1","end program probe"))
compilers<-c(c="gcc",cpp="g++",f90="gfortran");compiled<-list()
for(kind in names(sources)) {
 source<-file.path(scratch,paste0("probe.",kind));binary<-file.path(scratch,paste0("probe-",kind))
 writeLines(sources[[kind]],source,useBytes=TRUE)
 status<-system2(tools[[compilers[[kind]]]],c(shQuote(source),"-o",shQuote(binary)),stdout=TRUE,stderr=TRUE)
 check(is.null(attr(status,"status")) && file.exists(binary),paste("small compile/link probe failed:",kind))
 run<-system2(binary,stdout=TRUE,stderr=TRUE);check(is.null(attr(run,"status")),paste("small executable probe failed:",kind))
 compiled[[kind]]<-list(source_sha256=sha(source),binary_sha256=sha(binary),exit_code=0L)
}
check(requireNamespace("jsonlite",quietly=TRUE),"measured base JSON namespace unavailable")
record<-list(scope="BASE_C_CPP_FORTRAN_FIXED_PROBE_NOT_PACKAGE_INSTALL_OR_METHOD_ACCEPTANCE",R=as.character(getRversion()),
 tools=as.list(tools),tool_versions=version,tool_sha256=lapply(tools,sha),compiled=compiled,
 R_CC=system2(file.path(R.home("bin"),"R"),c("CMD","config","CC"),stdout=TRUE),
 R_CXX=system2(file.path(R.home("bin"),"R"),c("CMD","config","CXX"),stdout=TRUE),
 R_FC=system2(file.path(R.home("bin"),"R"),c("CMD","config","FC"),stdout=TRUE),
 method_executed=FALSE,formal_authorized=FALSE)
jsonlite::write_json(record,output,auto_unbox=TRUE,pretty=TRUE)
unlink(scratch,recursive=TRUE)
