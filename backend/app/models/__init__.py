# Import all models here so Alembic's autogenerate sees them.
from app.models.company import Company  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.job_criteria import JobCriteria  # noqa: F401
from app.models.setup_conversation import SetupConversation  # noqa: F401
from app.models.candidate import Candidate  # noqa: F401
from app.models.application import Application  # noqa: F401
from app.models.cv_chunk import CvChunk  # noqa: F401
from app.models.job_chunk import JobChunk  # noqa: F401
from app.models.interview_session import InterviewSession  # noqa: F401
from app.models.interview_message import InterviewMessage  # noqa: F401
from app.models.evaluation import Evaluation  # noqa: F401
