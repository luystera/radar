"""Static configuration: slug aliases, location grouping, source domains.

Nothing here touches the network. The egress policy of the environment the
pipeline runs in decides which of sources/boards.py can actually be used; see
BOARD_HOSTS and the note in sources/boards.py.
"""
from __future__ import annotations

import os

# Company-slug aliases, kept identical to the convention already recorded in
# the artifact database so role ids stay stable across the migration.
ALIASES = {
    "renaissancetechnologies": "rentec", "thecignagroup": "cigna",
    "lseglondonstockexchangegroup": "lseg", "clearclearsecure": "clear",
    "cursoranysphere": "cursor", "dominodatalab": "domino",
    "garnerhealth": "garner", "alticeusaoptimum": "altice",
    "johnshopkinsapl": "jhuapl", "susquehannainternationalgroup": "sig",
    "generaldynamicsmissionsystems": "gdms", "citadelsecurities": "citadelsec",
    "andurilindustries": "anduril", "imctrading": "imc", "akunacapital": "akuna",
    "belvederetrading": "belvedere", "boerboeltrading": "boerboel",
    "chicagotradingcompany": "ctc", "jpmorganchase": "jpmorgan",
    "goldmansachs": "goldman", "appliedmaterials": "amat",
    "appliedintuition": "applint", "northropgrumman": "northrop",
    "analogdevices": "adi", "energysolutions": "energysol",
    "ellipsislabs": "ellipsis",
}

# Group A — NYC metro. Matched case-insensitively as substrings of location.
GROUP_A = (
    "new york", "nyc", "manhattan", "brooklyn", "jersey city", "stamford",
    "greenwich, ct", "westport",
)

# Long Island towns, with road miles from Huntington NY.
LONG_ISLAND = {
    "greenlawn": 3, "melville": 4, "comtech": 4, "cold spring harbor": 5,
    "veeco": 8, "plainview": 8, "farmingdale": 9, "bethpage": 10,
    "edgewood": 10, "hauppauge": 12, "new hyde park": 18, "ronkonkoma": 18,
    "east setauket": 20, "stony brook": 20, "upton": 28, "islandia": 14,
    "bohemia": 16, "westbury": 14, "garden city": 16, "huntington": 0,
}

# Group B — rest of East Coast.
GROUP_B = (
    "philadelphia", "boston", "cambridge, ma", "hartford", "baltimore",
    "washington", "dc", ", nj", "new jersey", "princeton", "morris plains",
    ", pa", ", md", ", ct", ", ma", ", nh", ", de", "upstate",
)

# Hosts whose public board APIs the deterministic clients can read *when the
# running environment's egress policy permits it*. In the Anthropic cloud
# container these answer 403 at the proxy, so the agent reads them with
# WebFetch instead and feeds results back through `radar verify`.
BOARD_HOSTS = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
    "ashby": "api.ashbyhq.com",
}

# Trackers — plain GitHub raw markdown, reachable from code.
TRACKERS = {
    "speedyapply": "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md",
    "vanshb03": "https://raw.githubusercontent.com/vanshb03/New-Grad-2027/dev/README.md",
    "zapplyjobs": "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2027/main/README.md",
}

# Trackers whose date/age column is not trustworthy enough to derive recency.
UNTRUSTED_AGE = {"zapplyjobs", "vanshb03"}

# Sources that publish estimated total comp rather than posting base salary.
ESTIMATED_COMP = {"speedyapply"}

# The artifact the digest is published to. Deliberately NOT hardcoded: this
# repo is public and the URL points at a private page. Set RADAR_ARTIFACT_URL
# in the environment that runs the pipeline.
ARTIFACT_URL = os.environ.get("RADAR_ARTIFACT_URL", "")
