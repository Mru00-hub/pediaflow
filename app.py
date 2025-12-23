# --- METADATA & COMPLIANCE ---
__version__ = "1.0.0"
__model_date__ = "2025-12-22"
__validation_status__ = "Clinical validation pending"
__iap_guideline_version = "IAP 2023 Shock Guidelines"
__who_fluid_version = "WHO 2022 Pocketbook"

MEDICAL_DISCLAIMER = """
⚠️ DECISION SUPPORT TOOL - NOT A PRESCRIPTION
• Final responsibility: Treating physician
• Not a substitute for clinical judgment
• Offline calculator - no real-time monitoring
"""

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
    
class AGE_CONSTANTS:
    # Age (months): (Min RR, Max RR)
    RR_LIMITS = {0: (30,100), 12: (20,80), 60: (15,60), 216: (10,50)}

class PHYSICS_CONSTANTS:
    MINUTES_PER_DAY = 1440.0
    NEONATE_RENAL_MATURITY_BASE = 0.3
    RENAL_MATURATION_RATE_PER_MONTH = 0.029 # (1.0 - 0.3) / 24 months
    
    # Compartment Ratios
    NEONATE_TBW = 0.80
    INFANT_TBW = 0.70
    CHILD_TBW = 0.60
    SAM_HYDRATION_OFFSET = 0.05 # +5% water for SAM

class ClinicalDiagnosis(Enum):
    SEVERE_DEHYDRATION = "severe_dehydration" # Diarrhea/Vomiting
    SEPTIC_SHOCK = "septic_shock"             # Infection/Sepsis
    DENGUE_SHOCK = "dengue_shock_syndrome"    # Capillary Leak
    SAM_DEHYDRATION = "sam_severe_malnutrition" # Vulnerable State
    UNKNOWN = "undifferentiated_shock"

class ShockSeverity(Enum):
    COMPENSATED = "compensated_shock"     # BP Normal, HR High
    HYPOTENSIVE = "decompensated_shock"   # BP Low
    IRREVERSIBLE = "irreversible_shock"   # Organ Failure

class FluidType(Enum):
    RL = "ringer_lactate"
    NS = "normal_saline_0.9"
    D5_NS = "dextrose_5_normal_saline"      # For Hypoglycemia Risk
    RESOMAL = "resomal_rehydration_sol"     # For SAM
    PRBC = "packed_red_blood_cells"         # For Severe Anemia
    HALF_STRENGTH = "0.45_normal_saline"    # Maintenance
    COLLOID_ALBUMIN = "albumin_5_percent" # REQUIRED: For Refractory Dengue/Sepsis
    ORS_SOLUTION = "oral_rehydration_solution" # REQUIRED: For bridging IV to Oral

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
    model_version: str = __version__

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
    
    # Lab / Dynamic Inputs (Optional but high value)
    current_sodium: float = 140.0 # mEq/L (Critical for Cerebral Edema logic)
    current_glucose: float = 90.0 # mg/dL (Critical for Hypoglycemia check)
    hematocrit_pct: float = 35.0  # % (Critical for Dengue Leak tracking)
    
    # Context
    diagnosis: ClinicalDiagnosis = ClinicalDiagnosis.UNKNOWN
    iv_set_available: IVSetType = IVSetType.MICRO_DRIP

    # Illness Timeline (Critical for Dengue Sigma)
    illness_day: Optional[int] = None 

    # REQUIRED FOR DENGUE: To detect "Rising Hct" (Leak Indicator)
    baseline_hematocrit_pct: Optional[float] = None 
    plasma_albumin_g_dl: Optional[float] = None 
    platelet_count: Optional[int] = None
    lactate_mmol_l: Optional[float] = None
    
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

import math

@dataclass
class FluidProperties:
    name: str
    sodium_meq_l: float
    glucose_g_l: float
    oncotic_pressure_mmhg: float  # The "Pull" force
    vol_distribution_intravascular: float  # How much stays in veins immediately?
    
    # Critical for specific logic
    is_colloid: bool = False

class FLUID_LIBRARY:
    """
    The Pharmacopoeia of Fluids. 
    Defines how different fluids behave physically.
    """
    SPECS = {
        FluidType.RL: FluidProperties(
            name="Ringer Lactate", 
            sodium_meq_l=130, glucose_g_l=0, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.25 # Crystalloid: 1/4 stays, 3/4 leaks
        ),
        FluidType.NS: FluidProperties(
            name="Normal Saline", 
            sodium_meq_l=154, glucose_g_l=0, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.25
        ),
        FluidType.D5_NS: FluidProperties(
            name="D5 Normal Saline", 
            sodium_meq_l=154, glucose_g_l=50, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.20 # Glucose metabolizes -> free water -> cells
        ),
        FluidType.COLLOID_ALBUMIN: FluidProperties(
            name="Albumin 5%", 
            sodium_meq_l=145, glucose_g_l=0, oncotic_pressure_mmhg=20.0, # High Pull
            vol_distribution_intravascular=1.0, # Stays in vessel
            is_colloid=True
        ),
        FluidType.PRBC: FluidProperties(
            name="Packed Red Blood Cells",
            sodium_meq_l=140, glucose_g_l=0, oncotic_pressure_mmhg=25.0,
            vol_distribution_intravascular=1.0,
            is_colloid=True
        )
    }

    @staticmethod
    def get(fluid_enum: FluidType) -> FluidProperties:
        return FLUID_LIBRARY.SPECS.get(fluid_enum, FLUID_LIBRARY.SPECS[FluidType.RL])

class PediaFlowPhysicsEngine:
    """
    The Mathematical Core.
    Translates Clinical Inputs -> Physiological Parameters -> Initial State.
    """

    @staticmethod
    def _calculate_bsa(weight_kg: float, height_cm: Optional[float]) -> float:
        """
        Calculates Body Surface Area (m²) using Mosteller formula.
        Falls back to weight-based approximation if height is missing.
        """
        if weight_kg <= 0: return 0.1
        if height_cm is not None and isinstance(height_cm, (int, float)) and height_cm > 0:
            return math.sqrt((weight_kg * height_cm) / 3600)
        else:
            # Weight-based approximation
            return (4 * weight_kg + 7) / (weight_kg + 90)

    @staticmethod
    def _calculate_compartment_volumes(input: PatientInput) -> dict:
        """
        Determines the size of the 'Tanks' (Blood, Tissue, Cells).
        Logic: Adapts to Age and Malnutrition (SAM).
        """
        # 1. Base Ratios (Age-based)
        if input.age_months < 1:
            tbw_ratio = PHYSICS_CONSTANTS.NEONATE_TBW
            ecf_ratio = 0.45
        elif input.age_months < 12:
            tbw_ratio = PHYSICS_CONSTANTS.INFANT_TBW
            ecf_ratio = 0.30
        else:
            tbw_ratio = PHYSICS_CONSTANTS.CHILD_TBW
            ecf_ratio = 0.25

        if input.muac_cm < 11.5:
            tbw_ratio += PHYSICS_CONSTANTS.SAM_HYDRATION_OFFSET
            ecf_ratio += PHYSICS_CONSTANTS.SAM_HYDRATION_OFFSET

        # Calculate Derived ICF Ratio (Conservation of Mass)
        icf_ratio = max(tbw_ratio - ecf_ratio, 0.3) 

        # Calculate Actual Volume
        v_intracellular = input.weight_kg * icf_ratio

        # 3. Calculate Volumes (Liters)
        total_water = input.weight_kg * tbw_ratio
        ecf_total = input.weight_kg * ecf_ratio
        
        # Partition ECF into Intravascular (Blood) and Interstitial
        # Neonates/SAM have higher plasma volume relative to weight
        plasma_fraction = 0.25 # Standard approximation (1/4 of ECF)
        
        v_blood = ecf_total * plasma_fraction
        v_interstitial = ecf_total * (1 - plasma_fraction)
        
        return {
            "tbw_fraction": tbw_ratio,
            "v_blood": v_blood,
            "v_interstitial": v_interstitial,
            "v_intracellular": v_intracellular,
            "icf_ratio": icf_ratio
        }

    @staticmethod
    def _calculate_hemodynamics(input: PatientInput) -> dict:
        """
        Calculates SVR using Pediatric Lookup Tables and nonlinear viscosity.
        """
        # 1. Contractility (The Pump Strength)
        # Baseline = 1.0. SAM/Sepsis reduces it.
        contractility = 1.0
        
        if input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION or input.muac_cm < 11.5:
            contractility *= 0.5  # The "Flabby Heart" penalty
        
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            contractility *= 0.7  # Septic myocardial depression

        # 2. Viscosity 
        # Using Poiseuille's approximation: (Hct/45)^2.5
        # Prevents explosion at low Hct
        hct = input.hematocrit_pct
        if hct < 20.0:
            # Linear approx for severe anemia
            viscosity = 0.5 + (0.02 * hct)
        else:
            # Poiseuille approx
            viscosity = (hct / 45.0) ** 2.5
        
        # Clamp values to prevent mathematical explosion or division by zero
        # Floor: 0.7 (Water-like)
        # Ceiling: 3.0 (Severe Polycythemia sludge - prevents SVR overflow)
        viscosity = max(0.7, min(viscosity, 3.0))
        
        # 3. SVR - Dimensional Correctness
        # Using Age-Based Norms (dynes-sec-cm-5)
        if input.age_months < 1:
            base_svr = 1800.0
        elif input.age_months < 12:
            base_svr = 1400.0
        else:
            base_svr = 1000.0
            
        # Inverse Scaling: Larger child = Lower SVR
        # size_factor > 1 for small babies (Inc Resistance), < 1 for big kids (Dec Resistance)
        svr_scaling_factor = (10.0 / input.weight_kg) ** 0.5
        base_svr = base_svr * svr_scaling_factor

        # Temp Correction
        temp_factor = 1.0
        if input.temp_celsius < 36.0:
            temp_factor = 1.5
        elif input.temp_celsius > 38.5:
            temp_factor = 0.8
            
        svr = base_svr * viscosity * temp_factor

        return {
            "contractility": contractility,
            "svr": svr,
            "viscosity": viscosity
        }

    @staticmethod
    def _calculate_safe_rr_limit(age_months: int, baseline_rr: int) -> int:
        """
        Calculates the Respiratory Rate Safety Stop Limit.
        Logic: Stop if RR rises > 20% from baseline OR exceeds age-specific severe threshold.
        """
        # WHO Severe Thresholds
        if age_months < 2: severe_limit = 60
        elif age_months < 12: severe_limit = 50
        elif age_months < 60: severe_limit = 40
        else: severe_limit = 30
        
        if baseline_rr > severe_limit:
            # Already sick - stop if RR increases by 15%
            return int(baseline_rr * 1.15)
        else:
            # Normal baseline - stop at absolute threshold
            return severe_limit + 10

    @staticmethod
    def _calculate_renal_function(age_months: int, time_since_urine: float) -> float:
        """
        Calculates Renal Maturity Factor (0.0 to 1.0).
        """
        if age_months >= 24:
            maturity = 1.0
        
        # Linear maturation from 0.3 (birth) to 1.0 (2 years)
        # Slope = 0.7 / 24 = ~0.029 per month
        else: 
            maturity = PHYSICS_CONSTANTS.NEONATE_RENAL_MATURITY_BASE + \
                       (PHYSICS_CONSTANTS.RENAL_MATURATION_RATE_PER_MONTH * age_months)
            maturity = min(maturity, 1.0)
        
        # AKI Shutdown Logic
        if time_since_urine > 6.0:
            maturity *= 0.1 # Shutdown
        elif time_since_urine > 4.0:
            maturity *= 0.5 # Oliguria
            
        return maturity

    @staticmethod
    def _calculate_insensible_loss(input: PatientInput, bsa: float) -> float:
        """
        Calculates evaporation from skin/lungs (ml/min).
        """
        # Baseline: ~400 ml/m2/day
        daily_loss_ml = 400 * bsa
        
        # Fever Correction: +12% per degree > 38
        if input.temp_celsius > 38.0:
            excess_temp = input.temp_celsius - 38.0
            daily_loss_ml *= (1 + (0.12 * excess_temp))
            
        # Tachypnea Correction: +10% if RR > 50 (Work of breathing)
        if input.respiratory_rate_bpm > 50:
            daily_loss_ml *= 1.10
            
        return daily_loss_ml / PHYSICS_CONSTANTS.MINUTES_PER_DAY

    @staticmethod
    def create_digital_twin(data: dict) -> ValidationResult:
        """
        SAFE FACTORY: The main entry point for the UI/API.
        Handles validation, logic, confidence scoring, and error formatting.
        """
        warnings = CalculationWarnings()
        audit = None
        
        try:
            # 1. Pre-Validation / Input Sanitization
            # Check Hct/Hb consistency before object creation to log warning
            if 'hemoglobin_g_dl' in data and 'hematocrit_pct' in data:
                hb = float(data['hemoglobin_g_dl'])
                hct = float(data['hematocrit_pct'])
                if abs(hct - (hb * 3)) > 15:
                    warnings.hct_autocorrected = (hct, hb * 3)

            # 2. Create Patient Input (Validates types and ranges)
            patient = PatientInput(**data)

            # 3. Calculate Confidence Score
            # Base 60%, +10% per optional category
            score = 0.6
            if patient.plasma_albumin_g_dl: score += 0.15
            if patient.lactate_mmol_l: score += 0.1
            if patient.platelet_count: score += 0.1
            if patient.height_cm: score += 0.05
            confidence = min(score, 1.0)

            # 4. Input Quality Checks
            if not patient.plasma_albumin_g_dl: 
                warnings.missing_optimal_inputs.append("Albumin")
            if not patient.lactate_mmol_l: 
                warnings.missing_optimal_inputs.append("Lactate")
                
            if patient.muac_cm < 11.5 and patient.diagnosis in [ClinicalDiagnosis.SEPTIC_SHOCK, ClinicalDiagnosis.DENGUE_SHOCK]:
                warnings.sam_shock_conflict = True

            # 5. Initialize Physics Engine (Passing warnings container)
            params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
            state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)

            audit = AuditLog(inputs_hash=hash(str(data)))

            return ValidationResult(
                success=True,
                patient=patient,
                physics_params=params,
                initial_state=state,
                errors=[],
                warnings=warnings,
                confidence_score=confidence,
                audit_log=audit
            )

        except (CriticalConditionError, ValueError, DataTypeError) as e:
            return ValidationResult(
                success=False,
                patient=None,
                physics_params=None,
                initial_state=None,
                errors=[str(e)],
                warnings=warnings,
                confidence_score=0.0,
                audit_log=audit
            )
        except Exception as e:
            return ValidationResult(
                success=False,
                patient=None,
                physics_params=None,
                initial_state=None,
                errors=[f"System Error: {str(e)}"],
                warnings=warnings,
                confidence_score=0.0,
                audit_log=audit
            )

    @staticmethod
    def initialize_physics_engine(input: PatientInput, warnings: CalculationWarnings) -> PhysiologicalParams:
        """
        MASTER BUILDER: Creates the unique 'PhysiologicalParams' for this child.
        """
        bsa = PediaFlowPhysicsEngine._calculate_bsa(input.weight_kg, input.height_cm)
        insensible_rate = PediaFlowPhysicsEngine._calculate_insensible_loss(input, bsa)
        vols = PediaFlowPhysicsEngine._calculate_compartment_volumes(input)
        hemo = PediaFlowPhysicsEngine._calculate_hemodynamics(input)
        renal_factor = PediaFlowPhysicsEngine._calculate_renal_function(
            input.age_months, input.time_since_last_urine_hours
        )
        
        # Dengue Logic: Dynamic K_f
        k_f_base = 0.01
        sigma = 0.9 # Tight vessels
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            if input.illness_day <= 3:
                sigma = 0.9 # Febrile
            elif input.illness_day <= 6:
                sigma = 0.3 # Critical Leak
                k_f_base = 0.025
            else:
                sigma = 0.7 # Recovery
        
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            sigma = 0.4
            k_f_base = 0.02
            
        # Continuous Albumin Estimation
        albumin = input.plasma_albumin_g_dl
        albumin_uncertainty = 0.0 # Exact if measured
        if albumin is None:
            warnings.albumin_estimated = True
            albumin_uncertainty = 0.8 # +/- 0.8 g/dL uncertainty if estimated
            if input.muac_cm < 11.5: albumin = 2.5
            elif input.muac_cm > 12.5: albumin = 4.0
            else: albumin = 2.5 + ((input.muac_cm - 11.5) * 1.5) # Linear interp
            if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
                albumin = min(albumin * 0.85, 3.5) 

        # Oncotic Pressure Calculation
        pi_plasma = (2.1 * albumin) + (0.16 * (albumin**2)) + (0.009 * (albumin**3))

        # Glucose Stress Logic
        glucose_burn = 5.0 if input.age_months < 1 else 3.0
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            glucose_burn *= 1.5 # Stress
        if input.age_months < 3: # Low glycogen stores
            glucose_burn *= 1.2
        # Lactate Logic (Tissue Hypoxia)
        if input.lactate_mmol_l and input.lactate_mmol_l > 4.0:
            glucose_burn *= 1.5 # High stress
            
        # Platelet Logic (Bleeding Risk)
        if input.platelet_count and input.platelet_count < 20000:
            hemo["contractility"] *= 0.5 # Limit pressure generation to prevent bleed

        # SAM Logic: Tissue Compliance
        is_sam = input.muac_cm < 11.5
        tissue_compliance = 0.5 if is_sam else 1.0 # Floppy tissue if SAM
        sodium_bias = 1.2 if is_sam else 1.0 # Cells hold sodium if SAM

        # Target Generation
        target_map = 55.0 if input.age_months < 12 else 65.0
        max_hr = 160 if input.age_months > 12 else 180

        stop_rr = PediaFlowPhysicsEngine._calculate_safe_rr_limit(
            input.age_months, 
            input.respiratory_rate_bpm
        )
        
        # Flag Neonatal Colloid Risk
        if input.age_months < 1 and input.diagnosis in [ClinicalDiagnosis.SEPTIC_SHOCK, ClinicalDiagnosis.DENGUE_SHOCK]:
             warnings.missing_optimal_inputs.append("Neonatal Colloid Contraindication Risk")

        # 1. Calculate Afterload Sensitivity
        # Normal = 1.0. 
        # SAM or Hypothermia (<36C) = 1.5 (Heart is very sensitive to resistance)
        afterload_sens = 1.0
        if input.muac_cm < 11.5 or input.temp_celsius < 36.0:
            afterload_sens = 1.5

        # Interstitial Compliance (Stiffer in SAM = faster edema)
        # Replaces the magic number logic
        interstitial_compliance = 50.0 if input.muac_cm < 11.5 else 100.0

        # Previous Phase 2 logic glue
        afterload_sens = 1.5 if (input.muac_cm < 11.5 or input.temp_celsius < 36.0) else 1.0
        
        # 2. Calculate Baseline Capillary Pressure
        # Normal = 25 mmHg. 
        # Deep Shock = 15 mmHg (shut down). Compensated = 20 mmHg.
        if input.capillary_refill_sec > 4:
            base_pc = 15.0
        elif input.capillary_refill_sec > 2:
            base_pc = 20.0
        else:
            base_pc = 25.0
            
        # 3. Calculate Optimal Preload (The Frank-Starling Peak)
        # Usually 15% more than their normal blood volume
        opt_preload = (vols["v_blood"] * 1000.0) * 1.15

        return PhysiologicalParams(
            tbw_fraction=vols["tbw_fraction"],
            v_blood_normal_l=vols["v_blood"],
            v_inter_normal_l=vols["v_interstitial"],
            
            cardiac_contractility=hemo["contractility"],
            heart_stiffness_k=4.0, # Pediatric constant
            
            svr_resistance=hemo["svr"],
            capillary_filtration_k=k_f_base,
            blood_viscosity_eta=hemo["viscosity"],
            
            tissue_compliance_factor=tissue_compliance,
            renal_maturity_factor=renal_factor,
            
            max_cardiac_output_l_min=(input.weight_kg * 0.15), # approx 150ml/kg/min max
            venous_compliance_ml_mmhg=input.weight_kg * 1.5,
            osmotic_conductance_k=0.1,
            lymphatic_drainage_capacity_ml_min=input.weight_kg * 0.03, # ~1.8 ml/kg/hr
            
            intracellular_sodium_bias=sodium_bias,
            target_map_mmhg=target_map,
            target_heart_rate_upper_limit=max_hr,
            target_respiratory_rate_limit=stop_rr, 
            
            insensible_loss_ml_min=insensible_rate,
            plasma_oncotic_pressure_mmhg=pi_plasma,
            reflection_coefficient_sigma=sigma,
            glucose_utilization_mg_kg_min=glucose_burn,
            albumin_uncertainty_g_dl=albumin_uncertainty,
            weight_kg=input.weight_kg,
            interstitial_compliance_ml_mmhg=interstitial_compliance,
            afterload_sensitivity=afterload_sens,
            baseline_capillary_pressure_mmhg=base_pc,
            optimal_preload_ml=opt_preload
        )

    @staticmethod
    def initialize_simulation_state(input: PatientInput, params: PhysiologicalParams) -> SimulationState:
        """
        Creates the 'T=0' State based on current Clinical Presentation.
        """

        vols = PediaFlowPhysicsEngine._calculate_compartment_volumes(input)
        v_icf_normal = vols["v_intracellular"]

        # ICF Safety Check
        if v_icf_normal < 0.1:
            raise ValueError(f"Calculated ICF Volume too low ({v_icf_normal:.2f}L). Check Weight/Age.")
        
        # 1. Estimate Current Volumes based on Dehydration Severity
        deficit_factor = 0.0
        if input.diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
            if input.capillary_refill_sec > 4:
                deficit_factor = 0.15 # Severe/Shock (15%)
            else:
                deficit_factor = 0.10 # Standard Severe (10%)
        elif input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION:
            deficit_factor = 0.08 # Conservative estimate for SAM
        
        # Partition the deficit (mostly from ECF)
        vol_loss_liters = input.weight_kg * deficit_factor
        
        # 75% loss from Interstitial, 25% from Blood
        current_v_inter = params.v_inter_normal_l - (vol_loss_liters * 0.75)
        current_v_blood = params.v_blood_normal_l - (vol_loss_liters * 0.25)

        # Volume Floor (Relative, not absolute)
        min_v_blood = params.v_blood_normal_l * 0.4 # Death threshold
        current_v_blood = max(current_v_blood, min_v_blood)
        current_v_inter = max(current_v_inter, 0.05)

        # MAP Calculation via Pulse Pressure
        if input.diastolic_bp:
            # Gold Standard: MAP = DBP + 1/3 Pulse Pressure
            map_est = input.diastolic_bp + (input.systolic_bp - input.diastolic_bp) / 3.0
        else:
            # Fallback estimation
            is_vasodilated = input.diagnosis in [ClinicalDiagnosis.SEPTIC_SHOCK, ClinicalDiagnosis.DENGUE_SHOCK]
            dbp_ratio = 0.4 if is_vasodilated else 0.6
            estimated_dbp = input.systolic_bp * dbp_ratio
            map_est = estimated_dbp + (input.systolic_bp - estimated_dbp) / 3.0
        
        # 2. Ongoing Loss Estimation (The Third Vector)
        loss_rate_ml_kg = input.ongoing_losses_severity.value
        ongoing_loss_rate = (input.weight_kg * loss_rate_ml_kg) / 60.0 # Convert hr -> min

        # Initialize Glucose
        start_glucose = input.current_glucose if input.current_glucose else 90.0

        return SimulationState(
            time_minutes=0.0,
            
            v_blood_current_l=current_v_blood,
            v_interstitial_current_l=max(current_v_inter, 0.1),
            v_intracellular_current_l=v_icf_normal, 
            
            # Pressures (Estimated from Vitals for T=0)
            map_mmHg=map_est,
            cvp_mmHg=2.0 if deficit_factor > 0 else 5.0,
            pcwp_mmHg=4.0,
            p_interstitial_mmHg=-2.0 if deficit_factor > 0 else 0.0,
            
            # Fluxes (Start at 0)
            q_infusion_ml_min=0.0,
            q_leak_ml_min=0.0,
            q_urine_ml_min=0.0,
            q_lymph_ml_min=0.0,
            q_osmotic_shift_ml_min=0.0,
            
            # Safety Integrators
            total_volume_infused_ml=0.0,
            total_sodium_load_meq=0.0,
            
            current_hematocrit_dynamic=input.hematocrit_pct,
            current_weight_dynamic_kg=input.weight_kg,
            
            q_ongoing_loss_ml_min=ongoing_loss_rate,
            q_insensible_loss_ml_min=params.insensible_loss_ml_min,

            current_glucose_mg_dl=start_glucose,
            cumulative_bolus_count=0,
            time_since_last_bolus_min=999.0 # Arbitrary high number
        )

    @staticmethod
    def _calculate_derivatives(state: SimulationState, 
                               params: PhysiologicalParams, 
                               current_fluid: FluidProperties,
                               infusion_rate_ml_min: float) -> dict:
        """
        CALCULATES FLUXES (The Physics Core).
        Now includes 'Smart' Frank-Starling and Sodium logic.
        """
        
        # --- 1. ADVANCED HEMODYNAMICS (Frank-Starling Curve) ---
        # Instead of linear increase, we use a curve:
        # Volume -> Stretch -> Output (until heart is overstretched)
        
        # A. Preload (Stretch)
        current_blood_ml = state.v_blood_current_l * 1000.0
        
        # Ratio: 1.0 = Perfect Stretch. <1.0 = Empty. >1.2 = Overloaded.
        preload_ratio = current_blood_ml / params.optimal_preload_ml
        
        # B. Frank-Starling Curve Implementation
        if preload_ratio < 0.5:
             # Hypovolemic: Steep linear rise
             preload_efficiency = preload_ratio * 2.0 
        elif preload_ratio <= 1.2:
             # Optimal Plateau
             preload_efficiency = 1.0 
        else:
             # Failure: Heart is overstretched, output drops
             overstretch = preload_ratio - 1.2
             preload_efficiency = max(0.4, 1.0 - (overstretch * 1.5))

        # C. Afterload Penalty (SVR opposing flow)
        # Sepsis/Dengue often have low SVR (easier flow), Cold Shock has high SVR (harder flow)
        normalized_svr = params.svr_resistance / 1000.0
        afterload_factor = 1.0 / (1.0 + (normalized_svr - 1.0) * params.afterload_sensitivity) 

        # D. Resulting Cardiac Output (L/min)
        co_l_min = (params.max_cardiac_output_l_min * params.cardiac_contractility * preload_efficiency * afterload_factor)

        # --- 2. PRESSURE DERIVATION ---
        # MAP = (CO * SVR) + CVP
        # Factor 80 converts flow/resistance units to mmHg roughly
        derived_map = (co_l_min * params.svr_resistance / 80.0) + state.cvp_mmHg
        derived_map = max(30.0, min(derived_map, 160.0)) # Safety Clamp

        # --- 3. STARLING FORCES (Capillary Leak) ---
        # Scale Pc relative to baseline state
        p_capillary = params.baseline_capillary_pressure_mmhg * (derived_map / params.target_map_mmhg)
        
        # Dynamic Oncotic Pressure (Dilution Effect)
        dilution = params.v_blood_normal_l / state.v_blood_current_l
        current_pi_c = params.plasma_oncotic_pressure_mmhg * dilution
        if current_fluid.is_colloid: current_pi_c += 2.0 # Colloid boost

        # The Equation: Jv = Kf * [(Pc - Pi) - sigma(Pic - Pii)]
        hydrostatic_net = p_capillary - state.p_interstitial_mmHg
        oncotic_net = params.reflection_coefficient_sigma * (current_pi_c - 5.0)
        
        # Colloid Leak Adjustment
        effective_kf = params.capillary_filtration_k
        # If septic/dengue (sigma < 0.6) and using colloid, it still leaks but slower
        if current_fluid.is_colloid and params.reflection_coefficient_sigma < 0.6:
            effective_kf *= 0.5 

        q_leak = effective_kf * (hydrostatic_net - oncotic_net)
        q_leak = max(0.0, q_leak) # Fluid rarely flows back via capillaries alone

        # --- 4. RENAL & LYMPHATIC ---
        # Lymph increases with tissue pressure
        q_lymph = 0.0
        if state.p_interstitial_mmHg > -2.0:
            # Cap drive at 2x baseline to prevent infinite drainage
            lymph_drive = min((state.p_interstitial_mmHg + 2.0) / 3.0, 2.0)
            q_lymph = params.lymphatic_drainage_capacity_ml_min * max(0.5, lymph_drive)

        # Urine (Linear approximation based on perfusion)
        perfusion_p = derived_map - state.cvp_mmHg
        if perfusion_p < 35:
            q_urine = 0.0
        else:
            q_urine = (perfusion_p - 35) * 0.05 * params.renal_maturity_factor

        # OSMOTIC SHIFT (Bidirectional)
        # Handles Hypertonic (water OUT) and Hypotonic (water IN)
        # osmotic_conductance_k units: (mL / mEq) - Converts solute flux to solvent flow
        ecf_volume_l = state.v_blood_current_l + state.v_interstitial_current_l
        q_osmotic = 0.0
        
        if infusion_rate_ml_min > 0 and ecf_volume_l > 0:
            # Na influx rate
            na_flux_meq_min = (infusion_rate_ml_min / 1000.0) * current_fluid.sodium_meq_l
            # Concentration change rate in ECF (simplified)
            na_change_rate = na_flux_meq_min / ecf_volume_l
            
            # Osmotic bias: If Na is added slower than baseline tonicity (approx 0.1 meq/L/min threshold), cells swell
            # Positive gradient = Water INTO cells. Negative = Water OUT of cells.
            # We compare against a stable baseline (e.g. 140/TBW roughly) or simply the fluid tonicity vs plasma.
            
            # Simpler approach: Compare fluid Na to Plasma Na (assumed 140)
            tonic_diff = 140.0 - current_fluid.sodium_meq_l
            # If Fluid is 154 (NS), Diff is -14 (Hypertonic) -> Drive is negative -> Water out of cells
            # If Fluid is 0 (D5), Diff is 140 (Hypotonic) -> Drive is positive -> Water into cells
            
            q_osmotic = (infusion_rate_ml_min / 1000.0) * tonic_diff * params.osmotic_conductance_k * params.intracellular_sodium_bias
            
            # Add Glucose Effect (Metabolizes to free water -> into cells)
            if current_fluid.glucose_g_l > 0:
                q_osmotic += (infusion_rate_ml_min * 0.5) 

        return {
            "q_leak": q_leak,
            "q_urine": q_urine,
            "q_lymph": q_lymph,
            "q_osmotic": q_osmotic,
            "derived_map": derived_map,
            "derived_cvp": state.cvp_mmHg # CVP is updated in integration step
        }

    @staticmethod
    def simulate_single_step(state: SimulationState, 
                             params: PhysiologicalParams, 
                             infusion_rate_ml_hr: float, 
                             fluid_type: FluidType,
                             dt_minutes: float = 1.0) -> SimulationState:
        """
        THE INTEGRATOR.
        Applies fluxes to volumes over time dt.
        """
        fluid_props = FLUID_LIBRARY.get(fluid_type)
        rate_min = infusion_rate_ml_hr / 60.0
        
        # 1. Get Instantaneous Fluxes
        fluxes = PediaFlowPhysicsEngine._calculate_derivatives(state, params, fluid_props, rate_min)
        
        # 2. Update Volumes (Mass Balance)
        # Blood gains infusion (vascular portion) + lymph, loses leak + urine
        vol_dist = fluid_props.vol_distribution_intravascular
        dv_blood = ((rate_min * vol_dist) - fluxes['q_leak'] - fluxes['q_urine'] + fluxes['q_lymph']) * dt_minutes
        
        # Subtract ongoing pathological losses (diarrhea/bleeding)
        dv_blood -= (state.q_ongoing_loss_ml_min * 0.25) * dt_minutes

        new_v_blood = state.v_blood_current_l + (dv_blood / 1000.0)
        
        # Interstitial gains leak + free water (if any), loses lymph
        dv_inter = (fluxes['q_leak'] - fluxes['q_lymph'] + (rate_min * (1-vol_dist))) * dt_minutes
        dv_inter -= (state.q_ongoing_loss_ml_min * 0.75) * dt_minutes # Diarrhea comes mostly from here
        dv_inter -= state.q_insensible_loss_ml_min * dt_minutes # Sweat/Breathing
        # Adjust for osmotic shift (water moving to cells)
        dv_inter -= fluxes['q_osmotic'] * dt_minutes

        new_v_inter = state.v_interstitial_current_l + (dv_inter / 1000.0)

        # Intracellular gains osmotic shift
        dv_icf = fluxes['q_osmotic'] * dt_minutes
        new_v_icf = state.v_intracellular_current_l + (dv_icf / 1000.0)

        # 3. Update Pressures (Compliance Logic)
        # CVP (Veins are compliant but stiffen when full)
        vol_excess = (new_v_blood - params.v_blood_normal_l) * 1000
        new_cvp = 3.0 + (vol_excess / params.venous_compliance_ml_mmhg)
        new_cvp = max(1.0, min(new_cvp, 25.0))

        # Interstitial Pressure (Only rises if edema present)
        inter_excess = (new_v_inter - params.v_inter_normal_l) * 1000
        if inter_excess > 0:
            # Use the calculated compliance parameter instead of * 100.0
            new_p_inter = inter_excess / params.interstitial_compliance_ml_mmhg
        else:
            new_p_inter = -2.0

        # 4. Update Safety Trackers
        new_total_vol = state.total_volume_infused_ml + (rate_min * dt_minutes)
        new_sodium_load = state.total_sodium_load_meq + ((rate_min/1000) * fluid_props.sodium_meq_l * dt_minutes)

        # Hematocrit (Dilution)
        # Prevent division by zero if new_v_blood is impossibly low
        safe_v_blood = max(new_v_blood, 0.1)
        new_hct = (state.v_blood_current_l * state.current_hematocrit_dynamic) / safe_v_blood
        new_hct = max(5.0, min(new_hct, 70.0))
                                 
        # --- GLUCOSE DYNAMICS ---
        
        # 1. Supply: How much glucose is in the fluid? (e.g., D5 = 50g/L = 50,000mg/L)
        glucose_conc_mg_l = FLUID_LIBRARY.get(fluid_type).glucose_g_l * 1000.0
        glucose_in_mg = (rate_min / 1000.0) * glucose_conc_mg_l * dt_minutes

        # 2. Demand: Metabolic Burn Rate (mg/min)
        glucose_burn_mg = (params.glucose_utilization_mg_kg_min * params.weight_kg) * dt_minutes
        
        ecf_vol_dl = (new_v_blood + new_v_inter) * 10.0
        if ecf_vol_dl > 0:
            new_glucose = state.current_glucose_mg_dl + ((glucose_in_mg - glucose_burn_mg) / ecf_vol_dl)
        else:
            new_glucose = state.current_glucose_mg_dl
            
        new_glucose = max(10.0, min(new_glucose, 800.0))

        return SimulationState(
            time_minutes=state.time_minutes + dt_minutes,
            v_blood_current_l=new_v_blood,
            v_interstitial_current_l=new_v_inter,
            v_intracellular_current_l=new_v_icf,
            
            # Note: MAP is derived in the NEXT step's flux calculation, 
            # but we update it here for the UI to see the result of this step.
            map_mmHg=fluxes['derived_map'], 
            cvp_mmHg=new_cvp,
            pcwp_mmHg=new_cvp * 1.2, 
            p_interstitial_mmHg=new_p_inter,
            
            q_infusion_ml_min=rate_min,
            q_leak_ml_min=fluxes['q_leak'],
            q_urine_ml_min=fluxes['q_urine'],
            q_lymph_ml_min=fluxes['q_lymph'],
            q_osmotic_shift_ml_min=fluxes['q_osmotic'],
            
            total_volume_infused_ml=new_total_vol,
            total_sodium_load_meq=new_sodium_load,
            
            current_hematocrit_dynamic=new_hct,
            current_weight_dynamic_kg=state.current_weight_dynamic_kg + ((rate_min - fluxes['q_urine'])/1000 * dt_minutes),
            current_glucose_mg_dl=new_glucose,
            
            # Pass-throughs
            q_ongoing_loss_ml_min=state.q_ongoing_loss_ml_min,
            q_insensible_loss_ml_min=state.q_insensible_loss_ml_min,
            cumulative_bolus_count=state.cumulative_bolus_count,
            time_since_last_bolus_min=state.time_since_last_bolus_min + dt_minutes
        )

    @staticmethod
    def run_simulation(initial_state: SimulationState, 
                       params: PhysiologicalParams, 
                       fluid: FluidType, 
                       volume_ml: int, 
                       duration_min: int) -> dict:
        """
        PREDICTIVE ENGINE:
        Fast-forwards time to see what happens if we give this fluid.
        Returns the final state and any safety triggers.
        """
        
        current_state = initial_state
        rate_ml_hr = (volume_ml / duration_min) * 60
        
        # Safety Flags
        triggers = []
        aborted = False
        
        # SIMULATION LOOP
        for t in range(int(duration_min)):
            current_state = PediaFlowPhysicsEngine.simulate_single_step(
                current_state, params, rate_ml_hr, fluid, dt_minutes=1.0
            )
            
            # --- SAFETY SUPERVISOR CHECKS ---
            
            # 1. Pulmonary Edema Check (Rapid rise in PCWP or Interstitial Vol)
            # If lung fluid increases by > 10% in short time
            if current_state.p_interstitial_mmHg > 5.0:
                 triggers.append("STOP: Pulmonary Edema Risk (Crackles predicted)")
                 aborted = True
                 break
            
            # 2. Volume Overload (Total volume > 40ml/kg in shock)
            safe_limit_ml = params.v_blood_normal_l * 1000 * 0.8 # Rough estimate
            if current_state.total_volume_infused_ml > safe_limit_ml:
                 triggers.append(f"WARNING: Total Volume > {int(safe_limit_ml)}ml. Re-assess.")
                 # Don't abort, just warn
                 
            # 3. Hemodilution Safety
            # We just check the value directly because the engine already updated it.
            if current_state.current_hematocrit_dynamic < 20.0:
                 triggers.append("CRITICAL: Hemodilution (Hct < 20). Need Blood.")
                 aborted = True
                 break

            # Reassessment Trigger & Counter Increment
            bolus_threshold_vol = params.weight_kg * 10.0
            
            if current_state.total_volume_infused_ml >= bolus_threshold_vol and current_state.cumulative_bolus_count == 0:
                triggers.append(f"REASSESS: 10ml/kg ({int(bolus_threshold_vol)}ml) delivered. Check Vitals/Liver Span.")
                
                # Increment the counter in the state so we don't trigger again next minute
                current_state = replace(current_state, cumulative_bolus_count=1)
                
        return {
            "final_state": current_state,
            "success": not aborted,
            "triggers": triggers,
            "predicted_map_rise": int(current_state.map_mmHg - initial_state.map_mmHg),
            "fluid_leaked_percentage": int((current_state.q_leak_ml_min / (rate_ml_hr/60))*100) if rate_ml_hr > 0 else 0
        }
