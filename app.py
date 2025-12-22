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

    # Critical for Leak Phase & Oncotic Pressure calculation
    plasma_albumin_g_dl: Optional[float] = None 
    platelet_count: Optional[int] = None
    lactate_mmol_l: Optional[float] = None

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

    # ONCOTIC PRESSURE PHYSICS (Starling Forces)
    # The "Pull" keeping fluid in vessels. Critical for Dengue/Sepsis.
    plasma_oncotic_pressure_mmhg: float
    reflection_coefficient_sigma: float  # 0.9 (Tight) vs 0.3 (Leaky)

    # GLUCOSE DYNAMICS
    # Metabolic burn rate to predict hypoglycemia
    glucose_utilization_mg_kg_min: float 

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


import math

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
        if height_cm:
            return math.sqrt((weight_kg * height_cm) / 3600)
        else:
            # Weight-based approximation for children
            # Formula: (4W + 7) / (W + 90)
            return (4 * weight_kg + 7) / (weight_kg + 90)

    @staticmethod
    def _calculate_compartment_volumes(input: PatientInput) -> dict:
        """
        Determines the size of the 'Tanks' (Blood, Tissue, Cells).
        Logic: Adapts to Age and Malnutrition (SAM).
        """
        # 1. Base Ratios (Age-based)
        if input.age_months < 1:  # Neonate
            tbw_ratio = 0.80
            ecf_ratio = 0.45
        elif input.age_months < 12:  # Infant
            tbw_ratio = 0.70
            ecf_ratio = 0.30
        else:  # Child
            tbw_ratio = 0.60
            ecf_ratio = 0.25

        # 2. SAM Adjustment (Critical)
        # Malnourished children are 'wetter' (less fat/muscle, more water per kg)
        is_sam = input.muac_cm < 11.5
        if is_sam:
            tbw_ratio += 0.05  # +5% Total Water
            ecf_ratio += 0.05  # +5% Extracellular Fluid

        # Calculate Derived ICF Ratio (Conservation of Mass)
        icf_ratio = tbw_ratio - ecf_ratio

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
        # If Hct is missing, assume 35% (normal child) or 25% (anemic if Hb low)
        if input.hematocrit_pct:
            hct = input.hematocrit_pct
        elif input.hemoglobin_g_dl:
            hct = input.hemoglobin_g_dl * 3.0 # Rough est
        else:
            hct = 35.0
            
        viscosity = (hct / 45.0) ** 2.5
        
        # 3. SVR - Dimensional Correctness
        # Using Age-Based Norms (dynes-sec-cm-5)
        if input.age_months < 1:
            base_svr = 1800.0
        elif input.age_months < 12:
            base_svr = 1400.0
        else:
            base_svr = 1000.0
            
        # Adjusting for Size (Inverse relationship to surface area approx)
        # Larger child = Lower resistance vessels
        size_correction = 10 / input.weight_kg # Normalized to 10kg child
        base_svr = base_svr * (size_correction ** 0.5)

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
    def _calculate_renal_function(age_months: int) -> float:
        """
        Calculates Renal Maturity Factor (0.0 to 1.0).
        """
        if age_months >= 24:
            return 1.0
        
        # Linear maturation from 0.3 (birth) to 1.0 (2 years)
        # Slope = 0.7 / 24 = ~0.029 per month
        maturity = 0.3 + (0.029 * age_months)
        return min(maturity, 1.0)

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
            
        return daily_loss_ml / 1440.0  # Convert per day -> per minute

    @staticmethod
    def initialize_physics_engine(input: PatientInput) -> PhysiologicalParams:
        """
        MASTER BUILDER: Creates the unique 'PhysiologicalParams' for this child.
        """
        bsa = PediaFlowPhysicsEngine._calculate_bsa(input.weight_kg, input.height_cm)
        vols = PediaFlowPhysicsEngine._calculate_compartment_volumes(input)
        hemo = PediaFlowPhysicsEngine._calculate_hemodynamics(input)
        renal_factor = PediaFlowPhysicsEngine._calculate_renal_function(input.age_months)
        
        # Dengue Logic: Dynamic K_f
        k_f_base = 0.01
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            # Initial K_f is higher due to inflammatory markers
            k_f_base = 0.02 

        # SAM Logic: Tissue Compliance
        is_sam = input.muac_cm < 11.5
        tissue_compliance = 0.5 if is_sam else 1.0 # Floppy tissue if SAM
        sodium_bias = 1.2 if is_sam else 1.0 # Cells hold sodium if SAM

        # Target Generation
        target_map = 55.0 if input.age_months < 12 else 65.0
        max_hr = 160 if input.age_months > 12 else 180

        # 1. Calculate Oncotic Pressure (Starling Force)
        # Formula: π = 2.1A + 0.16A² + 0.009A³
        albumin = input.plasma_albumin_g_dl
        if albumin is None:
            # Estimate based on SAM status
            albumin = 2.5 if (input.muac_cm < 11.5) else 4.0
            
        pi_plasma = (2.1 * albumin) + (0.16 * (albumin**2)) + (0.009 * (albumin**3))
        
        # 2. Reflection Coefficient (Sigma)
        # How "leaky" are the vessels to albumin?
        # Normal = 0.9 (Tight). Dengue/Sepsis = 0.4 (Leaky).
        sigma = 0.9
        if input.diagnosis in [ClinicalDiagnosis.DENGUE_SHOCK, ClinicalDiagnosis.SEPTIC_SHOCK]:
            sigma = 0.4
            
        # 3. Glucose Utilization
        # Neonates burn sugar faster (4-6 mg/kg/min) than children (2-3 mg/kg/min)
        glucose_burn_rate = 5.0 if input.age_months < 1 else 3.0

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
            
            insensible_loss_ml_min=PediaFlowPhysicsEngine._calculate_insensible_loss(input, bsa),
            plasma_oncotic_pressure_mmhg=pi_plasma,
            reflection_coefficient_sigma=sigma,
            glucose_utilization_mg_kg_min=glucose_burn_rate,
        )

    @staticmethod
    def initialize_simulation_state(input: PatientInput, params: PhysiologicalParams) -> SimulationState:
        """
        Creates the 'T=0' State based on current Clinical Presentation.
        """

        vols = PediaFlowPhysicsEngine._calculate_compartment_volumes(input)
        v_icf_normal = input.weight_kg * vols["icf_ratio"]
        
        # 1. Estimate Current Volumes based on Dehydration Severity
        deficit_factor = 0.0
        if input.diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
            deficit_factor = 0.10 # 10% weight loss
        elif input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION:
            deficit_factor = 0.08 # Conservative estimate for SAM
        
        # Partition the deficit (mostly from ECF)
        vol_loss_liters = input.weight_kg * deficit_factor
        
        # 75% loss from Interstitial, 25% from Blood
        current_v_inter = params.v_inter_normal_l - (vol_loss_liters * 0.75)
        current_v_blood = params.v_blood_normal_l - (vol_loss_liters * 0.25)
        
        # 2. Ongoing Loss Estimation (The Third Vector)
        ongoing_loss_rate = 0.0
        if input.ongoing_losses_severity == "MILD":
            ongoing_loss_rate = (input.weight_kg * 5) / 60.0 # 5ml/kg/hr
        elif input.ongoing_losses_severity == "SEVERE":
            ongoing_loss_rate = (input.weight_kg * 10) / 60.0 # 10ml/kg/hr

        # Initialize Glucose
        start_glucose = input.current_glucose if input.current_glucose else 90.0

        return SimulationState(
            time_minutes=0.0,
            
            v_blood_current_l=max(current_v_blood, 0.1), # Prevent zero/neg
            v_interstitial_current_l=max(current_v_inter, 0.1),
            v_intracellular_current_l=v_icf_normal, 
            
            # Pressures (Estimated from Vitals for T=0)
            map_mmHg=float(input.systolic_bp) * 0.65, # Approx MAP
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
