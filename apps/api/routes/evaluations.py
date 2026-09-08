from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from database.db import get_db
from database.models import EvaluationRun
from evaluation.runner import run_evaluation_suite

router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])

@router.post("/run", status_code=status.HTTP_201_CREATED)
def trigger_evaluations(db: Session = Depends(get_db)):
    """
    Executes the golden evaluation suite and logs the metrics to the DB.
    """
    try:
        results = run_evaluation_suite()
        return results
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation suite failed: {str(e)}"
        )

@router.get("")
def list_evaluation_runs(db: Session = Depends(get_db)):
    """
    Lists all evaluation run records sorted by date.
    """
    runs = db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "dataset": r.dataset,
            "model": r.model,
            "metrics": r.metrics,
            "created_at": r.created_at
        } for r in runs
    ]
