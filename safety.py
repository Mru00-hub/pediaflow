# safety.py
from models import SimulationState, PhysiologicalParams, PatientInput, SafetyAlerts, ClinicalDiagnosis

class SafetySupervisor:
    @staticmethod
    def check_real_time(state: SimulationState, params: PhysiologicalParams, 
                        input: PatientInput) -> SafetyAlerts:
        alerts = SafetyAlerts()

        # 1. Pulmonary Edema Risk
        # Stop if interstitial pressure indicates wet lungs (>5 mmHg)
        if state.p_interstitial_mmHg > 5.0:
            alerts.risk_pulmonary_edema = True
            
        # 2. Volume Overload Risk
        # Warning if total fluid exceeds 40ml/kg (standard limit before re-eval)
        safe_limit = input.weight_kg * 40.0 
        if state.total_volume_infused_ml > safe_limit:
            alerts.risk_volume_overload = True

        # 3. Cerebral Edema Risk (Tonicity Mismatch)
        # Calculate Sodium Concentration of the fluid given so far
        if state.total_volume_infused_ml > 0:
            fluid_na_conc = (state.total_sodium_load_meq * 1000.0) / state.total_volume_infused_ml
            
            # RISK: Patient is Hypernatremic (>145) and we give Hypotonic fluid (<130)
            # This causes rapid water shift into brain cells.
            if input.current_sodium > 145 and fluid_na_conc < 130:
                alerts.risk_cerebral_edema = True
            
            # RISK: Rapid Hyponatremia Induction (Fluid is much lower than patient)
            if fluid_na_conc < (input.current_sodium - 15):
                 alerts.risk_cerebral_edema = True
        
        # Hypoglycemia
        if state.current_glucose_mg_dl < 54.0:
            alerts.risk_hypoglycemia = True
        
        # SAM Heart Warning
        is_sam_clinical = (input.muac_cm < 11.5) or (input.diagnosis == ClinicalDiagnosis.SAM_DEHYDRATION)
        
        if params.cardiac_contractility < 0.6 or is_sam_clinical:
            alerts.sam_heart_warning = True

        # 5. Ketoacidosis / Hyperglycemia Risk
        # Scenario A: Simple Hyperglycemia (Primary Screen for DKA) - Catches Test F
        is_dka_risk = (input.current_glucose and input.current_glucose > 250.0)
        
        # Scenario B: Metabolic Stress/Failure (Your existing logic)
        # High Lactate + Moderate Hyperglycemia suggests cells aren't using sugar
        is_metabolic_stress = (
            input.lactate_mmol_l is not None and 
            input.lactate_mmol_l > 5.0 and 
            state.current_glucose_mg_dl > 180 # Lower threshold if lactate is high
        )

        if is_dka_risk or is_metabolic_stress:
            alerts.risk_ketoacidosis = True

        # 6. Dengue Active Leak Warning
        # If we see Hct rising despite fluid (hemoconcentration)
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            # Logic A: Simulation shows Hct rising (Severe Hemoconcentration)
            hct_rising = state.current_hematocrit_dynamic > input.hematocrit_pct
            
            # Logic B: Physics calculates active capillary leak (> 1.0 ml/min)
            # This captures the "leaky state" (Day 4-6) even if the bolus temporarily 
            # dilutes the blood (masking the Hct rise).
            is_leaking_active = state.q_leak_ml_min > 0.1
            
            if hct_rising or is_leaking_active:
                alerts.dengue_leak_warning = True
                
        # 7. Refractory Shock (Hydrocortisone) ---
        # Trigger if Lactate is critically high (>7) implying tissue failure
        # OR if BP remains low despite treatment (Refractory)
        print(f"DEBUG CHECK: Diagnosis={input.diagnosis}, Lactate={input.lactate_mmol_l}")

        if input.lactate_mmol_l and input.lactate_mmol_l > 7.0:
             print("DEBUG: Triggering Hydrocortisone!")
             alerts.hydrocortisone_needed = True
        
        # 8. Anemia Dilution Warning ---
        # Trigger if Hb is in the "Danger Zone" (5-7) where fluids might dilute it < 5.
        # (If it was < 4, the Protocol Engine would have already switched to Blood)
        if 4.0 < input.hemoglobin_g_dl < 7.0:
             alerts.anemia_dilution_warning = True
            
        return alerts
