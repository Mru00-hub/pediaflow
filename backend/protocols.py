# protocols.py
from models import PatientInput, SimulationState, FluidType, ClinicalDiagnosis

class FluidSelector:
    @staticmethod
    def select_initial_fluid(input: PatientInput, state: SimulationState) -> FluidType:
        if input.hemoglobin_g_dl < 5.0: 
            return FluidType.PRBC
        # 2. Hypoglycemia Priority (Decoupled from SAM)
        # Any child with Glucose < 54 mg/dL needs Dextrose immediately.
        # We also keep the < 70 threshold if they are SAM, as they are more vulnerable.
        threshold = 54.0 # Base threshold for healthy children
        
        if input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK:
             # PREDICTIVE: Sepsis burns sugar fast. 
             # We treat < 90 as "At Risk" to prevent crashing during simulation.
             threshold = 90.0 
        elif input.muac_cm < 11.5:
             # SAM children have low glycogen stores.
             threshold = 70.0 
             
        is_hypoglycemic = state.current_glucose_mg_dl < threshold
        
        if is_hypoglycemic:
            return FluidType.D5_NS
        # 3. Dengue Shock: Critical Phase Refractory
        # If they are in day 4-6 and have already had boluses, consider Colloid
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            pulse_pressure = input.systolic_bp - (input.diastolic_bp if input.diastolic_bp else 0)
            # If late illness day AND narrow pulse pressure (Shock)
            if input.illness_day in [4, 5, 6] and pulse_pressure < 20 and pulse_pressure > 0:
                # Suggest Colloid as option for refractory
                return FluidType.COLLOID_ALBUMIN
                
        # 4. Default for Shock (IAP 2023 prefers RL over NS for acidosis)
        return FluidType.RL

class PrescriptionEngine:
    @staticmethod
    def generate_bolus(input: PatientInput, fluid: FluidType) -> dict:
        # SAM Protocol: Slower, smaller volume (10ml/kg over 1 hr)
        volume = 0
        duration = 60 # Default to slower infusion for safety
        
        is_sam = input.muac_cm < 11.5
        is_septic = input.diagnosis == ClinicalDiagnosis.SEPTIC_SHOCK
        if input.age_months < 2: 
            rr_limit = 60
        elif input.age_months < 12: 
            rr_limit = 50
        elif input.age_months < 60: 
            rr_limit = 40
        else: 
            rr_limit = 30 # >5 years
        is_hypoxic = input.sp_o2_percent < 92
        is_resp_distress = input.respiratory_rate_bpm >= rr_limit
        has_congestion_signs = input.baseline_hepatomegaly or is_hypoxic or is_resp_distress
        if input.age_months < 1:
            systolic_floor = 60
        elif input.age_months < 12:
            systolic_floor = 70
        elif input.age_months <= 120: # 1-10 years
            systolic_floor = 70 + (2 * (input.age_months / 12.0))
        else: # > 10 years
            systolic_floor = 90
            
        is_hypotensive = input.systolic_bp < systolic_floor
        
        # --- VOLUME CALCULATION ---
        if fluid == FluidType.D5_NS:
             # Hypoglycemia Management
             current_g = input.current_glucose if input.current_glucose is not None else 90.0
             if current_g < 54.0:
                 volume = int(input.weight_kg * 10) # Critical: 10ml/kg
                 duration = 30 
             else:
                 volume = int(input.weight_kg * 5)  # Buffer: 5ml/kg
                 duration = 30

        elif fluid == FluidType.PRBC:
            volume = int(input.weight_kg * 10)
            duration = 240 # Standard blood time

        elif fluid == FluidType.COLLOID_ALBUMIN:
             volume = int(input.weight_kg * 10)
             duration = 30

        else:
            # CRYSTALLOIDS (RL/NS) - The Core Shock Logic
            if input.diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
                 # WHO PLAN C (Severe Dehydration)
                 # Initial aggressive loading dose: 30 ml/kg
                 # (Followed by 70ml/kg later, but this function generates the *first* bolus)
                 volume = int(input.weight_kg * 30) 
                 
                 # Duration: 
                 # Infants (<12mo): 1 hour
                 # Older Children: 30 mins
                 if input.age_months < 12:
                     duration = 60
                 else:
                     duration = 30
                 
                 # SAM Safety Override for Plan C
                 if is_sam:
                     volume = int(input.weight_kg * 20) # Conservative
                     duration = 60 # Slower
            
            elif is_septic:
                 # SEPTIC SHOCK: 20ml/kg first hour (WHO / Surviving Sepsis)
                 # Note: Aggressive 15-min boluses are debated; 60 min is safer default.
                 volume = int(input.weight_kg * 20)
                 if is_sam: volume = int(input.weight_kg * 15)

                 # 2. Duration Determination
                 # Baseline: 60 minutes (Safe for compensated shock/unknown status)
                 duration = 60 

                 # 3. RAPID RESCUE OVERRIDE (The "Fast Bolus")
                 # Criteria: Hypotensive (Decompensated) AND "Dry" (Safe to fill)
                 
                 # Calc Hypotension Threshold (PALS approx: 70 + 2*age_years)
                 if is_hypotensive and not is_sam and not has_congestion_signs:
                     duration = 20 # Fast push to restore BP
                     # Rationale: Restore perfusion pressure immediately to prevent arrest.
                
            elif is_sam:
                 # Undifferentiated Shock + SAM
                 volume = int(input.weight_kg * 15)
                 duration = 60
                 
            else:
                 # Undifferentiated Shock (Healthy child)
                 volume = int(input.weight_kg * 20)
                 duration = 45
                
        # --- SAFETY BRAKES (Overrides everything else) ---
        # If the lungs are ALREADY wet or failing, we must slow down, 
        # even if hypotensive (Start inotropes instead of flooding).
        if has_congestion_signs:
            duration = max(duration, 60)
            if input.sp_o2_percent < 85: # Severe Hypoxia
                 duration = max(duration, 90) # Trickle
                
        # Calculate Flow Rate
        rate_ml_hr = (volume / duration) * 60
        
        # Calculate Drip Rates
        drops_per_ml = input.iv_set_available.value
        drops_per_min = (rate_ml_hr / 60.0) * drops_per_ml
        
        # 2. UX Safety for "Impossible Rates"
        # If rate is too high to count (>100 dpm), clamp for display 
        # but keep true rate for pumps.
        readable_drops = drops_per_min
        if drops_per_min > 100:
            readable_drops = ">100 (Uncountable)"

        # Avoid division by zero
        if drops_per_min > 0:
            sec_per_drop = 60.0 / drops_per_min
        else:
            sec_per_drop = 0.0
        
        return {
            "volume_ml": volume, 
            "duration_min": duration,
            "rate_ml_hr": int(rate_ml_hr), 
            "drops_per_min": int(drops_per_min),
            "readable_drops": readable_drops,
            "seconds_per_drop": round(sec_per_drop, 2) 
        }
