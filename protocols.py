# protocols.py
from models import PatientInput, SimulationState, FluidType, ClinicalDiagnosis

class FluidSelector:
    @staticmethod
    def select_initial_fluid(input: PatientInput, state: SimulationState) -> FluidType:
        if input.hemoglobin_g_dl < 5.0: 
            return FluidType.PRBC
        if input.muac_cm < 11.5 and state.current_glucose_mg_dl < 70: 
            return FluidType.D5_NS
        # 3. Dengue Shock: Critical Phase Refractory
        # If they are in day 4-6 and have already had boluses, consider Colloid
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            if input.illness_day in [4, 5, 6] and state.cumulative_bolus_count >= 2:
                return FluidType.COLLOID_ALBUMIN
                
        # 4. Default for Shock (IAP 2023 prefers RL over NS for acidosis)
        return FluidType.RL

class PrescriptionEngine:
    @staticmethod
    def generate_bolus(input: PatientInput, fluid: FluidType) -> dict:
        # SAM Protocol: Slower, smaller volume (10ml/kg over 1 hr)
        is_sam = input.muac_cm < 11.5
        
        volume = int(input.weight_kg * (10 if is_sam else 20))
        duration = 60 if is_sam else 20
        
        # Calculate Flow Rate
        rate_ml_hr = (volume / duration) * 60
        
        # Calculate Drip Rates
        drops_per_ml = input.iv_set_available.value
        drops_per_min = (rate_ml_hr / 60.0) * drops_per_ml
        
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
            "seconds_per_drop": round(sec_per_drop, 2) # Added for UI Metronome
        }
