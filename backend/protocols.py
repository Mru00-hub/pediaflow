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
        is_sam = input.muac_cm < 11.5
        diagnosis = input.diagnosis

        if fluid == FluidType.D5_NS:
             # Check the actual glucose to decide dose size
             # (Handle None safely by defaulting to 90)
             current_g = input.current_glucose if input.current_glucose is not None else 90.0
             
             if current_g < 54.0:
                 # A. CRITICAL HYPOGLYCEMIA (< 54 mg/dL)
                 # Priority: Immediate Sugar Load + Volume.
                 # Dose: Full Shock Bolus (10 ml/kg)
                 volume = int(input.weight_kg * 10)
                 duration = 30 # Slower than saline to prevent rapid osmotic shift
             else:
                 # B. PROACTIVE BUFFER (54 - 90 mg/dL)
                 # Priority: Prevent crash, but don't cause Hyperglycemia/Overload.
                 # Dose: Half Bolus (5 ml/kg)
                 volume = int(input.weight_kg * 5)
                 duration = 30

        # 1. Specific Dosing for Blood Products
        if fluid == FluidType.PRBC:
            # SAFETY: Never give 20ml/kg Blood as a rapid bolus.
            # Standard: 10ml/kg. 
            # Duration: Emergency = 60 mins, Standard = 240 mins.
            # We assume Emergency here since it's a shock calculator.
            volume = int(input.weight_kg * 10)
            duration = 240 # Slower than crystalloid (20 mins)
        elif fluid == FluidType.COLLOID_ALBUMIN:
             # Colloids are potent expanders. 10-20ml/kg.
             volume = int(input.weight_kg * 10) # Conservative start
             duration = 20
        else:
            # A. PURE VOLUME LOSS (Diarrhea/Vomiting)
            # The tank has a leak. We must refill it.
            if diagnosis == ClinicalDiagnosis.SEVERE_DEHYDRATION:
                 # WHO "Plan C"
                 volume = int(input.weight_kg * 20)
                 duration = 60 if is_sam else 20 # Slower if malnutrition
            
            # B. DISTRIBUTIVE SHOCK (Sepsis/Dengue/Unknown)
            # The tank is leaky/weak. DO NOT OVERFILL.
            # FEAST Trial / WHO 2022 Conservative Protocol
            else:
                 volume = int(input.weight_kg * 10) # [CHANGED FROM 20]
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
            "readable_drops": readable_drops,
            "seconds_per_drop": round(sec_per_drop, 2) 
        }
