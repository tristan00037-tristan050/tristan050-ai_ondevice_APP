"""Device-local company learning pipeline.

The package implements folder connect -> digest-only indexing -> evidence-bound
understanding -> learning_event.v1 CANDIDATE handoff. It never runs training and
never persists raw folder paths or chunk text.
"""

from .folder_ingest import IngestResult, ingest_folder
from .handoff import CompanyLearningHandoffResult, create_company_learning_candidate
from .job_store import CompanyLearningJob, CompanyLearningJobStore
from .understanding import build_understanding

__all__ = [
    "CompanyLearningHandoffResult",
    "CompanyLearningJob",
    "CompanyLearningJobStore",
    "IngestResult",
    "build_understanding",
    "create_company_learning_candidate",
    "ingest_folder",
]
