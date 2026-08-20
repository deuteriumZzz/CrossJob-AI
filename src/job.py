from dataclasses import dataclass


@dataclass
class Job:
    role: str = ""
    company: str = ""
    location: str = ""
    link: str = ""
    apply_method: str = ""
    description: str = ""
    source: str = ""
    external_id: str = ""
    salary: str = ""
    company_url: str = ""
