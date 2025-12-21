"""
PediaFlow: Phase 1 Data Dictionary & Variable Definitions
=========================================================
This module defines the entire state space for the Physiological Digital Twin.
It includes Inputs (Doctor), Internal States (Physics Engine), and Outputs (Safety).

NO LOGIC is implemented here. This is purely the definitions of the variables
that will drive the Differential Equations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

# --- 1. ENUMS (Standardizing the Inputs) ---

class IVSetType(Enum):
    MICRO_DRIP = "micro_60_gtt_ml"  # Standard Pediatric Set
    MACRO_DRIP = "macro_20_gtt_ml"  # Standard Adult Set

class ClinicalDiagnosis(Enum):
    SEVERE_DEHYDRATION = "severe_dehydration" # Diarrhea/Vomiting
    SEPTIC_SHOCK = "septic_shock"             # Infection/Sepsis
    DENGUE_SHOCK = "dengue_shock_syndrome"    # Capillary Leak
    SAM_DEHYDRATION = "sam_severe_malnutrition" # Vulnerable State
    UNKNOWN = "undifferentiated_shock"

class FluidType(Enum):
    RL = "ringer_lactate"
    NS = "normal_saline_0.9"
    D5_NS = "dextrose_5_normal_saline"      # For Hypoglycemia Risk
    RESOMAL = "resomal_rehydration_sol"     # For SAM
    PRBC = "packed_red_blood_cells"         # For Severe Anemia
    HALF_STRENGTH = "0.45_normal_saline"    # Maintenance
    COLLOID_ALBUMIN = "albumin_5_percent" # REQUIRED: For Refractory Dengue/Sepsis
    ORS_SOLUTION = "oral_rehydration_solution" # REQUIRED: For bridging IV to Oral

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
    
    # Lab / Dynamic Inputs (Optional but high value)
    current_sodium: float = 140.0 # mEq/L (Critical for Cerebral Edema logic)
    current_glucose: float = 90.0 # mg/dL (Critical for Hypoglycemia check)
    hematocrit_pct: float = 35.0  # % (Critical for Dengue Leak tracking)
    
    # Context
    diagnosis: ClinicalDiagnosis = ClinicalDiagnosis.UNKNOWN
    iv_set_available: IVSetType = IVSetType.MICRO_DRIP

    # REQUIRED FOR DENGUE: To detect "Rising Hct" (Leak Indicator)
    baseline_hematocrit_pct: Optional[float] = None 
    
    # REQUIRED FOR TRANSFUSION: To calculate Volume = Weight * (Target - Current) * 4
    target_hemoglobin_g_dl: Optional[float] = 10.0 
    
    # REQUIRED FOR RENAL: Context for "Is the kidney working or shut down?"
    time_since_last_urine_hours: float = 0.0

    # RESPIRATORY BASELINE
    # Required to trigger "Stop if RR increases by X"
    respiratory_rate_bpm: int

    # LOSS ESTIMATION (The "Third Vector")
    # "How many times has the child vomited/stooled in last 4 hours?"
    # The engine uses this to estimate a ml/hr "Drain Rate"
    ongoing_losses_severity: str # 'NONE', 'MILD', 'SEVERE' (Engine maps this to ml/kg/hr)
    
    # BASELINE ORGAN STATUS
    # Changes the sensitivity of the Safety Alerts
    baseline_hepatomegaly: bool = False # "Is liver already palpable?"
    
    # HEIGHT
    # Useful for accurate BSA (Insensible Loss) and Z-Score
    height_cm: Optional[float] = None

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

    # INSENSIBLE LOSS RATE
    # Skin/Lung evaporation. High in Fever/SAM.
    # Formula: (BSA * TempFactor) / 24h
    insensible_loss_ml_min: float 

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
    
    # FLUID SELECTION LOGIC
    requires_glucose: bool = False     # True if SAM/Hypoglycemia risk
    requires_blood: bool = False       # True if Anemia/Hb thresholds met
    
    alerts: SafetyAlerts
