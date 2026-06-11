from dataclasses import dataclass, field
from urllib.parse import urlparse

import yaml


@dataclass
class SourceRegistry:
    tier0: list[str] = field(default_factory=list)
    tier1: list[str] = field(default_factory=list)
    tier2: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str = "sources.yaml") -> "SourceRegistry":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            tier0=data.get("tier_0_factcheckers", []),
            tier1=data.get("tier_1_primarie", []),
            tier2=data.get("tier_2_stampa", []),
            blacklist=data.get("blacklist", []),
        )

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def _matches(self, url: str, domains: list[str]) -> bool:
        d = self._domain(url)
        return any(d == dom or d.endswith("." + dom) for dom in domains)

    def tier_of(self, url: str) -> int:
        for tier, domains in enumerate([self.tier0, self.tier1, self.tier2]):
            if self._matches(url, domains):
                return tier
        return 3

    def is_blacklisted(self, url: str) -> bool:
        return self._matches(url, self.blacklist)

    def trusted_domains(self) -> list[str]:
        return self.tier1 + self.tier2
