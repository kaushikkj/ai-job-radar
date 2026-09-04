from dataclasses import dataclass
from datetime import datetime


@dataclass
class CollectedJob:
    title: str
    location: str
    url: str
    description: str
    source: str
    posted_at: datetime | None = None
    remote: bool = False
    posted_at_source: str = ""
    company_name: str = ""
