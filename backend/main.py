# main.py

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import Data Models & Logic
from models import (
    EngineOutput, 
    SafetyAlerts,
    ClinicalDiagnosis, 
    OngoingLosses, 
    FluidType, 
    IVSetType,
    PatientInput,       # <--- Added
    CalculationWarnings
)
from app import generate_prescription
from core_physics import PediaFlowPhysicsEngin

# --- 1. CONFIGURATION & LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pediaflow-api")

app = FastAPI(
    title="PediaFlow API",
    version="1.0.0",
    description="Physiological Digital Twin for Pediatric Shock Management. \n\n"
                "**WARNING**: Decision Support Tool Only. Not for autonomous clinical use.",
    contact={"name": "Clinical Validation Team", "email": "safety@pediaflow.org"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Tighten this in real production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "active", "message": "PediaFlow API is running successfully!"}

@app.get("/health")
def health_check():
    """K8s/AWS Health Probe"""
    return {"status": "active", "version": "1.0.0", "module": "pediaflow-kinetic-engine"}

# --- 2. STRICT INPUT SCHEMA (The Guardrails) ---
class PatientRequest(BaseModel):
    # Demographics with hard physiological limits
    age_months: int = Field(..., ge=0, le=216, description="Age in months (0-18y)")
    weight_kg: float = Field(..., gt=0.5, le=120.0, description="Weight in kg")
    sex: str = Field(..., pattern="^(M|F)$", description="'M' or 'F'")
    muac_cm: float = Field(..., gt=5.0, le=40.0, description="Mid-Upper Arm Circumference")
    height_cm: Optional[float] = Field(None, gt=20.0, le=250.0, description="Height for BSA calculation")
    
    # Critical Vitals
    temp_celsius: float = Field(..., gt=25.0, le=45.0, description="Core Temperature")
    systolic_bp: int = Field(..., gt=30, le=250, description="Systolic Blood Pressure")
    diastolic_bp: Optional[int] = Field(None, gt=10, le=200)
    heart_rate: int = Field(..., gt=30, le=300, description="Heart Rate BPM")
    respiratory_rate_bpm: int = Field(..., gt=0, le=150)
    sp_o2_percent: int = Field(..., ge=0, le=100)
    capillary_refill_sec: int = Field(..., ge=0, le=20)
    
    # Labs & Context (Using Enums for strict validation)
    hemoglobin_g_dl: float = Field(..., gt=1.0, le=25.0)
    current_sodium: Optional[float] = Field(140.0, gt=100.0, le=180.0)
    current_glucose: Optional[float] = Field(90.0, gt=10.0, le=1000.0)
    hematocrit_pct: Optional[float] = Field(35.0, gt=5.0, le=80.0)
    lactate_mmol_l: Optional[float] = Field(None, ge=0.0, le=30.0, description="Blood lactate level")
    plasma_albumin_g_dl: Optional[float] = Field(None, ge=1.0, le=6.0)
    platelet_count: Optional[int] = Field(None, ge=1000, le=1000000)
    baseline_hematocrit_pct: Optional[float] = Field(None, gt=5.0, le=80.0)
    target_hemoglobin_g_dl: Optional[float] = Field(10.0, ge=4.0, le=20.0)
    time_since_last_urine_hours: float = Field(0.0, ge=0.0, le=72.0)
    baseline_hepatomegaly: bool = Field(False)
    
    # Auto-maps strings to Enums (e.g., "septic_shock" -> ClinicalDiagnosis.SEPTIC_SHOCK)
    diagnosis: ClinicalDiagnosis = Field(default=ClinicalDiagnosis.UNKNOWN)
    ongoing_losses_severity: OngoingLosses = Field(default=OngoingLosses.NONE)
    iv_set_available: IVSetType = Field(default=IVSetType.MICRO_DRIP)
    
    illness_day: Optional[int] = Field(None, ge=1, le=30, description="Required for Dengue")
    
    # Audit trail
    request_timestamp: Optional[datetime] = Field(default_factory=datetime.now)

    class Config:
        # Document an example for Swagger UI
        json_schema_extra = {
            "example": {
                "age_months": 12, "weight_kg": 10.0, "sex": "M", "muac_cm": 14.0,
                "temp_celsius": 38.5, "hemoglobin_g_dl": 11.0, "systolic_bp": 85,
                "heart_rate": 150, "capillary_refill_sec": 3, "sp_o2_percent": 96,
                "respiratory_rate_bpm": 40, "diagnosis": "septic_shock",
                "current_glucose": 85.0
            }
        }

# --- 3. EXPLICIT RESPONSE SCHEMA (The Contract) ---
# We define a Pydantic model mirroring EngineOutput to generate proper API docs
class PrescriptionResponse(BaseModel):
    recommended_fluid: FluidType
    bolus_volume_ml: int
    infusion_duration_min: int
    flow_rate_ml_hr: int
    drops_per_minute: int
    seconds_per_drop: float
    iv_set_used: str
    
    # Safety
    max_safe_infusion_rate_ml_hr: int
    max_allowed_bolus_volume_ml: int
    alerts: SafetyAlerts  # Pydantic handles nested Dataclasses automatically!
    
    # Predictions
    predicted_bp_rise: int
    stop_trigger_heart_rate: int
    stop_trigger_respiratory_rate: int
    
    # UX
    human_readable_summary: str
    trajectory: List[dict]
    generated_at: datetime = Field(default_factory=datetime.now)

# 1. Define the Input for the Simulation
class SimulationRequest(BaseModel):
    patient: PatientRequest  # The child
    fluid_type: str          # What you want to give (e.g. "normal_saline")
    volume_ml: int           # How much (e.g. 500)
    duration_min: int        # How fast (e.g. 30)

class SimulationResponse(BaseModel):
    summary: dict            # Start BP, End BP, Safety Alerts
    graph_data: List[dict]   # Time-series data for the chart

# --- 4. ENDPOINTS ---

@app.post("/prescribe", response_model=PrescriptionResponse)
async def get_prescription(patient: PatientRequest):
    """
    Generates a pediatric fluid resuscitation prescription based on the 
    PediaFlow Physiological Digital Twin engine.
    """
    try:
        logger.info(f"Processing prescription for Age: {patient.age_months}m, Wt: {patient.weight_kg}kg")
        
        # 1. Convert Pydantic model to dict (preserving Enums)
        # We exclude None/Defaults to let the Engine handle internal logic if needed
        patient_data = patient.dict() 
        if 'request_timestamp' in patient_data:
            del patient_data['request_timestamp']
        
        # 2. Run the Core Engine
        # The engine expects the 'PatientInput' structure which matches our schema
        engine_output: EngineOutput = generate_prescription(patient_data)
        
        # 3. Convert Engine Output to API Response
        # Pydantic is smart enough to map the EngineOutput dataclass to our Response model
        return engine_output

    except ValueError as e:
        # These are Logic/Validation errors from the Engine (e.g. "BP too low for calc")
        logger.warning(f"Clinical Validation Error: {str(e)}")
        raise HTTPException(status_code=422, detail=f"Clinical Validation Error: {str(e)}")
        
    except Exception as e:
        # These are unexpected crashes
        logger.error(f"Internal Engine Failure: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Physiological Engine Error")

@app.post("/simulate", response_model=SimulationResponse)
def simulate_outcome(request: SimulationRequest):
    """
    Predicts the future: 'What happens if I do X?'
    Returns time-series data for graphing.
    """
    # 1. Convert API Request -> Internal Model
    patient_data = request.patient.dict()
    patient = PatientInput(**patient_data)
    
    # 2. Initialize Physics
    warnings = CalculationWarnings()
    params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
    state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)
    
    # 3. Run Simulation with History Enabled
    fluid_enum = FluidType(request.fluid_type)
    
    result = PediaFlowPhysicsEngine.run_simulation(
        initial_state=state,
        params=params,
        fluid=fluid_enum,
        volume_ml=request.volume_ml,
        duration_min=request.duration_min,
        return_series=True # Tells engine to record history
    )
    
    return {
        "summary": {
            "bp_start": int(state.map_mmHg),
            "bp_end": int(result['final_state'].map_mmHg),
            "safety_alerts": result['triggers']
        },
        "graph_data": result['trajectory'] # The JSON for your frontend charts
    }

@app.get("/health")
def health_check():
    """K8s/AWS Health Probe"""
    return {"status": "active", "version": "1.0.0", "module": "pediaflow-kinetic-engine"}
