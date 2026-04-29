from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class KR23MetricResponse(BaseModel):
    total_discounts: int
    justified_discounts: int
    justification_rate: float
    
    model_config = ConfigDict(from_attributes=True)

class KR24MetricResponse(BaseModel):
    total_snapshots: int
    invariant_snapshots: int
    invariance_rate: float

    model_config = ConfigDict(from_attributes=True)

class KR25MetricResponse(BaseModel):
    total_hybrid_quotes: int
    accurate_hybrid_quotes: int
    precision_rate: float

    model_config = ConfigDict(from_attributes=True)

class KR27MetricResponse(BaseModel):
    total_ready_transitions: int
    transitions_with_checklist: int
    compliance_rate: float

    model_config = ConfigDict(from_attributes=True)

class DashboardMetricsResponse(BaseModel):
    kr23: KR23MetricResponse
    kr24: KR24MetricResponse
    kr25: KR25MetricResponse
    kr27: KR27MetricResponse

    model_config = ConfigDict(from_attributes=True)