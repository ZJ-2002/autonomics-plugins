# hashutil

本地文件哈希锚表。补齐主计划 §26.1 的缺口：引擎 `FileRef` 只记录
size+mtime，复现包需要内容寻址的 blake3/sha256 锚表（快照导出对账、
外部数据集投递自验）。

## 节点

| kind | 输入 | 输出 | 说明 |
|---|---|---|---|
| `file_hashes` | FileSet（任意文件） | `hashes.tsv`、`file_hashes.log` | 流式分块哈希，逐文件一行 |

参数：`algos`（string_array，默认 `["sha256","blake3"]`，取值仅限
sha256/blake3）、`chunk_mb`（默认 8）。大文件不整读入内存。

## 布局

```text
hashutil/
├── manifest.toml
├── scripts/file_hashes.py
├── Dockerfile          # 镜像 provenance（共享 biotools-py，见 _images/）
└── README.md
```

镜像：`localhost/autonomics/biotools-py@sha256:21e14c1582a9d4c261c0a23a11864293313ee2b49b9b7d85bcabc89210b48c7e`
（构建树在上级 `_images/biotools-py/`，本目录 Dockerfile 为副本）。

## 口径

- 输出列：`path`（相对 FileSet 根）、`bytes`、`algo`、`digest`。
  同一文件多算法 = 多行，不拼列。
- blake3 走 `blake3-py` 官方绑定（非 hashlib），摘要与 `b3sum` 一致。
- log 自锚：记录参数与文件数；摘要表本身可再被 file_hashes 处理形成
  递归锚（§26.1 的锚表-锚）。

## 冒烟记录

host `sha256sum` 逐字节比对一致；863080 字节 GSE 矩阵文件哈希自验通过。
