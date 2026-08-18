from typing import Literal

RootType = Literal["models", "input", "output"]

# Enrichment level constants
ENRICHMENT_STUB = 0  # Fast scan: path, size, mtime only
ENRICHMENT_METADATA = 1  # Metadata extracted (safetensors header, mime type)
ENRICHMENT_HASHED = 2  # Hash computed (blake3)
