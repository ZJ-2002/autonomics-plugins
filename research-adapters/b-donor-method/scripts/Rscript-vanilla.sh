#!/bin/sh
# Fixed image executable, not an agent-selectable script node. The engine
# inserts its loaded manifest script after this executable. Flags belong here.
exec /usr/local/bin/Rscript --vanilla "$@"
