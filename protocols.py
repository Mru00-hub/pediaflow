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
        is_hypoglycemic = state.current_glucose_mg_dl < 54.0
        is_sam_risk = input.muac_cm < 11.5 and state.current_glucose_mg_dl < 70.0
        
        if is_hypoglycemic or is_sam_risk:
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
        is_sam = input.muac_cm < 11.5

        # 1. Specific Dosing for Blood Products
        if fluid == FluidType.PRBC:
            # SAFETY: Never give 20ml/kg Blood as a rapid bolus.
            # Standard: 10ml/kg. 
            # Duration: Emergency = 60 mins, Standard = 240 mins.
            # We assume Emergency here since it's a shock calculator.
            volume = int(input.weight_kg * 10)
            duration = 60 # Slower than crystalloid (20 mins)
        elif fluid == FluidType.COLLOID_ALBUMIN:
             # Colloids are potent expanders. 10-20ml/kg.
             volume = int(input.weight_kg * 10) # Conservative start
             duration = 20
        else:
            # Standard Crystalloid Logic (RL/NS)
            volume = int(input.weight_kg * (10 if is_sam else 20))
            duration = 60 if is_sam else 20
        
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
            "seconds_per_drop": round(sec_per_drop, 2) 
        }
