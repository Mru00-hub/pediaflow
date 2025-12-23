# safety.py
from models import SimulationState, PhysiologicalParams, PatientInput, SafetyAlerts, ClinicalDiagnosis

class SafetySupervisor:
    @staticmethod
    def check_real_time(state: SimulationState, params: PhysiologicalParams, 
                        input: PatientInput) -> SafetyAlerts:
        alerts = SafetyAlerts()
        
        # Cerebral Edema (Na change > 12 mEq/24h)
        time_hours = state.time_minutes / 60.0
        if time_hours > 0:
            na_rate = state.total_sodium_load_meq / time_hours
            if na_rate * 24 > 12.0:
                alerts.risk_cerebral_edema = True
        
        # Hypoglycemia
        if state.current_glucose_mg_dl < 54.0:
            alerts.risk_hypoglycemia = True
        
        # SAM Heart Warning
        if params.cardiac_contractility < 0.6:
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
