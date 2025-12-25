"""
PediaFlow: Phase 1 Data Dictionary & Variable Definitions
=========================================================
This module defines the entire state space for the Physiological Digital Twin.
It includes Inputs (Doctor), Internal States (Physics Engine), and Outputs (Safety).

NO LOGIC is implemented here. This is purely the definitions of the variables
that will drive the Differential Equations.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import List, Optional
from datetime import datetime
from constants import VERSION, FluidType 

class CriticalConditionError(ValueError):
    """Raised when vitals indicate immediate life threat requiring ICU, not calculation."""
    pass

class DataTypeError(TypeError):
    """Raised when inputs are wrong python types (str instead of float)."""
    pass

# --- 1. ENUMS (Standardizing the Inputs) ---

class IVSetType(Enum):
    """Values represent drops per mL (gtt/mL)"""
    MICRO_DRIP = 60  
    MACRO_DRIP = 20  

class ClinicalDiagnosis(Enum):
    SEVERE_DEHYDRATION = "severe_dehydration" # Diarrhea/Vomiting
    SEPTIC_SHOCK = "septic_shock"             # Infection/Sepsis
    DENGUE_SHOCK = "dengue_shock_syndrome"    # Capillary Leak
    SAM_DEHYDRATION = "sam_severe_malnutrition" # Vulnerable State
    UNKNOWN = "undifferentiated_shock"
    SEVERE_ANEMIA = "severe_anemia"

class ShockSeverity(Enum):
    COMPENSATED = "compensated_shock"     # BP Normal, HR High
    HYPOTENSIVE = "decompensated_shock"   # BP Low
    IRREVERSIBLE = "irreversible_shock"   # Organ Failure

class OngoingLosses(Enum):
    NONE = 0
    MILD = 5      # 5 ml/kg/hr
    MODERATE = 7  # 7 ml/kg/hr (Added per feedback)
    SEVERE = 10   # 10 ml/kg/hr

@dataclass
class CalculationWarnings:
    """Tracks non-critical issues that the doctor must know."""
    hct_autocorrected: Optional[tuple] = None  # (original, corrected)
    albumin_estimated: bool = False
    missing_optimal_inputs: List[str] = field(default_factory=list)
    sam_shock_conflict: bool = False

from datetime import datetime

@dataclass
class AuditLog:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    action: str = "twin_creation"
    inputs_hash: int = 0
    model_version: str = VERSION

@dataclass
class ValidationResult:
    """Standardized response format for API/UI."""
    success: bool
    patient: Optional['PatientInput']
    physics_params: Optional['PhysiologicalParams']
    initial_state: Optional['SimulationState']
    errors: List[str]
    warnings: CalculationWarnings
    confidence_score: float = 1.0
    audit_log: Optional[AuditLog] = None

# --- 2. INPUT LAYER (What the Doctor Enters) ---

@dataclass
class PatientInput:
    """
    The raw data collected at the bedside.
    Includes 'Vulnerability Indicators' specific to India.
    """
    # Demographics
    age_months: int          # CRITICAL: Determines Renal/Heart Maturity
    weight_kg: float         # CRITICAL: Baseline for dosage volume
    sex: str                 # 'M' or 'F' (Minor impact on TBW)
    
    # Critical 'Vulnerability' Inputs
    muac_cm: float           # Malnutrition Proxy (<11.5cm = SAM)
    temp_celsius: float      # <36.0 = Hypothermia (Masked Shock risk)
    hemoglobin_g_dl: float   # <5.0 = Severe Anemia (Viscosity/Dilution risk)
    
    # Clinical Vitals (Snapshot at T=0)
    systolic_bp: int         # mmHg
    heart_rate: int          # bpm
    capillary_refill_sec: int # >3s = Shock
    sp_o2_percent: int       # Oxygen Saturation
    # RESPIRATORY BASELINE
    # Required to trigger "Stop if RR increases by X"
    respiratory_rate_bpm: int

    diastolic_bp: Optional[int] = None # [NEW] Optional for better MAP
    lactate_mmol_l: Optional[float] = None 
    # Illness Timeline (Critical for Dengue Sigma)
    illness_day: Optional[int] = None 

    # REQUIRED FOR DENGUE: To detect "Rising Hct" (Leak Indicator)
    baseline_hematocrit_pct: Optional[float] = None 
    plasma_albumin_g_dl: Optional[float] = None 
    platelet_count: Optional[int] = None
    
    # Lab / Dynamic Inputs (Optional but high value)
    current_sodium: float = 140.0 # mEq/L (Critical for Cerebral Edema logic)
    current_glucose: float = 90.0 # mg/dL (Critical for Hypoglycemia check)
    hematocrit_pct: float = 35.0  # % (Critical for Dengue Leak tracking)
    
    # Context
    diagnosis: ClinicalDiagnosis = ClinicalDiagnosis.UNKNOWN
    iv_set_available: IVSetType = IVSetType.MICRO_DRIP
    
    # REQUIRED FOR TRANSFUSION: To calculate Volume = Weight * (Target - Current) * 4
    target_hemoglobin_g_dl: Optional[float] = 10.0 
    
    # REQUIRED FOR RENAL: Context for "Is the kidney working or shut down?"
    time_since_last_urine_hours: float = 0.0

    # LOSS ESTIMATION (The "Third Vector")
    # "How many times has the child vomited/stooled in last 4 hours?"
    # The engine uses this to estimate a ml/hr "Drain Rate"
    ongoing_losses_severity: OngoingLosses = OngoingLosses.NONE
    
    # BASELINE ORGAN STATUS
    # Changes the sensitivity of the Safety Alerts
    baseline_hepatomegaly: bool = False # "Is liver already palpable?"
    
    # HEIGHT
    # Useful for accurate BSA (Insensible Loss) and Z-Score
    height_cm: Optional[float] = None

    def __post_init__(self):
        """
        Validates inputs against Age-Specific Norms and Type Safety.
        """

        # [NEW] 1. Type Safety (prevent string math crashes)
        numeric_fields = [
            'age_months', 'weight_kg', 'muac_cm', 'temp_celsius', 
            'hemoglobin_g_dl', 'systolic_bp', 'heart_rate', 
            'sp_o2_percent', 'respiratory_rate_bpm'
        ]
        for field in numeric_fields:
            val = getattr(self, field)
            if not isinstance(val, (int, float)):
                raise DataTypeError(f"Field '{field}' must be numeric, got {type(val)}")

        # [NEW] 2. Clinical Hard Stops (Safety First)
        if self.systolic_bp < 40:
            raise CriticalConditionError("BP <40 mmHg: Immediate ICU escalation required. Calculator locked.")
        if self.sp_o2_percent < 80:
            raise CriticalConditionError("SpO2 <80%: Priority is Oxygenation, not Fluid Calculation.")
        if self.hemoglobin_g_dl < 4.0:
            raise CriticalConditionError("Hb <4.0 g/dL: Immediate Transfusion required before Crystalloids.")

        # [NEW] Validate Sex
        if self.sex not in ['M', 'F']:
             raise ValueError("Sex must be 'M' or 'F'")

        # [NEW] Validate Diastolic if present
        if self.diastolic_bp is not None:
            if not (20 <= self.diastolic_bp <= 150):
                raise ValueError(f"Invalid Diastolic BP: {self.diastolic_bp}")
            if self.diastolic_bp >= self.systolic_bp:
                raise ValueError("Diastolic BP must be less than Systolic BP")

        # 1. Age-Specific Respiratory Rate Validation (WHO Guidelines)
        # We don't crash the app if it's high (patient might be sick!),
        # but we sanity check for impossible values based on age.
        if self.illness_day is not None and not isinstance(self.illness_day, int):
            raise DataTypeError(f"illness_day must be integer, got {type(self.illness_day)}")
            
        # Define physiologic limits (Lower Limit, Upper Limit)
        if self.age_months < 2:
            rr_min, rr_max = 30, 100 # Neonates breathe fast
        elif self.age_months < 12:
            rr_min, rr_max = 20, 80
        elif self.age_months < 60:
            rr_min, rr_max = 15, 60
        else:
            rr_min, rr_max = 10, 50 # Older children
            
        if not (rr_min <= self.respiratory_rate_bpm <= rr_max * 1.5):
            pass # This is now a "Soft Warning" logic in the Engine, not a crash here.
            
        # Hard Stop only for physiological impossibility (e.g., RR > 200)
        if self.respiratory_rate_bpm < 0 or self.respiratory_rate_bpm > 200:
             raise ValueError(f"RR {self.respiratory_rate_bpm} is physically impossible")

        # 2. Illness Day Validation
        # If Dengue is suspected, Illness Day is MANDATORY logic
        if self.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            if self.illness_day is None:
                raise ValueError("Illness Day is mandatory for Dengue diagnosis")
            if not (1 <= self.illness_day <= 14):
                raise ValueError(f"Invalid Illness Day: {self.illness_day}")

        # 3. Standard Range Checks
        if not (0 <= self.age_months <= 216): raise ValueError(f"Invalid age: {self.age_months}")
        if not (0.5 <= self.weight_kg <= 100.0): raise ValueError(f"Invalid weight: {self.weight_kg}")
        if not (5.0 <= self.muac_cm <= 35.0): raise ValueError(f"Invalid MUAC: {self.muac_cm}")
        if not (25.0 <= self.temp_celsius <= 42.0): raise ValueError(f"Invalid Temp: {self.temp_celsius}")
        if not (1.0 <= self.hemoglobin_g_dl <= 25.0): raise ValueError(f"Invalid Hb: {self.hemoglobin_g_dl}")
        if not (30 <= self.systolic_bp <= 240): raise ValueError(f"Invalid BP: {self.systolic_bp}")
        if not (30 <= self.heart_rate <= 300): raise ValueError(f"Invalid HR: {self.heart_rate}")
        if not (10 <= self.respiratory_rate_bpm <= 120): raise ValueError(f"Invalid RR: {self.respiratory_rate_bpm}")

        # 4. Consistency Checks
        # BMI Validation
        if self.height_cm:
            bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
            if not (10.0 <= bmi <= 35.0):
                raise ValueError(f"Impossible BMI: {bmi:.1f}. Check Height/Weight.")

        # 5. Protocol Conflicts (SAM + Shock)
        is_shock = self.diagnosis in [ClinicalDiagnosis.DENGUE_SHOCK, ClinicalDiagnosis.SEPTIC_SHOCK]
        is_sam = self.muac_cm < 11.5
        if is_sam and is_shock:
            # Valid scenario, but requires logic override in Engine
            pass # Engine handles this via Contractility penalty

# --- 3. INTERNAL PHYSICS CONSTANTS (The "Twin" Configuration) ---

@dataclass
class PhysiologicalParams:
    """
    These are calculated ONCE at initialization based on Inputs.
    They represent the 'Laws of Physics' for THIS specific child.
    """
    # Compartment Sizing (The Tanks)
    tbw_fraction: float      # Total Body Water % (0.6 to 0.8)
    v_blood_normal_l: float  # Normal Blood Volume (Liters)
    v_inter_normal_l: float  # Normal Interstitial Volume (Liters)
    
    # Heart Mechanics (Frank-Starling Curve)
    cardiac_contractility: float # 0.0 to 1.0. (0.5 for SAM).
    heart_stiffness_k: float     # Pediatric hearts are stiffer (higher K)
    
    # Vascular Physics
    svr_resistance: float        # Systemic Vascular Resistance (High in Hypothermia)
    capillary_filtration_k: float # 'K_f': How fast fluid leaks (High in Dengue/Sepsis)
    blood_viscosity_eta: float   # Derived from Hb. Low in Anemia.
    
    # Tissue Mechanics
    tissue_compliance_factor: float # Low in SAM (Floppy tissues = High Edema risk)
    
    # Renal (The Drain)
    renal_maturity_factor: float # 0.3 (Neonate) to 1.0 (Adult). Scales Urine Output.

    # REQUIRED FOR FRANK-STARLING "PLATEAU" LOGIC
    # The ceiling of the heart's output (Reduced in SAM/Heart Failure)
    max_cardiac_output_l_min: float 
    
    # REQUIRED FOR CVP CALCULATION (The "Back Pressure" equation)
    # cvp = volume / venous_compliance
    venous_compliance_ml_mmhg: float 
    
    # REQUIRED FOR INTRACELLULAR SHIFT (Cellular Hydration)
    # Controls flow between V_interstitial <-> V_intracellular
    osmotic_conductance_k: float 
    
    # REQUIRED FOR LYMPHATIC DRAINAGE
    # The natural "overflow drain" from tissues back to veins
    lymphatic_drainage_capacity_ml_min: float

    # ADDITION: For SAM, this is >1.0. For normal, 1.0.
    # Shifts the equilibrium point of water movement into cells.
    intracellular_sodium_bias: float 

    # ADDITION: Calculated safe targets (e.g., MAP > 55 for infant)
    target_map_mmhg: float
    target_heart_rate_upper_limit: int
    target_respiratory_rate_limit: int

    # INSENSIBLE LOSS RATE
    # Skin/Lung evaporation. High in Fever/SAM.
    # Formula: (BSA * TempFactor) / 24h
    insensible_loss_ml_min: float 

    # ONCOTIC PRESSURE PHYSICS (Starling Forces)
    # The "Pull" keeping fluid in vessels. Critical for Dengue/Sepsis.
    plasma_oncotic_pressure_mmhg: float
    reflection_coefficient_sigma: float  # 0.9 (Tight) vs 0.3 (Leaky)

    # GLUCOSE DYNAMICS
    # Metabolic burn rate to predict hypoglycemia
    glucose_utilization_mg_kg_min: float 

    # Captures how "stiff" the vessels are (SAM/Cold = High Sensitivity)
    afterload_sensitivity: float 
    
    # Captures the baseline capillary state (Shock vs Normal)
    baseline_capillary_pressure_mmhg: float
    
    # Captures the "Sweet Spot" volume for this specific child's heart
    optimal_preload_ml: float 

    weight_kg: float  # Required for glucose metabolic burn calculation
    interstitial_compliance_ml_mmhg: float # Replaces magic number 100.0

    target_cvp_mmhg: float

    # CONFIDENCE INTERVALS
    # Used to widen safety margins in output
    albumin_uncertainty_g_dl: float = 0.5 

# --- 4. DYNAMIC STATE (The Simulation Variables) ---

@dataclass
class SimulationState:
    """
    The variables that change continuously over time (T -> T+1).
    The ODE Solver updates these.
    """
    time_minutes: float
    
    # Fluid Volumes (The Integrals)
    v_blood_current_l: float
    v_interstitial_current_l: float
    v_intracellular_current_l: float
    
    # Pressures (Derived from Volumes)
    map_mmHg: float                 # Mean Arterial Pressure
    cvp_mmHg: float                 # Central Venous Pressure (Back pressure)
    pcwp_mmHg: float                # Pulmonary Capillary Wedge Pressure (Lung risk)
    p_interstitial_mmHg: float      # Tissue Turgor Pressure
    
    # Flux Rates (The Derivatives)
    q_infusion_ml_min: float        # Flow IN (From IV drip)
    q_leak_ml_min: float            # Flow OUT (Capillary Leak)
    q_urine_ml_min: float           # Flow OUT (Kidneys)
    q_lymph_ml_min: float          # Fluid returning from Tissue -> Blood
    q_osmotic_shift_ml_min: float  # Fluid moving Tissue <-> Cells

    # CUMULATIVE SAFETY COUNTERS (Integrators)
    total_volume_infused_ml: float      # To trigger TACO Alert (>20ml/kg)
    total_sodium_load_meq: float        # To trigger Cerebral Edema Alert (>12mEq/L/24h)
    
    # DERIVED CLINICAL METRIC
    current_hematocrit_dynamic: float   # To track Hemoconcentration in real-time

    # Track real-time weight changes due to fluid accumulation
    current_weight_dynamic_kg: float

    # NON-RENAL OUTPUTS
    # These subtract from the total volume available for BP
    q_ongoing_loss_ml_min: float  # Diarrhea/Vomiting rate
    q_insensible_loss_ml_min: float # Sweat/Respiration rate

    # METABOLIC TRACKING
    current_glucose_mg_dl: float
    
    # BOLUS SAFETY TRACKING
    cumulative_bolus_count: int
    time_since_last_bolus_min: float

    current_sodium: float = 140.0 # Default start value

# --- 5. OUTPUT LAYER (The Actionable Results) ---

@dataclass
class SafetyAlerts:
    """
    Boolean flags and warning strings for the UI.
    """
    risk_pulmonary_edema: bool = False  # If V_interstitial rises too fast
    risk_volume_overload: bool = False  # If Total Vol > Safe Limit
    risk_cerebral_edema: bool = False   # If Sodium shifts > 10mEq/24h
    risk_hypoglycemia: bool = False     # If Glucose < 54 & using NS
    hydrocortisone_needed: bool = False  # lactate>6 post-40ml/kg
    risk_ketoacidosis: bool = False      # D5NS + lactate>6
    
    # Specific Context Warnings
    sam_heart_warning: bool = False     # "Weak Heart Detected - Rate Limiting Active"
    anemia_dilution_warning: bool = False # "Hb Critically Low - Consider Blood"
    dengue_leak_warning: bool = False   # "Active Capillary Leak Detected"

@dataclass
class EngineOutput:
    """
    The final instructions displayed to the doctor.
    """
    # 1. The Prescription
    recommended_fluid: FluidType
    bolus_volume_ml: int
    infusion_duration_min: int
    
    # 2. The Hardware Instruction (The "Killer Feature")
    iv_set_used: str          # e.g., "Micro-Drip (60 drops/ml)"
    flow_rate_ml_hr: int      # e.g., 120 ml/hr
    drops_per_minute: int     # e.g., 120 dpm
    seconds_per_drop: float   # e.g., 0.5 sec (Visual Metronome)
    
    # 3. The Prediction (What will happen?)
    predicted_bp_rise: int    # "Expect SBP to rise by 10 mmHg"
    stop_trigger_heart_rate: int       # e.g. "Stop if HR > 180" (Fluid Overload)
    stop_trigger_respiratory_rate: int # e.g. "Stop if RR > 60" (Pulmonary Edema)
    stop_trigger_liver_span_increase: bool # True for "Check Hepatomegaly"

    # HARD SAFETY LIMITS
    max_safe_infusion_rate_ml_hr: int  # e.g., "Do not exceed 40ml/hr"
    max_allowed_bolus_volume_ml: int   # e.g., "Stop after 150ml"
    
    alerts: SafetyAlerts
    
    # FLUID SELECTION LOGIC
    requires_glucose: bool = False     # True if SAM/Hypoglycemia risk
    requires_blood: bool = False       # True if Anemia/Hb thresholds met

    # [NEW] Summary for Quick Read
    human_readable_summary: str = "" 
    # e.g. "Give 100ml RL over 1 hr. Stop if RR > 55."

    trajectory: List[dict] = field(default_factory=list) 
