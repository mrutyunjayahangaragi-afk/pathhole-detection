"""
Matching Repository
===================
Persistence operations for duplicate incident candidate matching, multi-signal scores, and decisions.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import MatchEvaluation, MatchCandidate, MatchDecision, IncidentObservation


class MatchingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_evaluation(self, data: Dict[str, Any]) -> MatchEvaluation:
        """Persists a new duplicate matching evaluation run."""
        evaluation = MatchEvaluation(**data)
        self.session.add(evaluation)
        self.session.flush()
        return evaluation

    def add_candidate(self, data: Dict[str, Any]) -> MatchCandidate:
        """Records an incident candidate considered during duplicate matching."""
        candidate = MatchCandidate(**data)
        self.session.add(candidate)
        self.session.flush()
        return candidate

    def record_decision(self, data: Dict[str, Any]) -> MatchDecision:
        """Records an automated or human match decision."""
        decision = MatchDecision(**data)
        self.session.add(decision)
        self.session.flush()
        return decision

    def create_observation(self, data: Dict[str, Any]) -> IncidentObservation:
        """Links a citizen report or evidence asset to a canonical physical incident."""
        obs = IncidentObservation(**data)
        self.session.add(obs)
        self.session.flush()
        return obs

    def get_candidates_for_report(self, report_id: str) -> List[MatchCandidate]:
        """Retrieves match candidates evaluated for a specific report."""
        return (
            self.session.query(MatchCandidate)
            .join(MatchEvaluation, MatchEvaluation.id == MatchCandidate.match_evaluation_id)
            .filter(MatchEvaluation.source_report_id == report_id)
            .order_by(MatchCandidate.composite_score.desc())
            .all()
        )
