from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class Poll:
    id: int
    society_id: int
    created_by: Optional[int] = None
    title: str = ""
    description: Optional[str] = None
    status: str = "active"
    choice_count: int = 2
    choice_1: str = ""
    choice_2: str = ""
    choice_3: Optional[str] = None
    choice_4: Optional[str] = None
    choice_5: Optional[str] = None
    results_announced_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    reminder_sent_at: Optional[datetime] = None
    total_votes: int = 0
    has_voted: bool = False
    user_vote: Optional[int] = None
    vote_counts: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    def choices(self) -> list[str]:
        result = [self.choice_1, self.choice_2]
        if self.choice_3:
            result.append(self.choice_3)
        if self.choice_4:
            result.append(self.choice_4)
        if self.choice_5:
            result.append(self.choice_5)
        return result

    def is_active(self) -> bool:
        return self.status == "active"

    def results_visible(self) -> bool:
        return self.results_announced_at is not None


@dataclass
class PollVote:
    id: int
    poll_id: int
    user_id: int
    choice: int
    cast_at: Optional[datetime] = None

    def to_dict(self):
        return asdict(self)
