# Self-contained synthetic data; no biological observations.
options(stringsAsFactors=FALSE)
set.seed(20261016)
out <- Sys.getenv("METHOD_FIXTURE_ROOT")
n <- 2000L
samples <- paste0("s",seq_len(8L))
mu <- exp(runif(n,log(25),log(3000)))
dispersion <- 0.12 + 10/mu
counts <- sapply(seq_len(8L), function(j) rnbinom(n,mu=mu,size=1/dispersion))
# Apply a fixed effect to a predeclared subset before any fitting.
for (j in 5:8) counts[1:200,j] <- rnbinom(200L,mu=mu[1:200]*2,size=1/dispersion[1:200])
counts <- rbind(all_zero=rep(0L,8L), counts)
rownames(counts) <- c("all_zero",paste0("g",seq_len(n)))
colnames(counts) <- samples
counts["g2000",] <- c(10000000,50,55,60,45,70,40,52)
write.table(data.frame(gene_id=rownames(counts),counts,check.names=FALSE),file.path(out,"counts.tsv"),sep="\t",quote=TRUE,row.names=FALSE)
metadata <- data.frame(sample_id=samples,condition=rep(c("ctrl","case"),each=4))
write.table(metadata,file.path(out,"metadata.tsv"),sep="\t",quote=TRUE,row.names=FALSE)
write.table(metadata[c(8,2,6,4,1,7,3,5),],file.path(out,"shuffled.tsv"),sep="\t",quote=TRUE,row.names=FALSE)
