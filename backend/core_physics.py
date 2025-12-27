"""
PediaFlow: Core Physics Engine
==============================
The mathematical core that translates inputs into physiological parameters
and simulates fluid dynamics over time.
"""

import math
from dataclasses import replace
from typing import Optional, Dict

# Import Data Models & Enums
from models import (
    PatientInput,
    PhysiologicalParams,
    SimulationState,
    ValidationResult,
    CalculationWarnings,
    AuditLog,
    ClinicalDiagnosis,
    FluidType,
    CriticalConditionError,
    DataTypeError
)

# Import Physics Constants & Fluid Library
from constants import (
    PHYSICS_CONSTANTS,
    FLUID_LIBRARY,
    FluidProperties
)

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
        
        is_sam = (input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION or input.muac_cm < 11.5)
        if is_sam:
            contractility *= 0.9  # The "Flabby Heart" penalty
        
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            contractility *= 0.7  # Septic myocardial depression

        # 2. Viscosity 
        # Using Poiseuille's approximation: (Hct/45)^2.5
        # Prevents explosion at low Hct
        hct = input.hematocrit_pct
        if hct < 20.0:
            # Linear approx for severe anemia
            viscosity = 1.5 + (0.05 * hct)
        else:
            # Poiseuille approx
            viscosity = (hct / 45.0) ** 2.5
        
        # Clamp values to prevent mathematical explosion or division by zero
        # Floor: 0.7 (Water-like)
        # Ceiling: 3.0 (Severe Polycythemia sludge - prevents SVR overflow)
        viscosity = max(0.8, min(viscosity, 3.0))
        
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

        # "Compensated Shock" 
        # Logic: We need to check deficit to apply boost to 'contractility'
        deficit_factor = 0.0
        if input.diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
             deficit_factor = 0.15 if input.capillary_refill_sec > 4 else 0.10
        elif input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION:
             deficit_factor = 0.08
        
        if deficit_factor > 0:
             compensation_boost = 1.4 if deficit_factor >= 0.10 else 1.2
             
             # NEW EXCEPTION: If SAM, remove or severely reduce the boost
             if is_sam:
                 compensation_boost = 1.05 
                 
             contractility *= compensation_boost

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
            sigma = 0.35
            k_f_base = 0.035
            
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
        glucose_burn = 0.15 # Base mg/kg/min (Neonates/Infants need ~4-6, but in shock we consume reserves)
        
        if input.age_months > 12: 
            glucose_burn = 0.12 # Older kids burn less per kg
            
        # Stress Modifiers
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            glucose_burn *= 1.5 # Hypermetabolism
            
        # Platelet Logic (Bleeding Risk)
        if input.platelet_count and input.platelet_count < 20000:
            hemo["contractility"] *= 0.5 # Limit pressure generation to prevent bleed

        # SAM Logic: Tissue Compliance
        is_sam = input.muac_cm < 11.5
        if is_sam:
            tissue_compliance = 0.3  # More floppy (LOWER = MORE compliant)
            interstitial_compliance = 30.0  # **LOWER compliance = FASTER edema**
            # ADD: Reduced capillary surface area
            capillary_recruitment_base = 0.7  # SAM microvascular rarefaction
        else:
            tissue_compliance = 1.0
            interstitial_compliance = 100.0
            capillary_recruitment_base = 1.0

        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK and input.sp_o2_percent < 90:
             interstitial_compliance = 40.0 # Stiff lungs
             warnings.missing_optimal_inputs.append("Hypoxic Septic Shock: High ARDS Risk Mode")
        
        # Store recruitment base in params for derivatives
        sodium_bias = 1.2 if is_sam else 1.0 # Cells hold sodium if SAM

        # Target Generation
        target_map = 55.0 if input.age_months < 12 else 65.0
        base_max_hr = 160 if input.age_months > 12 else 180
        fever_buffer = 0
        
        if input.temp_celsius > 37.5:
            excess_temp = input.temp_celsius - 37.5
            fever_buffer = int(excess_temp * 15) # Allow 15 bpm per degree
            
        max_hr = base_max_hr + fever_buffer
        
        # Hard Ceiling (Physiological Max) just to be safe
        max_hr = min(max_hr, 220)

        stop_rr = PediaFlowPhysicsEngine._calculate_safe_rr_limit(
            input.age_months, 
            input.respiratory_rate_bpm
        )
        
        # Flag Neonatal Colloid Risk
        if input.age_months < 1 and input.diagnosis in [ClinicalDiagnosis.SEPTIC_SHOCK, ClinicalDiagnosis.DENGUE_SHOCK]:
             warnings.missing_optimal_inputs.append("Neonatal Colloid Contraindication Risk")

        # 1. Calculate Afterload Sensitivity
        # Normal = 0.2 (Healthy hearts maintain flow against resistance).
        # SAM or Hypothermia = 1.5 (Weak hearts give up easily).
        afterload_sens = 0.2 
        if input.muac_cm < 11.5 or input.temp_celsius < 36.0:
            afterload_sens = 0.5

        # 2. Calculate Baseline Capillary Pressure
        # Normal = 25 mmHg. 
        # Deep Shock = 15 mmHg (shut down). Compensated = 20 mmHg.
        if input.capillary_refill_sec > 4:
            base_pc = 15.0
        elif input.capillary_refill_sec > 2:
            base_pc = 20.0
        else:
            base_pc = 25.0    

        opt_preload = (vols["v_blood"] * 1000.0) * 1.15
        if input.baseline_hepatomegaly:
             # Reduce the "Optimal Preload" (Heart can't stretch as much)
             opt_preload *= 0.85 
             warnings.missing_optimal_inputs.append("Hepatomegaly Detected: Reduced Volume Tolerance")
    
        # 1. Estimate Start Volume (Copying logic from initialize_simulation_state)
        # We need to know the *actual* blood volume at T=0 to calibrate SVR correctly.
        deficit_factor = 0.0
        if input.diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
            deficit_factor = 0.15 if input.capillary_refill_sec > 4 else 0.10
        elif input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION:
            deficit_factor = 0.08
            
        vol_loss_liters = input.weight_kg * deficit_factor
        current_v_blood_est = vols["v_blood"] - (vol_loss_liters * 0.25)
        
        # 2. Determine Target MAP
        if input.diastolic_bp is not None:
             start_map = input.diastolic_bp + (input.systolic_bp - input.diastolic_bp) / 3.0
        else:
             start_map = input.systolic_bp * 0.65

        # 3. Base Cardiac Output (Using EST VOLUME, not Normal Volume)
        preload_ratio = (current_v_blood_est * 1000.0) / opt_preload
        
        # Standard Frank-Starling Logic
        if preload_ratio <= 1.0:
             preload_efficiency = preload_ratio
        elif preload_ratio <= 1.2:
             preload_efficiency = 1.0 
        else:
             overstretch = preload_ratio - 1.2
             preload_efficiency = max(0.4, 1.0 - (overstretch * 1.5))
        
        base_co = (
            (input.weight_kg * 0.15) * hemo["contractility"] * preload_efficiency
        )

        # 4. Iterative Solver to find SVR
        current_guess_svr = hemo["svr"]
        assumed_cvp = 2.0 if deficit_factor > 0 else 5.0 # Lower CVP if dehydrated
        if input.age_months < 2: rr_limit = 60
        elif input.age_months < 12: rr_limit = 50
        else: rr_limit = 40

        dry_lung_diagnoses = [
            ClinicalDiagnosis.SEVERE_DEHYDRATION,
            ClinicalDiagnosis.SAM_DEHYDRATION,  # <--- ADD THIS
            ClinicalDiagnosis.SEPTIC_SHOCK,  # ← ADD THIS
            ClinicalDiagnosis.DENGUE_SHOCK,
        ]
        
        is_hypoxic = input.sp_o2_percent < 90
        is_extreme_tachypnea = input.respiratory_rate_bpm > (rr_limit * 1.4)
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            is_hypoxic = input.sp_o2_percent < 85 
        # Only treat as "Congestion" if not clearly DKA/Severe Dehydration (Acidotic breathing)
        # But if SpO2 is low (<90), it is ALWAYS Congestion/ARDS.
        has_wet_lungs = is_hypoxic or (is_extreme_tachypnea and input.diagnosis not in dry_lung_diagnoses)

        if has_wet_lungs:
             # Force High CVP (Congestion). 
             # 16.0 mmHg ensures that 'p_interstitial' initializes > 4.0, triggering the Safety Halt.
             assumed_cvp = max(assumed_cvp, 16.0) 
             warnings.missing_optimal_inputs.append("Respiratory Distress: Modeling Pulmonary Congestion")
             
        elif input.baseline_hepatomegaly:
             # Start with higher back-pressure due to congestion (Lower priority than Hypoxia)
             assumed_cvp = max(assumed_cvp, 8.0)
            
        current_sens = afterload_sens
        
        for _ in range(15):
            normalized_svr = current_guess_svr / 1000.0
            denom = 1.0 + (normalized_svr - 1.0) * afterload_sens
            raw_factor = 1.0 / max(0.1, denom)
            afterload_factor = max(0.3, raw_factor)
            
            effective_co = base_co * afterload_factor
            safe_co = max(0.01, effective_co)
            
            # SVR = (MAP - CVP) * 80 / Flow
            required_svr = ((start_map - assumed_cvp) * 80.0) / safe_co
            
            current_guess_svr = (current_guess_svr + required_svr) / 2.0

        final_svr = max(200.0, min(current_guess_svr, 20000.0)) # Allowed higher SVR cap
        final_sens = afterload_sens
        if final_svr > 3000:
            final_sens = afterload_sens * 0.5

        final_starting_volume = current_v_blood_est

        print(f"DEBUG: has_wet_lungs={has_wet_lungs}")
        print(f"DEBUG: is_hypoxic={input.sp_o2_percent < 90}")
        print(f"DEBUG: assumed_cvp={assumed_cvp}")
        
        return PhysiologicalParams(
            tbw_fraction=vols["tbw_fraction"],
            v_blood_normal_l=vols["v_blood"],
            v_inter_normal_l=vols["v_interstitial"],
            
            cardiac_contractility=hemo["contractility"],
            heart_stiffness_k=4.0, # Pediatric constant
            
            svr_resistance=final_svr,
            capillary_filtration_k=k_f_base,
            blood_viscosity_eta=hemo["viscosity"],
            
            tissue_compliance_factor=tissue_compliance,
            renal_maturity_factor=renal_factor,
            
            max_cardiac_output_l_min=(input.weight_kg * 0.15), # approx 150ml/kg/min max
            venous_compliance_ml_mmhg=input.weight_kg * 1.5,
            osmotic_conductance_k=0.5,
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
            afterload_sensitivity=final_sens,
            baseline_capillary_pressure_mmhg=base_pc,
            optimal_preload_ml=opt_preload,
            target_cvp_mmhg=assumed_cvp,
            final_starting_blood_volume_l=final_starting_volume,
            is_sam=is_sam,
            capillary_recruitment_base=capillary_recruitment_base
        )

    @staticmethod
    def initialize_simulation_state(input: PatientInput, params: PhysiologicalParams) -> SimulationState:
        """
        T=0: INPUT BP IS TRUTH. 
        Calculates CVP and Blood Volume backwards from the Input BP,
        BUT respects clinical signs of congestion (Hepatomegaly).
        """
        
        # 1. Base Volumes
        vols = PediaFlowPhysicsEngine._calculate_compartment_volumes(input)
        current_v_inter = params.v_inter_normal_l
        
        # SAM/Septic Baseline Edema (Third spacing logic)
        if input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION:
            baseline_edema_ml = input.weight_kg * 15  # SAM = Edema
        elif input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
            baseline_edema_ml = input.weight_kg * 5   # Sepsis = Mild 3rd spacing only
        else:
            baseline_edema_ml = 0
        if baseline_edema_ml > 0:
            current_v_inter += baseline_edema_ml / 1000.0

        # 2. DETERMINE STARTING MAP (The Ground Truth)
        if input.diastolic_bp is not None:
             start_map = input.diastolic_bp + (input.systolic_bp - input.diastolic_bp) / 3.0
        else:
             start_map = input.systolic_bp * 0.65

        # 3. BACK-CALCULATE CVP (The "Backward" Physics)
        # Physics: MAP = CVP + (CO * SVR / 80)
        co_est = params.max_cardiac_output_l_min * params.cardiac_contractility * 0.75 
        
        # Hyperdynamic Sepsis Check
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
             co_est *= 1.2 

        pressure_drop = (co_est * params.svr_resistance) / 80.0
        estimated_cvp = start_map - pressure_drop
        
        # Clamp CVP to physiological realities
        start_cvp = max(1.0, min(estimated_cvp, 18.0))

        # --- CRITICAL RESTORATION: CONGESTION OVERRIDE ---
        # If the math says "Low CVP" (due to low BP), but exam says "Hepatomegaly",
        # we must force CVP up. This implies the Heart/SVR are worse than estimated.
        if input.baseline_hepatomegaly:
            start_cvp = max(start_cvp, 10.0) # Force congestion threshold

        # 4. BACK-CALCULATE BLOOD VOLUME FROM CVP
        # CVP = 3 + (Excess / Compliance)
        vol_excess_ml = (start_cvp - 3.0) * params.venous_compliance_ml_mmhg
        current_v_blood = params.v_blood_normal_l + (vol_excess_ml / 1000.0)
        
        # Safety floor: Even if math says empty, don't crash the array
        current_v_blood = max(current_v_blood, params.v_blood_normal_l * 0.35)

        # 5. INTERSTITIAL PRESSURE & LUNG WATER
        # If CVP is high (>8), fluid leaks into tissue (Restored Logic)
        if start_cvp > 8.0:
             # Equilibrium: P_inter rises with CVP
             equilibrium_p_inter = (start_cvp - 8.0) * 0.5 
             
             # Calculate volume needed to reach this pressure
             # P = Vol / Compliance -> Vol = P * Compliance
             if equilibrium_p_inter > 0:
                 required_excess_vol = (equilibrium_p_inter * params.interstitial_compliance_ml_mmhg) / 1000.0
                 current_v_inter += required_excess_vol

        # Recalculate P_inter based on final volume
        inter_excess_ml = (current_v_inter - params.v_inter_normal_l) * 1000
        start_p_inter = max(-2.0, inter_excess_ml / params.interstitial_compliance_ml_mmhg)

        # 6. DISEASE-SPECIFIC METABOLIC BASELINES
        start_glucose = input.current_glucose if input.current_glucose else 90.0
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK and not input.current_glucose: 
            start_glucose = 65.0 # Septic hypoglycemia risk
            
        start_sodium = input.current_sodium if input.current_sodium else 140.0
        if params.is_sam and not input.current_sodium: 
            start_sodium = 132.0 # SAM Hyponatremia
            
        start_lactate = input.lactate_mmol_l if input.lactate_mmol_l else 2.0
        if not input.lactate_mmol_l:
            if input.capillary_refill_sec > 4: start_lactate = 6.0
            elif input.capillary_refill_sec > 2: start_lactate = 3.5

        print(f"DEBUG: p_interstitial={start_p_inter}")
        print(f"DEBUG: baseline_edema_ml={baseline_edema_ml}")
        print(f"DEBUG: interstitial_compliance={params.interstitial_compliance_ml_mmhg}")

        return SimulationState(
            time_minutes=0.0,
            
            # Exact Volumes aligned to Input BP + Congestion Flags
            v_blood_current_l=current_v_blood,
            v_interstitial_current_l=max(current_v_inter, 0.1),
            v_intracellular_current_l=vols["v_intracellular"], 
        
            # Exact Pressures
            cvp_mmHg=start_cvp,      
            p_interstitial_mmHg=start_p_inter,      
            map_mmHg=start_map,                          
            pcwp_mmHg=start_cvp * 1.25, 

            # Zeroed Fluxes
            q_infusion_ml_min=0.0, q_leak_ml_min=0.0, q_urine_ml_min=0.0,
            q_lymph_ml_min=0.0, q_osmotic_shift_ml_min=0.0,
            
            # Integrators
            total_volume_infused_ml=0.0,
            total_sodium_load_meq=0.0,
            
            current_hematocrit_dynamic=input.hematocrit_pct,
            current_weight_dynamic_kg=input.weight_kg,
            
            q_ongoing_loss_ml_min=(input.weight_kg * input.ongoing_losses_severity.value) / 60.0,
            q_insensible_loss_ml_min=params.insensible_loss_ml_min,

            # Metabolics
            current_glucose_mg_dl=start_glucose,
            current_sodium=start_sodium,
            current_hemoglobin=input.hemoglobin_g_dl if input.hemoglobin_g_dl else 11.0,
            current_potassium=3.8 if params.is_sam else 4.2, 
            current_lactate_mmol_l=start_lactate,
            
            cumulative_bolus_count=0,
            time_since_last_bolus_min=999.0, 
            is_sam=params.is_sam,
            capillary_recruitment_base=params.capillary_recruitment_base,
            final_starting_blood_volume_l=current_v_blood
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
        print(f"\n🔍 T={state.time_minutes:.0f}min | MAP={state.map_mmHg:.1f} | Glucose={state.current_glucose_mg_dl:.1f}")
        print(f"   Infusion={infusion_rate_ml_min:.1f}ml/min | Vblood={state.v_blood_current_l*1000:.0f}ml")
        # --- 1. ADVANCED HEMODYNAMICS (Frank-Starling Curve) ---
        # Instead of linear increase, we use a curve:
        # Volume -> Stretch -> Output (until heart is overstretched)
        
        # A. Preload (Stretch)
        current_blood_ml = state.v_blood_current_l * 1000.0
        
        # Ratio: 1.0 = Perfect Stretch. <1.0 = Empty. >1.2 = Overloaded.
        safe_preload_ml = max(params.optimal_preload_ml, 10.0)  # Minimum 10ml optimal preload
        preload_ratio = current_blood_ml / safe_preload_ml
        is_sam = params.is_sam 
        capillary_recruitment_base = params.capillary_recruitment_base
        
        # B. Frank-Starling Curve Implementation 
        # Linear rise up to 1.0 (Optimal), then plateau, then failure.
        print(f"DEBUG FS: preload_ratio={preload_ratio:.3f}, v_blood_ml={current_blood_ml:.0f}")
        if preload_ratio <= 1.0:
             # Sympathetic Compensation
             # If very empty (<0.8), heart rate/contractility rises to maintain output
             if preload_ratio < 0.8 and not params.is_sam:
                 max_boost = 0.3 * params.cardiac_contractility
                 compensatory_boost = 1.0 + (0.8 - preload_ratio) * max_boost
                 preload_efficiency = preload_ratio * compensatory_boost
             else:
                 compensatory_boost = 1.0 
                 preload_efficiency = preload_ratio 
        elif preload_ratio <= 1.3:
             # Plateau (Optimal stretch)
             preload_efficiency = 1.0 
        else:
             # Failure: Heart is overstretched, output drops
             overstretch = preload_ratio - 1.3
             preload_efficiency = max(0.85, 1.0 - (overstretch * 0.3))
        print(f"DEBUG FS: efficiency={preload_efficiency:.3f}")

        # C. Afterload Penalty (SVR opposing flow)
        # Sepsis/Dengue often have low SVR (easier flow), Cold Shock has high SVR (harder flow)
        normalized_svr = params.svr_resistance / 1000.0
        denom = 1.0 + (normalized_svr - 1.0) * params.afterload_sensitivity
        raw_factor = 1.0 / max(0.1, denom)
        afterload_factor = max(0.5, raw_factor) 
        print(f"DEBUG Hemodynamics: SVR={params.svr_resistance:.0f} -> Afterload_Factor={afterload_factor:.2f}")

        # Dynamic SVR 
        # SVR adjusts to CVP changes (Baroreflex). 
        # If CVP drops, SVR rises to maintain MAP.
        safe_cvp = max(0.1, state.cvp_mmHg)
        # 1. Calculate potential vasodilation based on CVP refill
        potential_svr = params.svr_resistance * ((params.target_cvp_mmhg / safe_cvp) ** 0.3)
        
        # 2. Safety Clamp with Volume Interlock:
        # Condition A: If Hypotensive, Clamp SVR (Sympathetic Rescue).
        # Condition B: If Normotensive BUT Heart is Empty (Compensated Cold Shock), Clamp SVR.
        # Result: We only relax SVR when MAP is stable AND Volume is returning.
        
        is_hypotensive = state.map_mmHg < (params.target_map_mmhg - 5.0)
        is_empty_heart = preload_ratio < 0.95 # Heart is less than 95% full
        
        if is_hypotensive or is_empty_heart: 
             target_svr = params.svr_resistance
        else:
             # Only allow SVR to drop if we have Pressure AND Volume
             target_svr = min(potential_svr, params.svr_resistance)
            
        # Prevent SVR from jumping instantly (Arterial Smooth Muscle Inertia)
        # This smooths out the "Spikes" and "Steps".
        
        # Estimate current SVR state based on Ohm's law approximation
        # SVR ~ (MAP - CVP) / Approx_CO
        # 1. Estimate True CO (Must include Preload Efficiency!)
        # If we ignore preload, we overestimate CO and underestimate the required SVR.
        true_co_est = (
            params.max_cardiac_output_l_min * params.cardiac_contractility * preload_efficiency * # <--- CRITICAL ADDITION
            afterload_factor
        )
        true_co_est = max(0.01, true_co_est) # Safety floor
        
        # 2. Calculate current implied SVR based on physics
        current_svr_est = (state.map_mmHg - state.cvp_mmHg) * 80 / true_co_est
        
        # 3. Blend: 95% Inertia, 5% New Target
        inertia = 0.999 if not is_hypotensive else 0.995
        svr_dynamic = (current_svr_est * inertia) + (target_svr * (1 - inertia))
        
        if params.is_sam:
            svr_dynamic = min(svr_dynamic, params.svr_resistance * 1.2)  # Cap compensation
            svr_dynamic = max(svr_dynamic, params.svr_resistance * 0.6)  # Floor for vasodilatory tendency
        
        # 4. Clamp to safe limits
        svr_dynamic = max(200.0, min(svr_dynamic, 20000.0))

        normalized_svr_dynamic = svr_dynamic / 1000.0
        denom_dynamic = 1.0 + (normalized_svr_dynamic - 1.0) * params.afterload_sensitivity
        raw_factor_updated = 1.0 / max(0.1, denom_dynamic)
        afterload_factor_updated = max(0.5, raw_factor_updated)
                                   
        # Recalculate CO and MAP
        co_l_min = (params.max_cardiac_output_l_min * params.cardiac_contractility * preload_efficiency * afterload_factor_updated)
        derived_map = (co_l_min * svr_dynamic / 80.0) + state.cvp_mmHg
        derived_map = max(30.0, min(derived_map, 160.0))
        
        print(f"🎯 FINAL: CO={co_l_min:.3f}L/min → MAP={derived_map:.1f} | SVR={svr_dynamic:.0f}")

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

        if derived_map < 50:
            capillary_recruitment = 2.0
        elif preload_ratio < 0.8:
            capillary_recruitment = 0.5
        else:
            capillary_recruitment = 1.0

        capillary_recruitment = capillary_recruitment_base * capillary_recruitment
        if params.is_sam:  # Prevent over-recruitment
            capillary_recruitment = min(capillary_recruitment, 0.8)
        effective_kf = effective_kf * capillary_recruitment

        q_leak = effective_kf * (hydrostatic_net - oncotic_net)
        q_leak = max(0.0, q_leak) # Fluid rarely flows back via capillaries alone

        # --- 4. RENAL & LYMPHATIC ---
        # Lymph increases with tissue pressure
        q_lymph = 0.0
        # Baseline drive (0.2) + Pressure drive
        lymph_drive = 0.2 + max(0.0, (state.p_interstitial_mmHg + 2.0) / 4.0)
        # Cap at 3x
        lymph_drive = min(lymph_drive, 3.0)
        if params.is_sam:
            lymphatic_efficiency = 0.4  # Poor lymphatic function
        else:
            lymphatic_efficiency = 1.0
        q_lymph = params.lymphatic_drainage_capacity_ml_min * lymph_drive * lymphatic_efficiency

        # Urine (Linear approximation based on perfusion)
        perfusion_p = derived_map - state.cvp_mmHg
        baseline_gfr = 2.1 * (params.weight_kg / 10.0) * params.renal_maturity_factor
        if perfusion_p < 30:
            q_urine = 0.0
        elif perfusion_p < 60:
            sigmoid = 1.0 / (1.0 + math.exp(-(perfusion_p - 45) / 5))
            q_urine = (perfusion_p - 30) * 0.03 * params.renal_maturity_factor * sigmoid
        elif perfusion_p < 100:
            q_urine = baseline_gfr 
        else:
            q_urine = baseline_gfr * (1 + (perfusion_p - 100) * 0.01)

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
            tonic_diff = state.current_sodium - current_fluid.sodium_meq_l
            # If Fluid is 154 (NS), Diff is -14 (Hypertonic) -> Drive is negative -> Water out of cells
            # If Fluid is 0 (D5), Diff is 140 (Hypotonic) -> Drive is positive -> Water into cells
            
            q_osmotic = (infusion_rate_ml_min / 1000.0) * tonic_diff * (params.osmotic_conductance_k * 0.005) * params.intracellular_sodium_bias
            
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
        """ROCK-SOLID INTEGRATOR - No overrides, pure physics."""
        fluid_props = FLUID_LIBRARY.get(fluid_type)
        rate_min = infusion_rate_ml_hr / 60.0
    
        # 1. PHYSICS FIRST (Calculate ALL fluxes from CURRENT state)
        fluxes = PediaFlowPhysicsEngine._calculate_derivatives(state, params, fluid_props, rate_min)
    
        # 2. VOLUME UPDATES (Conservation of mass - exact ml/min * time)
        vol_dist = fluid_props.vol_distribution_intravascular
    
        # Blood: +infusion(25%) +lymph -leak -urine -gut_loss(25%)
        dv_blood_ml = (
            (rate_min * vol_dist) * dt_minutes +
            fluxes['q_lymph'] * dt_minutes -
            fluxes['q_leak'] * dt_minutes -
            fluxes['q_urine'] * dt_minutes -
            (state.q_ongoing_loss_ml_min * 0.25) * dt_minutes
        )
    
        # Interstitial: +leak +infusion(75%) -lymph -gut_loss(75%) -insensible -osmotic_out
        dv_inter_ml = (
            fluxes['q_leak'] * dt_minutes +
            (rate_min * (1-vol_dist)) * dt_minutes -
            fluxes['q_lymph'] * dt_minutes -
            (state.q_ongoing_loss_ml_min * 0.75) * dt_minutes -
            state.q_insensible_loss_ml_min * dt_minutes -
            fluxes['q_osmotic'] * dt_minutes
        )
    
        # Intracellular: +osmotic_in
        dv_icf_ml = fluxes['q_osmotic'] * dt_minutes
    
        # 3. NEW VOLUMES (Safety floors)
        new_v_blood = max(state.v_blood_current_l + (dv_blood_ml / 1000), params.v_blood_normal_l * 0.4)
        new_v_inter = max(state.v_interstitial_current_l + (dv_inter_ml / 1000), 0.1)
        new_v_icf = max(state.v_intracellular_current_l + (dv_icf_ml / 1000), 0.1)
    
        # 4. PRESSURES FROM VOLUMES (Pure compliance physics)
        blood_excess_ml = (new_v_blood - params.v_blood_normal_l) * 1000
        new_cvp = max(1.0, min(3.0 + (blood_excess_ml / params.venous_compliance_ml_mmhg), 25.0))
    
        inter_excess_ml = (new_v_inter - params.v_inter_normal_l) * 1000
        new_p_inter = max(-2.0, inter_excess_ml / params.interstitial_compliance_ml_mmhg)
    
        # 5. MAP EMERGES NATURALLY (CO * SVR + CVP)
        # Recalculate derivatives WITH NEW VOLUMES for accurate MAP
        new_state_temp = replace(state,
            v_blood_current_l=new_v_blood,
            v_interstitial_current_l=new_v_inter,
            cvp_mmHg=new_cvp,
            p_interstitial_mmHg=new_p_inter
        )
        final_fluxes = PediaFlowPhysicsEngine._calculate_derivatives(new_state_temp, params, fluid_props, rate_min)
        new_map = final_fluxes['derived_map']
    
        # Smooth MAP transition (prevents jumps)
        new_map = state.map_mmHg * 0.7 + new_map * 0.3

        # 6. METABOLIC UPDATES (ALL electrolytes, Hb, glucose)
        # Helper: Liters infused this step
        step_infusion_l = (rate_min * dt_minutes) / 1000.0
        
        # --- A. HEMOGLOBIN & HEMATOCRIT ---
        # Logic: Hb changes if we ADD red cells (PRBC) or if Volume changes (Dilution/Concentration).
        # We calculate Total Hb Mass in circulation.
        
        # 1. Current Mass (g) = Conc (g/dL) * Vol (L) * 10
        current_hb_mass_g = state.current_hemoglobin * state.v_blood_current_l * 10.0
        
        # 2. Influx Mass
        # Since FluidProperties doesn't have 'hemoglobin_content', we check the Enum type.
        hb_conc_in_fluid = 22.0 if fluid_type == FluidType.PRBC else 0.0
        
        hb_influx_g = hb_conc_in_fluid * step_infusion_l * 10.0
        
        # 3. New Concentration = (Old Mass + Influx) / New Volume
        # NOTE: If Dengue leaks plasma (lowering new_v_blood) but Hb Mass stays same,
        # the denominator shrinks, causing Hb to RISE. (Auto-Hemoconcentration).
        new_total_hb_mass = current_hb_mass_g + hb_influx_g
        new_hemoglobin = new_total_hb_mass / (new_v_blood * 10.0)
        
        # Clamp to physiological survival limits
        new_hemoglobin = max(2.0, min(new_hemoglobin, 26.0))
        new_hematocrit = new_hemoglobin * 3.0

        # --- B. SODIUM (Distribution: ECF) ---
        # Sodium distributes across Blood + Interstitial fluid.
        ecf_vol_l = new_v_blood + new_v_inter
        
        # 1. Current Mass (mEq)
        current_na_mass = state.current_sodium * (state.v_blood_current_l + state.v_interstitial_current_l)
        
        # 2. Influx (From Fluid)
        na_influx = fluid_props.sodium_meq_l * step_infusion_l
        
        # 3. Efflux (Urine)
        # SAM retains Na (low urine conc), Sepsis/Dengue wastes Na (high urine conc).
        if state.current_sodium > 145:
            urine_na_conc = 100.0 # Dumping excess
        elif state.current_sodium < 130:
            urine_na_conc = 10.0 # Conservation
        else:
            urine_na_conc = 60.0 # Baseline

        if params.is_sam:
            # SAM kidneys cannot excrete sodium load effectively
            # Even if serum Na is high, urine Na remains inappropriately low
            urine_na_conc = min(urine_na_conc, 20.0) 
            
        elif params.reflection_coefficient_sigma < 0.6: 
            # Sepsis/Dengue: Tubular dysfunction / wasting
            # Kidneys leak sodium; urine Na is inappropriately high
            urine_na_conc = max(urine_na_conc, 80.0)
            
        na_efflux = (fluxes['q_urine'] / 1000.0 * dt_minutes) * urine_na_conc
        
        # 4. New Concentration
        new_sodium = (current_na_mass + na_influx - na_efflux) / ecf_vol_l
        print(f"DEBUG Na: Mass={current_na_mass:.1f} + In={na_influx:.2f} - Out={na_efflux:.2f} | Vol={ecf_vol_l:.3f}L -> Na={new_sodium:.1f}")
        new_sodium = max(110.0, min(new_sodium, 180.0))
        na_in_meq_min = (rate_min / 1000.0) * fluid_props.sodium_meq_l

        # --- C. POTASSIUM (Dengue Hypokalemia Logic) ---
        # 
        # Domain: We model Serum K changes in Blood Volume.
        
        current_k_mass = state.current_potassium * (state.v_blood_current_l + state.v_interstitial_current_l)
        
        # Influx (High for ReSoMal, Moderate for RL)
        k_influx = fluid_props.potassium_meq_l * step_infusion_l
        
        # Efflux (Urine)
        k_efflux = (fluxes['q_urine'] / 1000.0 * dt_minutes) * 40.0 # Urine K is usually high
        
        # DENGUE/SEPSIS SHIFT
        # In high-stress leaky states, K shifts intracellularly or is wasted.
        k_shift_loss = 0.0
        if params.reflection_coefficient_sigma < 0.6:
             k_shift_loss = 0.005 * dt_minutes 
            
        ecf_vol_l = new_v_blood + new_v_inter
        new_k = (current_k_mass + k_influx - k_efflux - k_shift_loss) / ecf_vol_l
        new_potassium = max(1.5, min(new_k, 9.0))

        # --- D. GLUCOSE ---
        # Domain: Blood Volume (rapid equilibration)
        
        # 1. Mass (mg) = mg/dL * dL (Vol*10)
        current_ecf_dl = (state.v_blood_current_l + state.v_interstitial_current_l) * 10.0
        current_gluc_mass_mg = state.current_glucose_mg_dl * current_ecf_dl
        
        # 2. Influx (fluid g/L -> mg/L -> mg total)
        gluc_influx_mg = (fluid_props.glucose_g_l * 1000.0) * step_infusion_l
        
        # 3. Consumption (mg/kg/min)
        burn_rate = params.glucose_utilization_mg_kg_min
        if params.reflection_coefficient_sigma < 0.6: 
            burn_rate *= 1.5 # Stress Hypermetabolism
        if params.is_sam:
            burn_rate *= 0.7 # Low muscle mass
            
        gluc_consumption_mg = (params.weight_kg * burn_rate) * dt_minutes
        
        new_ecf_dl = (new_v_blood + new_v_inter) * 10.0
        new_gluc_conc = (current_gluc_mass_mg + gluc_influx_mg - gluc_consumption_mg) / new_ecf_dl
        
        print(f"DEBUG Glucose: Mass={current_gluc_mass_mg:.0f} + In={gluc_influx_mg:.0f} - Burn={gluc_consumption_mg:.0f} | Vol={new_ecf_dl/10:.2f}L -> {new_gluc_conc:.0f} mg/dL")
        new_glucose = max(10.0, min(new_gluc_conc, 800.0))

        # --- E. LACTATE & WEIGHT ---
        # Lactate clearance improves with Perfusion (MAP - CVP)
        perfusion_p = new_map - new_cvp
        clearance_k = 0.08 * (perfusion_p / 65.0) 
        if params.reflection_coefficient_sigma < 0.6: clearance_k = 0.02 # Liver Dysfunction
        
        new_lactate = state.current_lactate_mmol_l * (1.0 - (clearance_k * dt_minutes))
        # Production if shock persists
        if perfusion_p < 35.0: new_lactate += 0.15 * dt_minutes
        
        # Real-time Weight (Sum of all fluid changes)
        # 1 L = 1 kg approx
        total_fluid_change_l = (dv_blood_ml + dv_inter_ml + dv_icf_ml) / 1000.0
        new_weight = state.current_weight_dynamic_kg + total_fluid_change_l
        
        # Bolus tracking logic
        # Calculate volume given in this specific minute
        step_infused_vol_ml = rate_min * dt_minutes
        total_vol_accum_ml = state.total_volume_infused_ml + step_infused_vol_ml

        # Logic: If we are actively flowing (> 5 ml/hr), the "Time Since Last Bolus" is 0.
        # It only starts counting up (1, 2, 3...) once the infusion stops.
        if step_infused_vol_ml > 0.1: 
            new_time_since_bolus = 0.0
        else:
            new_time_since_bolus = state.time_since_last_bolus_min + dt_minutes

        # Logic: Count discrete boluses? 
        # (Simplified: Just count total volume for now, unless specific trigger needed)
        new_bolus_count = state.cumulative_bolus_count
                                
        return replace(state,
            time_minutes=state.time_minutes + dt_minutes,
            v_blood_current_l=new_v_blood,
            v_interstitial_current_l=new_v_inter,
            v_intracellular_current_l=new_v_icf,
            map_mmHg=new_map,
            cvp_mmHg=new_cvp,
            p_interstitial_mmHg=new_p_inter,
            pcwp_mmHg=new_cvp * 1.2,  # PCWP tracks CVP
            q_infusion_ml_min=rate_min,
            q_leak_ml_min=fluxes['q_leak'],
            q_urine_ml_min=fluxes['q_urine'],
            q_lymph_ml_min=fluxes['q_lymph'],
            q_osmotic_shift_ml_min=fluxes['q_osmotic'],
            current_glucose_mg_dl=new_glucose,
            current_sodium=new_sodium,
            current_hemoglobin=new_hemoglobin,
            current_hematocrit_dynamic=new_hematocrit,
            current_potassium=new_potassium,
            current_lactate_mmol_l=max(0.1, min(new_lactate, 25.0)),
            total_volume_infused_ml=state.total_volume_infused_ml + (rate_min * dt_minutes),
            total_sodium_load_meq=state.total_sodium_load_meq + (na_in_meq_min * dt_minutes),
            current_weight_dynamic_kg=new_weight,
        
            # Bolus tracking
            cumulative_bolus_count=new_bolus_count,
            time_since_last_bolus_min=new_time_since_bolus
        )

    @staticmethod
    def run_simulation(initial_state: SimulationState, 
                       params: PhysiologicalParams, 
                       fluid: FluidType, 
                       volume_ml: int, 
                       duration_min: int,
                       return_series: bool = False) -> dict:
        """
        PREDICTIVE ENGINE:
        Fast-forwards time to see what happens if we give this fluid.
        Returns the final state and any safety triggers.
        """
        # Baseline Safety Check
        # If the patient ALREADY has high lung pressure (Wet Lungs),
        # do not simulate a bolus. Abort immediately.
        triggers = []
        if initial_state.p_interstitial_mmHg >= 4.0:
            return {
                "final_state": initial_state,
                "success": False,
                "triggers": ["STOP: Pre-existing Pulmonary Congestion/Hypoxia"],
                "predicted_map_rise": 0,
                "fluid_leaked_percentage": 0
            }
            
        current_state = initial_state
        rate_ml_hr = (volume_ml / duration_min) * 60
        
        aborted = False
        trajectory = [] 

        # 1. CAPTURE T=0 (Initial State)
        # This forces the graph to start at your INPUT BP, not the calculated T=1.
        if return_series:
            # Visual Fix: Clamp lung water to 0 (Negative pressure = Dry Lungs)
            display_lung_water = max(0.0, initial_state.p_interstitial_mmHg)
            
            trajectory.append({
                "time": 0, # <--- Start at Time 0
                "map": int(initial_state.map_mmHg),
                "lung_water": round(display_lung_water, 1),
                "leak_rate": 0.0,
                "urine_output": 0.0,
                "sodium": round(initial_state.current_sodium, 1),
                "potassium": round(initial_state.current_potassium, 2),
                "glucose": int(initial_state.current_glucose_mg_dl),
                "hb": round(initial_state.current_hemoglobin, 1),
                "hct": round(initial_state.current_hematocrit_dynamic, 1)
            })
        
        # SIMULATION LOOP
        for t in range(int(duration_min)):
            current_state = PediaFlowPhysicsEngine.simulate_single_step(
                current_state, params, rate_ml_hr, fluid, dt_minutes=1.0
            )
            
            # Record key metrics every minute
            if return_series:
                trajectory.append({
                    "time": t + 1,
                    "map": int(current_state.map_mmHg),
                    "lung_water": round(current_state.p_interstitial_mmHg, 1),
                    "leak_rate": round(current_state.q_leak_ml_min, 2),
                    "urine_output": round(current_state.q_urine_ml_min, 2),
                    # Labs / Metabolics (NEW)
                    "sodium": round(current_state.current_sodium, 1),
                    "potassium": round(current_state.current_potassium, 2), # Critical for Renal
                    "glucose": int(current_state.current_glucose_mg_dl),
                    "hb": round(current_state.current_hemoglobin, 1),
                    "hct": round(current_state.current_hematocrit_dynamic, 1)
                })
            
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
            "fluid_leaked_percentage": int((current_state.q_leak_ml_min / (rate_ml_hr/60))*100) if rate_ml_hr > 0 else 0,
            "trajectory": trajectory 
          }
