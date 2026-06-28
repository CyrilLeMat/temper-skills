"""LicenseQuery — features for OSS license-compatibility assessment.

The plan's flagship "moat" domain (§8): fully public, low-stakes, genuinely hard
combinatorics — the verdict depends on the *interaction* of license × linking ×
distribution, not a flat lookup. Closed feature space, so the loop converges.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

License = Literal[
    "MIT", "BSD-3-Clause", "Apache-2.0",
    "LGPL-3.0", "MPL-2.0",
    "GPL-2.0", "GPL-3.0", "AGPL-3.0",
    "proprietary",
]


class LicenseQuery(BaseModel):
    project_license: License            # what you ship YOUR work under
    dependency_license: License         # the license of the dependency you're pulling in
    linking: Literal["static", "dynamic", "none"]   # none = separate process / mere aggregation
    distributing: bool = False          # shipping the combined work, vs internal use only
    modified_dependency: bool = False   # did you modify the dependency's source
