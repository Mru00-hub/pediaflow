# safety.py
from models import SimulationState, PhysiologicalParams, PatientInput, SafetyAlerts, ClinicalDiagnosis

class SafetySupervisor:
    @staticmethod
    def check_real_time(state: SimulationState, params: PhysiologicalParams, 
                        input: PatientInput) -> SafetyAlerts:
        alerts = SafetyAlerts()

        # Cerebral Edema Risk (Tonicity Mismatch)
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

        # 4. Anemia / Hemodilution Warning (Secondary check)
        # If not critical (<5) but low (<7), warn.
        if state.current_hematocrit_dynamic < 21.0: # Approx Hb 7
            alerts.anemia_dilution_warning = True

        # 5. Ketoacidosis Risk
        # If D5 is used but Lactate is high, glucose might not be metabolizing well
        if input.lactate_mmol_l and input.lactate_mmol_l > 5.0 and state.current_glucose_mg_dl > 250:
            alerts.risk_ketoacidosis = True

        # 6. Dengue Active Leak Warning
        # If we see Hct rising despite fluid (hemoconcentration)
        if input.diagnosis == ClinicalDiagnosis.DENGUE_SHOCK:
            if state.current_hematocrit_dynamic > input.hematocrit_pct:
                alerts.dengue_leak_warning = True
            
        return alerts
