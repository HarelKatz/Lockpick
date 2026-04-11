"""Graph endpoints — compute pivot graph on demand."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from routers.deps import get_op_or_404
from schemas import GraphResponse, PathFinderRequest, PathFinderResponse
from services.graph_builder import build_graph, expand_host
from services.pivot_analysis import find_paths

router = APIRouter(tags=["graph"])


@router.get("/ops/{op_id}/graph", response_model=GraphResponse)
def get_graph(
    op_id: str,
    host_ids: Optional[str] = Query(default=None, description="Comma-separated host IDs"),
    db: Session = Depends(get_db),
) -> GraphResponse:
    """Return nodes and edges for an operation, optionally filtered to a host subset."""
    get_op_or_404(op_id, db)
    parsed_ids = (
        [h.strip() for h in host_ids.split(",") if h.strip()]
        if host_ids
        else None
    )
    return build_graph(db, op_id, parsed_ids)


@router.get("/ops/{op_id}/hosts/{host_id}/expand", response_model=GraphResponse)
def expand_host_endpoint(
    op_id: str,
    host_id: str,
    evidence_type: str = Query(default="all", description="all|key_match|connection_log|indicator"),
    db: Session = Depends(get_db),
) -> GraphResponse:
    """Return the target host plus all adjacent hosts and edges, filtered by evidence type."""
    get_op_or_404(op_id, db)
    return expand_host(db, op_id, host_id, evidence_type)


@router.post("/ops/{op_id}/graph/paths", response_model=PathFinderResponse)
def find_graph_paths(
    op_id: str,
    body: PathFinderRequest,
    db: Session = Depends(get_db),
) -> PathFinderResponse:
    """BFS/DFS pivot path finder. Max depth 8, max 30 paths returned."""
    get_op_or_404(op_id, db)
    return find_paths(db, op_id, body)
