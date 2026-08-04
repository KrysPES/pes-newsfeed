"""One module per source. Each exposes SOURCE metadata and collect(fetcher, ctx)."""

from . import boe
from . import bls
from . import cftc
from . import clocks
from . import ecb
from . import eia_ngs
from . import eia_steo
from . import eia_wpsr
from . import fed
from . import ons

# Order here is the order rows are gathered in. It has no effect on the output
# file, which is sorted by date then title.
SOURCES = [
    boe,
    ecb,
    fed,
    ons,
    bls,
    eia_ngs,
    eia_wpsr,
    eia_steo,
    cftc,
    clocks,
]

BY_ID = {module.SOURCE["id"]: module for module in SOURCES}
